# comms_manager.py
import sys
import struct
import serial
import time
import queue
import threading
from PyQt6.QtCore import QObject, pyqtSignal, QThread

# Try to import MCUComm driver (primary)
try:
    from mcu_comm.driver import MCUComm
    from mcu_comm.protocol import (
        MSG_ACK,
        MSG_DESIRED_FLOW,
        MSG_DESIRED_FLOW_IMMEDIATE,
        MSG_HANDSHAKE_ACK,
        MSG_HEARTBEAT,
        MSG_NACK,
        MSG_TELEMETRY_PUSH as MSG_TELEMETRY,
    )
except Exception:
    MCUComm = None
    MSG_ACK = 0x01
    MSG_NACK = 0x02
    MSG_DESIRED_FLOW = None
    MSG_DESIRED_FLOW_IMMEDIATE = None
    MSG_HANDSHAKE_ACK = 0x12
    MSG_HEARTBEAT = 0x13
    # Keep a fallback numeric value for telemetry if driver import fails
    MSG_TELEMETRY = 0x03

# --- Configuration ---
if sys.platform.startswith('win'):
    SERIAL_PORT = "COM8"
else:
    SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 256000

# --- Protocol / legacy message IDs ---
HEADER_BYTE      = 0xA5
MSG_GO_HOME      = 0x41
MSG_SET_MIDDLE   = 0x42
MSG_POSITION_MODE2 = 0x43  # Move-to absolute (steps)
DEFAULT_HANDSHAKE_HEARTBEAT_MS = 500
DEFAULT_HANDSHAKE_TELEMETRY_MS = 200


# ---------- Fallback legacy listener ----------
class CommsListener(QThread):
    """
    Legacy background thread that reads and parses frames directly from serial.
    Used as a fallback if MCUComm is not available, or when running in camera-only
    mode with a controller attached via raw serial.
    """
    telemetry_received = pyqtSignal(int, int, int, int, int)  # ts, state, flow, vol, pos
    heartbeat_received = pyqtSignal(int, int, int, int)  # ts, state, startup_step, counter
    handshake_ack_received = pyqtSignal(int, int, int)  # ts, state, status
    nack_received = pyqtSignal(int, int)  # ts, state

    def __init__(self, serial_port):
        super().__init__()
        self.ser = serial_port
        self.running = True

    def run(self):
        while self.running:
            if not self.ser or not self.ser.is_open:
                self.msleep(100)
                continue
            try:
                if self.ser.in_waiting > 0:
                    byte = self.ser.read(1)
                    if byte == b'\xA5':
                        self._parse_packet()
                else:
                    self.msleep(1)
            except Exception as e:
                print(f"Serial Read Error: {e}")
                self.msleep(100)

    def _parse_packet(self):
        header_rem = self.ser.read(3)
        if len(header_rem) < 3:
            return
        msg_type, seq, payload_len = struct.unpack('BBB', header_rem)
        data = self.ser.read(payload_len + 1)
        if len(data) < payload_len + 1:
            return
        payload      = data[:-1]
        received_crc = data[-1]
        calc_crc     = msg_type ^ seq
        for b in payload:
            calc_crc ^= b
        if calc_crc != received_crc:
            print("CRC Mismatch! Dropping packet.")
            return
        if msg_type == MSG_TELEMETRY:
            self._decode_telemetry(payload)
        elif msg_type == MSG_HEARTBEAT:
            self._decode_heartbeat(payload)
        elif msg_type == MSG_HANDSHAKE_ACK:
            self._decode_handshake_ack(payload)
        elif msg_type == MSG_NACK:
            self._decode_nack(payload)

    def _decode_telemetry(self, payload):
        # 21 bytes: <I(Time) B(State) I(Flow) I(Vol) i(Pos) I(Rsv)
        if len(payload) != 21:
            return
        try:
            ts, state, flow, vol, pos, rsv = struct.unpack('<IBIIiI', payload)
            self.telemetry_received.emit(ts, state, flow, vol, pos)
        except struct.error:
            pass

    def _decode_heartbeat(self, payload):
        if len(payload) != 8:
            return
        try:
            ts, state, startup_step, counter = struct.unpack('<IBBH', payload)
            self.heartbeat_received.emit(ts, state, startup_step, counter)
        except struct.error:
            pass

    def _decode_handshake_ack(self, payload):
        if len(payload) != 6:
            return
        try:
            ts, state, status = struct.unpack('<IBB', payload)
            self.handshake_ack_received.emit(ts, state, status)
        except struct.error:
            pass

    def _decode_nack(self, payload):
        if len(payload) != 5:
            return
        try:
            ts, state = struct.unpack('<IB', payload)
            self.nack_received.emit(ts, state)
        except struct.error:
            pass

    def stop(self):
        self.running = False
        self.wait()


