import serial
import time
import struct
from PyQt6.QtCore import QObject, pyqtSignal, QThread

# --- Configuration ---
# Update this if your Pi assigns a different port (e.g. /dev/ttyACM0)
SERIAL_PORT = "/dev/ttyUSB0" 
BAUD_RATE = 256000  # Updated to match STM32 1Mbps

# --- Protocol Definitions ---
HEADER_BYTE = 0xA5
MSG_TELEMETRY = 0x03
MSG_GO_HOME = 0x41
MSG_SET_MIDDLE = 0x42
MSG_POSITION_MODE2 = 0x43  # New command for absolute movement

class CommsListener(QThread):
    """
    Background thread to continuously read from Serial without freezing the GUI.
    """
    telemetry_received = pyqtSignal(int, int, int, int, int) # Time, State, Flow, Vol, Pos

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
                # 1. Wait for Header (0xA5)
                if self.ser.in_waiting > 0:
                    byte = self.ser.read(1)
                    if byte == b'\xA5':
                        self._parse_packet()
                else:
                    self.msleep(1) # Prevent CPU hogging
            except Exception as e:
                print(f"Serial Read Error: {e}")
                self.msleep(100)

    def _parse_packet(self):
        # We already read Header (0xA5).
        # Need: TYPE(1) + SEQ(1) + LEN(1)
        header_rem = self.ser.read(3)
        if len(header_rem) < 3: return

        msg_type, seq, payload_len = struct.unpack('BBB', header_rem)

        # Read Payload + CRC
        data = self.ser.read(payload_len + 1)
        if len(data) < payload_len + 1: return

        payload = data[:-1]
        received_crc = data[-1]

        # CRC Check: XOR(Type, Seq, Payload...)
        calc_crc = msg_type ^ seq
        for b in payload:
            calc_crc ^= b
        
        if calc_crc != received_crc:
            print("CRC Mismatch! Dropping packet.")
            return

        # Handle Telemetry Packet (0x03)
        if msg_type == MSG_TELEMETRY:
            self._decode_telemetry(payload)

    def _decode_telemetry(self, payload):
        # Payload size must be 21 bytes based on your STM32 code
        if len(payload) != 21: 
            return

        # Format: < I(Time) B(State) I(Flow) I(Vol) i(Pos) I(Rsv)
        # i = int32 (signed) for position
        try:
            ts, state, flow, vol, pos, rsv = struct.unpack('<IBIIiI', payload)
            self.telemetry_received.emit(ts, state, flow, vol, pos)
        except struct.error:
            pass

    def stop(self):
        self.running = False
        self.wait()


class CommsManager(QObject):
    # Re-emit signal for Main Window
    telemetry_data = pyqtSignal(int, int, int, int, int)

    def __init__(self, port=SERIAL_PORT, baud=BAUD_RATE):
        super().__init__()
        self.ser = None
        self.seq_counter = 0
        
        try:
            self.ser = serial.Serial(port, baud, timeout=0.1)
            print(f"Connected to {port} at {baud} baud.")
            
            # Start Listening Thread
            self.listener = CommsListener(self.ser)
            self.listener.telemetry_received.connect(self.telemetry_data)
            self.listener.start()

        except serial.SerialException as e:
            print(f"Error opening serial port: {e}")

    def _send_frame(self, msg_type, payload=b""):
        if not self.ser or not self.ser.is_open:
            return

        seq = self.seq_counter % 256
        length = len(payload)
        
        # 1. Build Header: HDR, TYPE, SEQ, LEN
        header = struct.pack('BBBB', HEADER_BYTE, msg_type, seq, length)
        
        # 2. Calculate CRC
        crc = msg_type ^ seq
        for byte in payload:
            crc ^= byte
            
        # 3. Construct final packet
        packet = header + payload + struct.pack('B', crc)
        
        try:
            self.ser.write(packet)
            self.seq_counter += 1
        except Exception as e:
            print(f"Serial write error: {e}")

    def send_go_home(self, slave_addr=0x03):
        """
        Sends MSG_GO_HOME (0x41). Payload: [SlaveAddr]
        """
        payload = struct.pack('B', slave_addr)
        self._send_frame(MSG_GO_HOME, payload)
        print("Command Sent: GO HOME")

    def send_set_middle(self):
        """
        Sends MSG_SET_MIDDLE (0x42). Payload: None
        """
        # Simple command with no payload, matching MCU implementation
        self._send_frame(MSG_SET_MIDDLE, b"")
        print("Command Sent: SET MIDDLE")

    def send_move_to(self, steps, slave_addr=0x03, speed=1000, acc=150):
        """
        Sends MSG_POSITION_MODE2 (0x43).
        Payload Structure (Updated to 4 bytes):
          - Steps (4 bytes, int32)
        
        Note: slave_addr, speed, and acc are ignored/hardcoded in the firmware now,
        so we do not send them.
        """
        # Pack Little Endian (<), i=Int32 (4 bytes)
        payload = struct.pack('<i', int(steps))
        
        self._send_frame(MSG_POSITION_MODE2, payload)
        print(f"TX: Move To {int(steps)} steps")

    def close(self):
        if hasattr(self, 'listener'):
            self.listener.stop()
        if self.ser and self.ser.is_open:
            self.ser.close()