# mcu_comm/driver.py
"""MCUComm: a lightweight, thread-aware serial driver for the framed MCU protocol.

Responsibilities:
- Open/close serial port
- Background read thread that parses frames and dispatches callbacks
- Safe send helpers (send_frame, send_handshake)
- Callback registration by message type or wildcard

The driver intentionally delegates payload decoding to the application layer.
"""
import threading
import serial
import time
import logging
from typing import Callable, Dict, List, Optional

from .protocol import PacketParser, build_frame, xor_crc, u16_le, u32_le, MSG_DESIRED_FLOW, MSG_DESIRED_FLOW_IMMEDIATE
from .protocol import CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG, MSG_FLOWMETER_PULSE_DEBUG

# near other imports from .protocol
from .protocol import decode_telemetry, MSG_TELEMETRY_PUSH

# Add imports at top of file (if not already present)
import struct
# mcu_comm/driver.py (patch - imports)
# add these imports (merge with existing imports)
from .protocol import (
    build_config_payload,
    CONFIG_TAG_TELEMETRY_PERIOD_MS,
    CONFIG_TAG_HEARTBEAT_PERIOD_MS,
    CONFIG_TAG_PI_KP,
    CONFIG_TAG_PI_KI,
    CONFIG_TAG_ENABLE_PI_CONTROL,
    MSG_CONFIG,
    MSG_SET_PUMP_PWM,
    MSG_EXIT_SYS_DEBUG,
    CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG,
    CONFIG_TAG_SERIAL_SEND_MS,
    CONFIG_TAG_PWM_DEBUG,
    CONFIG_TAG_ENABLE_ECHO_DEBUG,
    CONFIG_TAG_FLOW_WINDOW_MS,
    CONFIG_TAG_FLOW_PULSES_PER_LITRE,
    CONFIG_TAG_ENABLE_LOOKUP_TABLE,
    CONFIG_TAG_PUMP_SAMPLE_TIME_MS,
    # --- add the stepper message IDs here (ensure protocol exports these) ---
    MSG_GO_HOME,
    MSG_SET_MIDDLE,
    MSG_POSITION_MODE2,
)

logger = logging.getLogger(__name__)

