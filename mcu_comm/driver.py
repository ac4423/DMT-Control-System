# mcu_comm/driver.py
"""MCUComm: a lightweight, thread-aware serial driver for the framed MCU protocol.

Responsibilities:
- Open/close serial port
- Background read thread that parses frames and dispatches callbacks
- Safe send helpers (send_frame, send_handshake, send_desired_flow, etc.)
- Callback registration by message type or wildcard
- Internal telemetry decoding with latest-value cache and typed callbacks
- Config TLV helpers for tuning MCU parameters at runtime
- Stepper motor helpers (go home, set middle, move to absolute position)
- Pump PWM control

The driver intentionally delegates higher-level application logic to the caller.
"""

import struct
import threading
import serial
import time
import logging
from typing import Callable, Dict, List, Optional

from .protocol import (
    # Core framing
    PacketParser,
    build_frame,
    xor_crc,
    u16_le,
    u32_le,

    # Flow message IDs
    MSG_DESIRED_FLOW,
    MSG_DESIRED_FLOW_IMMEDIATE,

    # Telemetry
    decode_telemetry,
    MSG_TELEMETRY_PUSH,

    # Config system
    build_config_payload,
    MSG_CONFIG,
    CONFIG_TAG_TELEMETRY_PERIOD_MS,
    CONFIG_TAG_HEARTBEAT_PERIOD_MS,
    CONFIG_TAG_PI_KP,
    CONFIG_TAG_PI_KI,
    CONFIG_TAG_ENABLE_PI_CONTROL,
    CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG,
    CONFIG_TAG_SERIAL_SEND_MS,
    CONFIG_TAG_PWM_DEBUG,
    CONFIG_TAG_ENABLE_ECHO_DEBUG,
    CONFIG_TAG_FLOW_WINDOW_MS,
    CONFIG_TAG_FLOW_PULSES_PER_LITRE,
    CONFIG_TAG_ENABLE_LOOKUP_TABLE,
    CONFIG_TAG_PUMP_SAMPLE_TIME_MS,
    CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG,

    # Pump / debug control
    MSG_SET_PUMP_PWM,
    MSG_EXIT_SYS_DEBUG,
    MSG_FLOWMETER_PULSE_DEBUG,

    # Stepper motor
    MSG_GO_HOME,
    MSG_SET_MIDDLE,
    MSG_POSITION_MODE2,
)

logger = logging.getLogger(__name__)