# ---------- CommsManager ----------
class CommsManager(QObject):
    """
    Unified communications manager.

    Connection priority:
      1. MCUComm driver (full-featured, preferred)
      2. Legacy raw serial + CommsListener thread
      3. Camera-only mode — no controller found; send calls are silently
         no-ops so the rest of the GUI keeps working without a controller.

    The public API (signals + send_* methods) is identical in all three modes,
    so callers never need to check which mode is active.
    """
    telemetry_data = pyqtSignal(int, int, int, int, int)  # ts, state, flow, vol, pos
    link_alive = pyqtSignal(bool)
    heartbeat_data = pyqtSignal(int, int, int, int)  # ts, state, startup_step, counter
    handshake_status = pyqtSignal(bool, str)
    tx_status = pyqtSignal(str)

    def __init__(self, port=SERIAL_PORT, baud=BAUD_RATE):
        super().__init__()
        self.port = port
        self.baud = baud

        self.mcu               = None
        self._fallback_listener = None
        self._ser              = None
        self.seq_counter       = 0
        self.camera_only       = False  # set True when no controller is reachable
        self.telemetry_seen    = False
        self.heartbeat_seen    = False
        self.handshake_acked   = False
        self._pairing_handshake_retry_sent = False
        self._last_heartbeat   = None
        self._tx_queue         = queue.Queue()
        self._tx_running       = False
        self._tx_thread        = None

        # ── Try MCUComm (primary) ──────────────────────────────────────────
        if MCUComm is not None:
            try:
                self.mcu = MCUComm(port=self.port, baud=self.baud, timeout=0.05)
                self.mcu.open()
                self.mcu.register_callback(MSG_TELEMETRY, self._on_mcu_packet)
                self.mcu.register_callback(MSG_HEARTBEAT, self._on_heartbeat_packet)
                self.mcu.register_callback(MSG_HANDSHAKE_ACK, self._on_handshake_ack_packet)
                self.mcu.register_callback(MSG_NACK, self._on_nack_packet)
                print(f"CommsManager: connected via MCUComm on {self.port} @ {self.baud}")
                self._start_tx_worker()
                self.send_handshake()
                self.link_alive.emit(True)
                return
            except Exception as e:
                print(f"CommsManager: MCU not found on {self.port}, trying legacy serial...")
                self.mcu = None

        # ── Try legacy raw serial + CommsListener (fallback) ──────────────
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.1, write_timeout=0.2)
            print(f"CommsManager: legacy serial connected on {self.port} @ {self.baud}")
            self._fallback_listener = CommsListener(self._ser)
            self._fallback_listener.telemetry_received.connect(self.telemetry_data)
            self._fallback_listener.telemetry_received.connect(
                lambda *_: self._mark_telemetry_seen())
            self._fallback_listener.heartbeat_received.connect(self._on_legacy_heartbeat)
            self._fallback_listener.handshake_ack_received.connect(self._on_legacy_handshake_ack)
            self._fallback_listener.nack_received.connect(self._on_legacy_nack)
            self._fallback_listener.start()
            self._start_tx_worker()
            self.send_handshake()
            self.link_alive.emit(True)
            return
        except serial.SerialException as e:
            print(f"CommsManager: no serial device on {self.port}.")
            self._ser = None

        # ── Camera-only mode ───────────────────────────────────────────────
        # No controller found; GUI continues without telemetry or motion control.
        self.camera_only = True
        print(
            f"CommsManager Warning: no controller found on {self.port}. "
            "Camera-only mode active — motion/flow commands will be ignored."
        )

    # ── MCUComm callback ──────────────────────────────────────────────────
    def _start_tx_worker(self):
        if self._tx_thread is not None:
            return
        self._tx_running = True
        self._tx_thread = threading.Thread(target=self._tx_loop, daemon=True)
        self._tx_thread.start()

    def _tx_loop(self):
        while self._tx_running:
            item = self._tx_queue.get()
            if item is None:
                break
            description, fn, args, kwargs = item
            try:
                fn(*args, **kwargs)
                self.tx_status.emit(f"TX: {description} sent")
            except Exception as e:
                msg = f"TX: {description} failed: {e}"
                print(f"CommsManager: {description} failed: {e}")
                self.tx_status.emit(msg)

    def _enqueue_tx(self, description, fn, *args, **kwargs):
        if self.camera_only:
            msg = f"TX: {description} ignored - serial not connected"
            print(f"CommsManager: camera-only - {description} ignored")
            self.tx_status.emit(msg)
            return
        if self._tx_thread is None:
            try:
                fn(*args, **kwargs)
                self.tx_status.emit(f"TX: {description} sent")
            except Exception as e:
                msg = f"TX: {description} failed: {e}"
                print(f"CommsManager: {description} failed: {e}")
                self.tx_status.emit(msg)
            return
        self.tx_status.emit(f"TX: {description} queued")
        self._tx_queue.put((description, fn, args, kwargs))

    def _mark_telemetry_seen(self):
        if not self.telemetry_seen:
            self.telemetry_seen = True
            self.link_alive.emit(True)

    def _mark_heartbeat_seen(self, ts, state, startup_step, counter):
        self.heartbeat_seen = True
        self._last_heartbeat = {
            "ts": ts,
            "state": state,
            "startup_step": startup_step,
            "counter": counter,
        }
        self.heartbeat_data.emit(ts, state, startup_step, counter)
        self.link_alive.emit(True)

        if state == 1 and not self.handshake_acked and not self._pairing_handshake_retry_sent:
            self._pairing_handshake_retry_sent = True
            self.send_handshake()
        elif state != 1 and not self.handshake_acked:
            self._pairing_handshake_retry_sent = False

    def _on_legacy_heartbeat(self, ts, state, startup_step, counter):
        self._mark_heartbeat_seen(ts, state, startup_step, counter)

    def _on_legacy_handshake_ack(self, ts, state, status):
        self.handshake_acked = True
        self.handshake_status.emit(True, f"ACK ts={ts} state={state} status={status}")

    def _on_legacy_nack(self, ts, state):
        self.handshake_status.emit(False, f"NACK ts={ts} state={state}")

    def _on_mcu_packet(self, pkt: dict):
        """
        Called in MCUComm's reader thread. Decode telemetry and emit Qt signal.
        pyqtSignal.emit() is thread-safe.
        """
        if not pkt or "invalid" in pkt:
            return
        t       = pkt.get("type")
        payload = pkt.get("payload", b"")
        if t == MSG_TELEMETRY and len(payload) == 25:
            try:
                ts, state, flow1, total1, flow2, total2, pos = struct.unpack('<IBIIIIi', payload)
                self._mark_telemetry_seen()
                self.telemetry_data.emit(ts, state, flow1, total1, pos)
            except struct.error:
                pass

    # ── Internal raw sender ───────────────────────────────────────────────
    def _on_heartbeat_packet(self, pkt: dict):
        if not pkt or "invalid" in pkt:
            return
        payload = pkt.get("payload", b"")
        if len(payload) != 8:
            return
        try:
            ts, state, startup_step, counter = struct.unpack('<IBBH', payload)
            self._mark_heartbeat_seen(ts, state, startup_step, counter)
        except struct.error:
            pass

    def _on_handshake_ack_packet(self, pkt: dict):
        if not pkt or "invalid" in pkt:
            return
        payload = pkt.get("payload", b"")
        if len(payload) != 6:
            return
        try:
            ts, state, status = struct.unpack('<IBB', payload)
            self.handshake_acked = True
            self.handshake_status.emit(True, f"ACK ts={ts} state={state} status={status}")
        except struct.error:
            pass

    def _on_nack_packet(self, pkt: dict):
        if not pkt or "invalid" in pkt:
            return
        payload = pkt.get("payload", b"")
        if len(payload) != 5:
            return
        try:
            ts, state = struct.unpack('<IB', payload)
            self.handshake_status.emit(False, f"NACK ts={ts} state={state}")
        except struct.error:
            pass

    def _send_raw(self, msg_type: int, payload: bytes = b""):
        """
        Route a raw frame through whichever transport is active.
        Silently no-ops in camera-only mode.
        """
        if self.camera_only:
            return

        if self.mcu:
            try:
                self.mcu.send_frame(msg_type, payload)
            except Exception as e:
                print("CommsManager: MCU send_frame error:", e)
            return

        if not self._ser or not self._ser.is_open:
            print("CommsManager: serial port not open for raw send")
            return

        seq    = self.seq_counter % 256
        header = struct.pack('BBBB', HEADER_BYTE, msg_type, seq, len(payload))
        crc    = msg_type ^ seq
        for byte in payload:
            crc ^= byte
        packet = header + payload + struct.pack('B', crc)
        try:
            self._ser.write(packet)
            self.seq_counter += 1
        except Exception as e:
            print(f"CommsManager: serial write error: {e}")

    # ── Public send helpers ───────────────────────────────────────────────
    def send_handshake(
        self,
        heartbeat_ms: int = DEFAULT_HANDSHAKE_HEARTBEAT_MS,
        telemetry_ms: int = DEFAULT_HANDSHAKE_TELEMETRY_MS,
        send_ack: bool = True,
    ):
        self._enqueue_tx(
            "HANDSHAKE",
            self._send_handshake_now,
            int(heartbeat_ms),
            int(telemetry_ms),
            bool(send_ack),
        )

    def _send_handshake_now(self, heartbeat_ms: int, telemetry_ms: int, send_ack: bool):
        if self.mcu and hasattr(self.mcu, "send_handshake"):
            self.mcu.send_handshake(heartbeat_ms, telemetry_ms, send_ack)
            print(
                f"CommsManager: handshake sent "
                f"(heartbeat={heartbeat_ms} ms, telemetry={telemetry_ms} ms)"
            )
            return
        payload = struct.pack(
            '<HHB',
            int(heartbeat_ms) & 0xFFFF,
            int(telemetry_ms) & 0xFFFF,
            1 if send_ack else 0,
        )
        self._send_raw(0x10, payload)
        print(
            f"CommsManager: handshake sent (legacy, heartbeat={heartbeat_ms} ms, "
            f"telemetry={telemetry_ms} ms)"
        )

    def send_go_home(self, slave_addr=0x03):
        self._enqueue_tx("GO HOME", self._send_go_home_now, slave_addr)

    def _send_go_home_now(self, slave_addr=0x03):
        if self.camera_only:
            print("CommsManager: camera-only — GO HOME ignored")
            return
        if self.mcu and hasattr(self.mcu, "send_stepper_go_home"):
            try:
                self.mcu.send_stepper_go_home(int(slave_addr) & 0xFF)
                print("CommsManager: Command Sent via MCUComm: GO HOME")
                return
            except Exception as e:
                print("CommsManager: MCUComm send_stepper_go_home error:", e)
        payload = struct.pack('B', int(slave_addr) & 0xFF)
        self._send_raw(MSG_GO_HOME, payload)
        print("CommsManager: Command Sent (legacy): GO HOME")

    def send_set_middle(self):
        self._enqueue_tx("SET MIDDLE", self._send_set_middle_now)

    def _send_set_middle_now(self):
        if self.camera_only:
            print("CommsManager: camera-only — SET MIDDLE ignored")
            return
        if self.mcu and hasattr(self.mcu, "send_stepper_set_middle"):
            try:
                self.mcu.send_stepper_set_middle()
                print("CommsManager: Command Sent via MCUComm: SET MIDDLE")
                return
            except Exception as e:
                print("CommsManager: MCUComm send_stepper_set_middle error:", e)
        self._send_raw(MSG_SET_MIDDLE, b"")
        print("CommsManager: Command Sent (legacy): SET MIDDLE")

    def send_move_to(self, steps, slave_addr=0x03, speed=1000, acc=150):
        self._enqueue_tx("MOVE TO", self._send_move_to_now, steps, slave_addr, speed, acc)

    def _send_move_to_now(self, steps, slave_addr=0x03, speed=1000, acc=150):
        if self.camera_only:
            print("CommsManager: camera-only — MOVE TO ignored")
            return
        if self.mcu and hasattr(self.mcu, "send_stepper_move_to"):
            try:
                self.mcu.send_stepper_move_to(
                    int(steps), slave_addr=int(slave_addr),
                    speed=int(speed), acc=int(acc)
                )
                print(f"CommsManager: TX via MCUComm: Move To {int(steps)} steps")
                return
            except Exception as e:
                print("CommsManager: MCUComm send_stepper_move_to error:", e)
        payload = struct.pack('<i', int(steps))
        self._send_raw(MSG_POSITION_MODE2, payload)
        print(f"CommsManager: TX (legacy): Move To {int(steps)} steps")

    def send_desired_flow(self, ml_per_min: int, immediate: bool = False):
        self._enqueue_tx("DESIRED FLOW", self._send_desired_flow_now, ml_per_min, immediate)

    def _send_desired_flow_now(self, ml_per_min: int, immediate: bool = False):
        if self.camera_only:
            print("CommsManager: camera-only — DESIRED FLOW ignored")
            return
        if self.mcu and hasattr(self.mcu, "send_desired_flow"):
            try:
                if immediate and hasattr(self.mcu, "send_desired_flow_immediate"):
                    self.mcu.send_desired_flow_immediate(int(ml_per_min))
                else:
                    self.mcu.send_desired_flow(int(ml_per_min))
                return
            except Exception as e:
                print("CommsManager: error calling MCUComm send_desired_flow:", e)
        payload = struct.pack('<I', int(ml_per_min) & 0xFFFFFFFF)
        if immediate and MSG_DESIRED_FLOW_IMMEDIATE is not None:
            self._send_raw(MSG_DESIRED_FLOW_IMMEDIATE, payload)
        elif MSG_DESIRED_FLOW is not None:
            self._send_raw(MSG_DESIRED_FLOW, payload)
        else:
            self._send_raw(0x20, payload)  # last-resort original ID

    # ── Teardown ──────────────────────────────────────────────────────────
    @staticmethod
    def mm_to_steps(mm: float) -> int:
        return int(round(float(mm) * 1638.4))

    def send_stepper_oscillate_start(self, low_mm: float, high_mm: float):
        self._enqueue_tx(
            "OSCILLATE START",
            self._send_stepper_oscillate_start_now,
            low_mm,
            high_mm,
        )

    def _send_stepper_oscillate_start_now(self, low_mm: float, high_mm: float):
        if self.camera_only:
            print("CommsManager: camera-only - OSCILLATE START ignored")
            return
        if self.mcu and hasattr(self.mcu, "send_stepper_oscillate_start"):
            try:
                self.mcu.send_stepper_oscillate_start(float(low_mm), float(high_mm))
                return
            except Exception as e:
                print("CommsManager: MCUComm oscillate start error:", e)
        print(f"CommsManager: oscillate start requested ({low_mm:.1f}-{high_mm:.1f} mm)")

    def send_stepper_oscillate_stop(self):
        self._enqueue_tx("OSCILLATE STOP", self._send_stepper_oscillate_stop_now)

    def _send_stepper_oscillate_stop_now(self):
        if self.camera_only:
            return
        if self.mcu and hasattr(self.mcu, "send_stepper_oscillate_stop"):
            try:
                self.mcu.send_stepper_oscillate_stop()
                return
            except Exception as e:
                print("CommsManager: MCUComm oscillate stop error:", e)
        print("CommsManager: oscillate stop requested")

    def send_set_pump_pwm(self, duty: int):
        self._enqueue_tx("PUMP PWM", self._send_set_pump_pwm_now, duty)

    def _send_set_pump_pwm_now(self, duty: int):
        if self.camera_only:
            print("CommsManager: camera-only - PUMP PWM ignored")
            return
        duty = max(0, min(int(duty), 100))
        if self.mcu and hasattr(self.mcu, "send_set_pump_pwm"):
            try:
                self.mcu.send_set_pump_pwm(duty)
                return
            except Exception as e:
                print("CommsManager: MCUComm pump PWM error:", e)
        self._send_raw(0x44, struct.pack("B", duty))

    def close(self):
        self._tx_running = False
        if self._tx_thread is not None:
            try:
                self._tx_queue.put(None)
                self._tx_thread.join(timeout=1.0)
            except Exception:
                pass
            self._tx_thread = None

        if self.mcu:
            try:
                self.mcu.close()
            except Exception:
                pass
            self.mcu = None

        if self._fallback_listener:
            try:
                self._fallback_listener.stop()
            except Exception:
                pass
            self._fallback_listener = None

        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def get_mcu(self):
        """Expose underlying MCUComm instance for advanced use (None if not active)."""
        return self.mcu

    def is_camera_only(self) -> bool:
        """True if no controller was found and the app is running without motion/flow control."""
        return self.camera_only