class MCUComm:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.01):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self._parser = PacketParser()
        self._callbacks: Dict[int, List[Callable[[dict], None]]] = {}
        self._wildcard_callbacks: List[Callable[[dict], None]] = []
        self._read_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._seq = 0

        # latest parsed telemetry (dict) — updated by internal handler
        self._latest_telemetry: Optional[dict] = None

        # telemetry-specific callbacks: called with parsed telemetry dict
        self._telemetry_callbacks: List[Callable[[dict], None]] = []


        # register internal parser for telemetry messages so we always decode them
        # BEFORE user callbacks (we register internal handler first)
        self.register_callback(MSG_TELEMETRY_PUSH, self._handle_telemetry_packet)

    # ---- lifecycle ----
    def open(self):
        if self._ser and self._ser.is_open:
            return
        self._ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
        self._stop_event.clear()
        self._read_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._read_thread.start()
        logger.info("Opened serial %s @ %d", self.port, self.baud)

    def close(self):
        self._stop_event.set()
        if self._read_thread:
            self._read_thread.join(timeout=1.0)
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        logger.info("Closed serial %s", self.port)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ---- callbacks ----
    def register_callback(self, msg_type: Optional[int], cb: Callable[[dict], None]):
        """Register a callback for a specific msg_type or for all messages.

        msg_type: integer message type (e.g. 0x13) or None for wildcard (all messages)
        cb: callable that receives the parsed packet dict
        """
        if msg_type is None:
            self._wildcard_callbacks.append(cb)
        else:
            self._callbacks.setdefault(msg_type, []).append(cb)

    def unregister_callback(self, msg_type: Optional[int], cb: Callable[[dict], None]):
        if msg_type is None:
            if cb in self._wildcard_callbacks:
                self._wildcard_callbacks.remove(cb)
        else:
            if msg_type in self._callbacks and cb in self._callbacks[msg_type]:
                self._callbacks[msg_type].remove(cb)

    def _dispatch(self, pkt: dict):
        # call specific callbacks
        t = pkt.get("type")
        if t is not None and t in self._callbacks:
            for cb in list(self._callbacks[t]):
                try:
                    cb(pkt)
                except Exception:
                    logger.exception("callback error for type %s", t)
        # wildcard callbacks
        for cb in list(self._wildcard_callbacks):
            try:
                cb(pkt)
            except Exception:
                logger.exception("wildcard callback error")

    # ---- send helpers ----
    def _next_seq(self) -> int:
        with self._lock:
            v = self._seq
            self._seq = (self._seq + 1) & 0xFF
            return v

    def send_frame(self, msg_type: int, payload: bytes) -> int:
        seq = self._next_seq()
        frame = build_frame(msg_type, seq, payload)
        with self._lock:
            if not self._ser or not self._ser.is_open:
                raise RuntimeError("Serial port not open")
            self._ser.write(frame)
        logger.debug("TX type=0x%02X seq=%d len=%d", msg_type, seq, len(payload))
        return seq

    def send_handshake(self, hb_ms: int, tel_ms: int, send_ack: bool, extra: bytes = b"") -> int:
        payload = bytearray()
        payload += u16_le(hb_ms)
        payload += u16_le(tel_ms)
        payload.append(1 if send_ack else 0)
        if extra:
            payload += extra
        return self.send_frame(0x10, bytes(payload))

    def send_desired_flow(self, flow_ml_per_min: int) -> int:
        """
        Send a scheduled desired flow command (MSG_DESIRED_FLOW).
        flow_ml_per_min: unsigned 32-bit integer mL/min
        Returns the sequence number used for the frame.
        """
        if not (0 <= flow_ml_per_min <= 0xFFFFFFFF):
            raise ValueError("flow_ml_per_min out of range 0..0xFFFFFFFF")
        payload = u32_le(flow_ml_per_min)
        return self.send_frame(MSG_DESIRED_FLOW, payload)

    def send_desired_flow_immediate(self, flow_ml_per_min: int) -> int:
        """
        Send an immediate desired flow command (MSG_DESIRED_FLOW_IMMEDIATE).
        """
        if not (0 <= flow_ml_per_min <= 0xFFFFFFFF):
            raise ValueError("flow_ml_per_min out of range 0..0xFFFFFFFF")
        payload = u32_le(flow_ml_per_min)
        return self.send_frame(MSG_DESIRED_FLOW_IMMEDIATE, payload)

    # Convenience emulation helpers (kept for development)
    @staticmethod
    def build_raw_stepper_gohome_ack():
        pkt = bytearray([0xFB, 0x03, 0x91, 0x02])
        checksum = sum(pkt) & 0xFF
        pkt.append(checksum)
        return bytes(pkt)

    @staticmethod
    def build_raw_stepper_setzero_ack():
        pkt = bytearray([0xFB, 0x03, 0x92, 0x01])
        checksum = sum(pkt) & 0xFF
        pkt.append(checksum)
        return bytes(pkt)

    # ---- reader loop ----
    def _reader_loop(self):
        ser = self._ser
        if ser is None:
            return
        while not self._stop_event.is_set():
            try:
                data = ser.read(256)
            except Exception:
                logger.exception("serial read error")
                break
            if data:
                for b in data:
                    pkt = self._parser.feed(b)
                    if pkt is not None:
                        self._dispatch(pkt)
            else:
                # avoid busy spin
                time.sleep(0.001)

    def send_config(self, fields: list) -> int:
        """
        Generic: send a MSG_CONFIG with TLV fields.

        fields: list of (tag:int, value:bytes)
        returns: sequence number used
        """
        payload = build_config_payload(fields)
        return self.send_frame(MSG_CONFIG, payload)

    # Convenience wrappers for common types --------------------------------
    def send_config_u16(self, tag: int, value: int) -> int:
        """Send a 2-byte little-endian unsigned int TLV field."""
        if not (0 <= value <= 0xFFFF):
            raise ValueError("u16 out of range")
        val = bytes([value & 0xFF, (value >> 8) & 0xFF])
        return self.send_config([(tag, val)])

    def send_config_u8(self, tag: int, value: int) -> int:
        """Send a 1-byte unsigned TLV field."""
        if not (0 <= value <= 0xFF):
            raise ValueError("u8 out of range")
        val = bytes([value & 0xFF])
        return self.send_config([(tag, val)])

    def send_config_f32(self, tag: int, value: float) -> int:
        """Send a 4-byte little-endian IEEE754 float TLV field."""
        val = struct.pack("<f", float(value))
        return self.send_config([(tag, val)])

    def send_set_pump_pwm(self, duty: int) -> int:
        """
        Send MSG_SET_PUMP_PWM to set manual pump PWM duty and put MCU into SYS_DEBUG.
        duty: int 0..99 (MCU accepts 0..PUMP_DUTY_MAX==99); we'll validate here.
        returns: sequence number used
        """
        if not (0 <= duty <= 99):
            raise ValueError("duty must be 0..99")
        payload = bytes([duty & 0xFF])
        return self.send_frame(MSG_SET_PUMP_PWM, payload)

    def send_exit_sys_debug(self) -> int:
        """
        Send MSG_EXIT_SYS_DEBUG (no payload). This instructs MCU to return to SYS_RUNNING_PI
        if currently in SYS_DEBUG.
        """
        return self.send_frame(MSG_EXIT_SYS_DEBUG, b"")

    # ---- convenience config helpers ----
    def send_config_bool(self, tag: int, enabled: bool) -> int:
        """Send a 1-byte TLV boolean (0/1)."""
        return self.send_config_u8(tag, 1 if enabled else 0)

    def send_config_flowmeter_pulse_send_debug(self, enabled: bool) -> int:
        """Set CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG on the MCU (0/1)."""
        from mcu_comm.protocol import CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG
        return self.send_config_bool(CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG, enabled)

    # ---- stepper / motor helpers ----
    def send_stepper_go_home(self, slave_addr: int = 0x03) -> int:
        """
        Instruct the stepper to go home.
        Payload (legacy): [slave_addr:1byte]
        Returns the sequence number used.
        """
        if not (0 <= slave_addr <= 0xFF):
            raise ValueError("slave_addr out of range 0..0xFF")
        payload = bytes([slave_addr & 0xFF])
        return self.send_frame(MSG_GO_HOME, payload)

    def send_stepper_set_middle(self) -> int:
        """
        Instruct the stepper to move to the predefined 'middle' position.
        No payload required (keeps parity with legacy implementation).
        Returns the sequence number used.
        """
        return self.send_frame(MSG_SET_MIDDLE, b"")

    def send_stepper_move_to(self, steps: int, slave_addr: int = 0x03,
                             speed: int = 1000, acc: int = 150) -> int:
        """
        Move the stepper to an absolute position (position mode 2).
        Firmware expects a 4-byte little-endian signed int (int32) with steps.
        Note: firmware currently ignores slave/speed/acc arguments and uses hardcoded values,
              but we keep them here for API clarity and future compatibility.

        Returns the sequence number used.
        """
        # pack as signed 32-bit little-endian
        payload = struct.pack('<i', int(steps))
        return self.send_frame(MSG_POSITION_MODE2, payload)
    
    # ---- internal telemetry handling ----
    def _handle_telemetry_packet(self, pkt: dict):
        """
        Internal callback registered for MSG_TELEMETRY_PUSH packets.
        Parses payload (using protocol.decode_telemetry) and updates internal state.
        Also calls any registered telemetry callbacks.
        pkt: dict from PacketParser: {'type','seq','len','payload','crc'}
        """
        payload = pkt.get("payload", b"")
        try:
            tel = decode_telemetry(payload)
        except Exception as e:
            logger.exception("Failed to decode telemetry payload: %s", e)
            return

        # store latest telemetry
        self._latest_telemetry = tel

        # notify telemetry-specific callbacks
        for cb in list(self._telemetry_callbacks):
            try:
                cb(tel)
            except Exception:
                logger.exception("telemetry callback error")

    # ---- telemetry helpers (public) ----
    def register_telemetry_callback(self, cb: Callable[[dict], None]) -> None:
        """
        Register a callback that will be called with parsed telemetry dicts
        whenever a telemetry packet arrives.
        """
        self._telemetry_callbacks.append(cb)

    def unregister_telemetry_callback(self, cb: Callable[[dict], None]) -> None:
        if cb in self._telemetry_callbacks:
            self._telemetry_callbacks.remove(cb)

    def get_latest_telemetry(self) -> Optional[dict]:
        """Return the most recently parsed telemetry dict, or None if none received yet."""
        return self._latest_telemetry

    def get_latest_secondary_flow(self) -> Optional[int]:
        """Convenience: return the latest secondary flow (flow2, mL/min) or None."""
        tel = self._latest_telemetry
        if tel is None:
            return None
        return tel.get("flow2")