class MCUComm:
    def __init__(self, port: str, baud: int = 115200, timeout: float = 0.01):
        self.port    = port
        self.baud    = baud
        self.timeout = timeout

        self._ser:         Optional[serial.Serial]   = None
        self._parser                                  = PacketParser()
        self._callbacks:   Dict[int, List[Callable[[dict], None]]] = {}
        self._wildcard_callbacks: List[Callable[[dict], None]]     = []
        self._read_thread: Optional[threading.Thread] = None
        self._stop_event  = threading.Event()
        self._lock        = threading.Lock()
        self._seq         = 0

        # Latest parsed telemetry dict — updated by the internal handler
        self._latest_telemetry: Optional[dict] = None

        # Typed telemetry callbacks: called with the *parsed* telemetry dict,
        # not the raw packet dict.  Separate from the generic callback system
        # so callers don't have to re-decode the payload themselves.
        self._telemetry_callbacks: List[Callable[[dict], None]] = []

        # Register the internal telemetry handler first so it always runs
        # before any user-registered callbacks for MSG_TELEMETRY_PUSH.
        self.register_callback(MSG_TELEMETRY_PUSH, self._handle_telemetry_packet)

    # ── Lifecycle ─────────────────────────────────────────────────────────

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

    # ── Callback registration ─────────────────────────────────────────────

    def register_callback(self, msg_type: Optional[int], cb: Callable[[dict], None]):
        """Register a callback for a specific msg_type or all messages (msg_type=None).

        The callback receives the raw parsed packet dict:
            {'type': int, 'seq': int, 'len': int, 'payload': bytes, 'crc': int}

        For decoded telemetry use register_telemetry_callback() instead.
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

    def register_telemetry_callback(self, cb: Callable[[dict], None]) -> None:
        """Register a callback that receives the *decoded* telemetry dict on every packet."""
        self._telemetry_callbacks.append(cb)

    def unregister_telemetry_callback(self, cb: Callable[[dict], None]) -> None:
        if cb in self._telemetry_callbacks:
            self._telemetry_callbacks.remove(cb)

    def _dispatch(self, pkt: dict):
        t = pkt.get("type")
        if t is not None and t in self._callbacks:
            for cb in list(self._callbacks[t]):
                try:
                    cb(pkt)
                except Exception:
                    logger.exception("callback error for type 0x%02X", t)
        for cb in list(self._wildcard_callbacks):
            try:
                cb(pkt)
            except Exception:
                logger.exception("wildcard callback error")

    # ── Internal telemetry handler ────────────────────────────────────────

    def _handle_telemetry_packet(self, pkt: dict):
        """
        Internal handler registered for MSG_TELEMETRY_PUSH.
        Decodes payload via protocol.decode_telemetry, caches result, and
        notifies all telemetry-specific callbacks with the decoded dict.
        """
        payload = pkt.get("payload", b"")
        try:
            tel = decode_telemetry(payload)
        except Exception:
            logger.exception("Failed to decode telemetry payload")
            return

        self._latest_telemetry = tel

        for cb in list(self._telemetry_callbacks):
            try:
                cb(tel)
            except Exception:
                logger.exception("telemetry callback error")

    # ── Telemetry accessors ───────────────────────────────────────────────

    def get_latest_telemetry(self) -> Optional[dict]:
        """Return the most recently decoded telemetry dict, or None if none received yet."""
        return self._latest_telemetry

    def get_latest_secondary_flow(self) -> Optional[int]:
        """Convenience: return the latest secondary flow (flow2, mL/min), or None."""
        tel = self._latest_telemetry
        return tel.get("flow2") if tel is not None else None

    # ── Reader loop ───────────────────────────────────────────────────────

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
                time.sleep(0.001)

    # ── Low-level send ────────────────────────────────────────────────────

    def _next_seq(self) -> int:
        with self._lock:
            v = self._seq
            self._seq = (self._seq + 1) & 0xFF
            return v

    def send_frame(self, msg_type: int, payload: bytes) -> int:
        """Build and transmit one framed packet. Returns the sequence number used."""
        seq   = self._next_seq()
        frame = build_frame(msg_type, seq, payload)
        with self._lock:
            if not self._ser or not self._ser.is_open:
                raise RuntimeError("Serial port not open")
            self._ser.write(frame)
        logger.debug("TX type=0x%02X seq=%d len=%d", msg_type, seq, len(payload))
        return seq

    # ── Connection helpers ────────────────────────────────────────────────

    def send_handshake(self, hb_ms: int, tel_ms: int, send_ack: bool,
                       extra: bytes = b"") -> int:
        payload = bytearray()
        payload += u16_le(hb_ms)
        payload += u16_le(tel_ms)
        payload.append(1 if send_ack else 0)
        if extra:
            payload += extra
        return self.send_frame(0x10, bytes(payload))

    # ── Flow control ──────────────────────────────────────────────────────

    def send_desired_flow(self, flow_ml_per_min: int) -> int:
        """Send MSG_DESIRED_FLOW (scheduled). flow_ml_per_min: unsigned 32-bit mL/min."""
        if not (0 <= flow_ml_per_min <= 0xFFFFFFFF):
            raise ValueError("flow_ml_per_min out of range 0..0xFFFFFFFF")
        return self.send_frame(MSG_DESIRED_FLOW, u32_le(flow_ml_per_min))

    def send_desired_flow_immediate(self, flow_ml_per_min: int) -> int:
        """Send MSG_DESIRED_FLOW_IMMEDIATE. flow_ml_per_min: unsigned 32-bit mL/min."""
        if not (0 <= flow_ml_per_min <= 0xFFFFFFFF):
            raise ValueError("flow_ml_per_min out of range 0..0xFFFFFFFF")
        return self.send_frame(MSG_DESIRED_FLOW_IMMEDIATE, u32_le(flow_ml_per_min))

    # ── Config TLV system ─────────────────────────────────────────────────

    def send_config(self, fields: list) -> int:
        """
        Send MSG_CONFIG with a list of TLV fields.
        fields: list of (tag: int, value: bytes) tuples.
        Returns the sequence number used.
        """
        payload = build_config_payload(fields)
        return self.send_frame(MSG_CONFIG, payload)

    def send_config_u8(self, tag: int, value: int) -> int:
        """Send a single 1-byte unsigned TLV field."""
        if not (0 <= value <= 0xFF):
            raise ValueError("u8 out of range")
        return self.send_config([(tag, bytes([value & 0xFF]))])

    def send_config_u16(self, tag: int, value: int) -> int:
        """Send a single 2-byte little-endian unsigned TLV field."""
        if not (0 <= value <= 0xFFFF):
            raise ValueError("u16 out of range")
        return self.send_config([(tag, bytes([value & 0xFF, (value >> 8) & 0xFF]))])

    def send_config_f32(self, tag: int, value: float) -> int:
        """Send a single 4-byte little-endian IEEE 754 float TLV field."""
        return self.send_config([(tag, struct.pack("<f", float(value)))])

    def send_config_bool(self, tag: int, enabled: bool) -> int:
        """Send a 1-byte boolean (0/1) TLV field."""
        return self.send_config_u8(tag, 1 if enabled else 0)

    def send_config_flowmeter_pulse_send_debug(self, enabled: bool) -> int:
        """Enable/disable flowmeter pulse debug output on the MCU."""
        return self.send_config_bool(CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG, enabled)

    # ── Pump / debug control ──────────────────────────────────────────────

    def send_set_pump_pwm(self, duty: int) -> int:
        """
        Send MSG_SET_PUMP_PWM to set manual pump PWM duty (puts MCU into SYS_DEBUG).
        duty: 0..99
        """
        if not (0 <= duty <= 99):
            raise ValueError("duty must be 0..99")
        return self.send_frame(MSG_SET_PUMP_PWM, bytes([duty & 0xFF]))

    def send_exit_sys_debug(self) -> int:
        """Send MSG_EXIT_SYS_DEBUG (no payload) to return MCU to SYS_RUNNING_PI."""
        return self.send_frame(MSG_EXIT_SYS_DEBUG, b"")

    # ── Stepper motor helpers ─────────────────────────────────────────────

    def send_stepper_go_home(self, slave_addr: int = 0x03) -> int:
        """Instruct the stepper to go to the home position. Returns sequence number."""
        if not (0 <= slave_addr <= 0xFF):
            raise ValueError("slave_addr out of range 0..0xFF")
        return self.send_frame(MSG_GO_HOME, bytes([slave_addr & 0xFF]))

    def send_stepper_set_middle(self) -> int:
        """Instruct the stepper to move to the predefined middle position."""
        return self.send_frame(MSG_SET_MIDDLE, b"")

    def send_stepper_move_to(self, steps: int, slave_addr: int = 0x03,
                             speed: int = 1000, acc: int = 150) -> int:
        """
        Move the stepper to an absolute position (position mode 2).
        Firmware expects a 4-byte little-endian signed int32 for steps.

        Note: firmware currently uses hardcoded speed/acc values; slave_addr/speed/acc
        are accepted here for API clarity and forward compatibility.
        """
        payload = struct.pack('<i', int(steps))
        return self.send_frame(MSG_POSITION_MODE2, payload)

    # ── Development / emulation helpers ──────────────────────────────────

    @staticmethod
    def build_raw_stepper_gohome_ack() -> bytes:
        """Build a raw stepper go-home acknowledgement packet (for testing/emulation)."""
        pkt      = bytearray([0xFB, 0x03, 0x91, 0x02])
        pkt.append(sum(pkt) & 0xFF)
        return bytes(pkt)

    @staticmethod
    def build_raw_stepper_setzero_ack() -> bytes:
        """Build a raw stepper set-zero acknowledgement packet (for testing/emulation)."""
        pkt      = bytearray([0xFB, 0x03, 0x92, 0x01])
        pkt.append(sum(pkt) & 0xFF)
        return bytes(pkt)