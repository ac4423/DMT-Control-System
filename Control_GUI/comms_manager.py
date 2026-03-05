# comms_manager.py
import sys
import struct
import serial
import time
from PyQt6.QtCore import QObject, pyqtSignal, QThread

# Try to import MCUComm driver (primary)
try:
    from mcu_comm.driver import MCUComm
    from mcu_comm.protocol import MSG_DESIRED_FLOW, MSG_DESIRED_FLOW_IMMEDIATE, MSG_TELEMETRY_PUSH as MSG_TELEMETRY
except Exception:
    MCUComm = None
    MSG_DESIRED_FLOW = None
    MSG_DESIRED_FLOW_IMMEDIATE = None
    # Keep a fallback numeric value for telemetry if driver import fails
    MSG_TELEMETRY = 0x03

# --- Configuration ---
if sys.platform.startswith('win'):
    SERIAL_PORT = "COM3"
else:
    SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 256000

# --- Protocol / legacy message IDs ---
HEADER_BYTE      = 0xA5
MSG_GO_HOME      = 0x41
MSG_SET_MIDDLE   = 0x42
MSG_POSITION_MODE2 = 0x43  # Move-to absolute (steps)


# ---------- Fallback legacy listener ----------
class CommsListener(QThread):
    """
    Legacy background thread that reads and parses frames directly from serial.
    Used as a fallback if MCUComm is not available, or when running in camera-only
    mode with a controller attached via raw serial.
    """
    telemetry_received = pyqtSignal(int, int, int, int, int)  # ts, state, flow, vol, pos

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

    def _decode_telemetry(self, payload):
        # 21 bytes: <I(Time) B(State) I(Flow) I(Vol) i(Pos) I(Rsv)
        if len(payload) != 21:
            return
        try:
            ts, state, flow, vol, pos, rsv = struct.unpack('<IBIIiI', payload)
            self.telemetry_received.emit(ts, state, flow, vol, pos)
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

    def __init__(self, port=SERIAL_PORT, baud=BAUD_RATE):
        super().__init__()
        self.port = port
        self.baud = baud

        self.mcu               = None
        self._fallback_listener = None
        self._ser              = None
        self.seq_counter       = 0
        self.camera_only       = False  # set True when no controller is reachable

        # ── Try MCUComm (primary) ──────────────────────────────────────────
        if MCUComm is not None:
            try:
                self.mcu = MCUComm(port=self.port, baud=self.baud, timeout=0.05)
                self.mcu.open()
                self.mcu.register_callback(MSG_TELEMETRY, self._on_mcu_packet)
                print(f"CommsManager: connected via MCUComm on {self.port} @ {self.baud}")
                return
            except Exception as e:
                print(f"CommsManager: MCUComm init failed, trying legacy serial: {e}")
                self.mcu = None

        # ── Try legacy raw serial + CommsListener (fallback) ──────────────
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.1)
            print(f"CommsManager: legacy serial connected on {self.port} @ {self.baud}")
            self._fallback_listener = CommsListener(self._ser)
            self._fallback_listener.telemetry_received.connect(self.telemetry_data)
            self._fallback_listener.start()
            return
        except serial.SerialException as e:
            print(f"CommsManager: legacy serial also failed: {e}")
            self._ser = None

        # ── Camera-only mode ───────────────────────────────────────────────
        # No controller found; GUI continues without telemetry or motion control.
        self.camera_only = True
        print(
            f"CommsManager Warning: no controller found on {self.port}. "
            "Camera-only mode active — motion/flow commands will be ignored."
        )

    # ── MCUComm callback ──────────────────────────────────────────────────
    def _on_mcu_packet(self, pkt: dict):
        """
        Called in MCUComm's reader thread. Decode telemetry and emit Qt signal.
        pyqtSignal.emit() is thread-safe.
        """
        if not pkt or "invalid" in pkt:
            return
        t       = pkt.get("type")
        payload = pkt.get("payload", b"")
        if t == MSG_TELEMETRY and len(payload) == 21:
            try:
                ts, state, flow, vol, pos, rsv = struct.unpack('<IBIIiI', payload)
                self.telemetry_data.emit(ts, state, flow, vol, pos)
            except struct.error:
                pass

    # ── Internal raw sender ───────────────────────────────────────────────
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
    def send_go_home(self, slave_addr=0x03):
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
    def close(self):
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