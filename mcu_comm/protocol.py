# mcu_comm/protocol.py
"""Protocol helpers: constants, CRC, frame builder, PacketParser.

This module intentionally focuses on byte-level framing logic and
lightweight parsing. Higher-level decoding (interpret fields in
payload) is left to the application (terminal/GUIs) so the driver
stays generic.
"""
from typing import Optional

COMMS_HDR = 0xA5
COMMS_MAX_PAYLOAD = 128

# Message types (keep in sync with MCU firmware)
MSG_ACK = 0x01
MSG_NACK = 0x02
MSG_TELEMETRY_PUSH = 0x03
MSG_HANDSHAKE = 0x10
MSG_CONFIG = 0x11
MSG_HANDSHAKE_ACK = 0x12
MSG_HEARTBEAT = 0x13
MSG_DESIRED_FLOW = 0x20
MSG_DESIRED_FLOW_IMMEDIATE = 0x21
# New application-level message code from MCU -> PC
MSG_FLOWMETER_PULSE_DEBUG = 0x32  # payload: [ts:u32][state:u8][pulse_total:u32]

# in mcu_comm/protocol.py (top-level constants)
MSG_GO_HOME = 0x41
MSG_SET_MIDDLE = 0x42
MSG_POSITION_MODE2 = 0x43


# New debug function codes (must match MCU values)
MSG_SET_PUMP_PWM = 0x30   # payload: [duty:1byte] - PC -> MCU
MSG_EXIT_SYS_DEBUG = 0x31 # payload: none          - PC -> MCU

def xor_crc(msg_type: int, seq: int, payload: bytes) -> int:
    c = msg_type ^ seq
    for b in payload:
        c ^= b
    return c & 0xFF


def build_frame(msg_type: int, seq: int, payload: bytes) -> bytes:
    length = len(payload)
    if length > COMMS_MAX_PAYLOAD:
        raise ValueError("Payload too long")
    crc = xor_crc(msg_type, seq, payload)
    return bytes([COMMS_HDR, msg_type, seq & 0xFF, length]) + payload + bytes([crc])


def u16_le(v: int) -> bytes:
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def u32_from_le(b: bytes) -> int:
    if len(b) < 4:
        raise ValueError("need 4 bytes")
    return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)

def u32_le(v: int) -> bytes:
    """Return 4-byte little-endian representation of unsigned 32-bit integer."""
    return bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])

class PacketParser:
    """A streaming parser for the simple framed protocol.

    Usage:
        p = PacketParser()
        for b in incoming_bytes:
            pkt = p.feed(b)
            if pkt is not None:
                # pkt is dict either {'type':..., 'seq':..., 'len':..., 'payload':..., 'crc':...}
                # or {'invalid': bytes}
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "IDLE"
        self.msg_type = 0
        self.seq = 0
        self.length = 0
        self.payload = bytearray()
        self.buffered = bytearray()

    def feed(self, b: int) -> Optional[dict]:
        # keep a running buffer for invalid packet reporting
        self.buffered.append(b)

        if self.state == "IDLE":
            if b == COMMS_HDR:
                self.state = "TYPE"
                self.buffered = bytearray([b])
            return None

        if self.state == "TYPE":
            self.msg_type = b
            self.state = "SEQ"
            return None

        if self.state == "SEQ":
            self.seq = b
            self.state = "LEN"
            return None

        if self.state == "LEN":
            self.length = b
            self.payload = bytearray()
            if self.length == 0:
                self.state = "CRC"
            elif self.length > COMMS_MAX_PAYLOAD:
                invalid = bytes(self.buffered)
                self.reset()
                return {"invalid": invalid}
            else:
                self.state = "PAYLOAD"
            return None

        if self.state == "PAYLOAD":
            self.payload.append(b)
            if len(self.payload) >= self.length:
                self.state = "CRC"
            return None

        if self.state == "CRC":
            crc_calc = xor_crc(self.msg_type, self.seq, bytes(self.payload))
            crc_recv = b
            if crc_calc == crc_recv:
                pkt = {
                    "type": self.msg_type,
                    "seq": self.seq,
                    "len": self.length,
                    "payload": bytes(self.payload),
                    "crc": crc_recv,
                }
            else:
                pkt = {"invalid": bytes(self.buffered)}
            self.reset()
            return pkt

        return None

# Config TLV tags (mirror STM32 config.h)
CONFIG_TAG_TELEMETRY_PERIOD_MS = 0x01
CONFIG_TAG_HEARTBEAT_PERIOD_MS = 0x02
CONFIG_TAG_PI_KP               = 0x03
CONFIG_TAG_PI_KI               = 0x04
CONFIG_TAG_ENABLE_PI_CONTROL   = 0x05

# --- add new TLV tags to mirror STM32 config.h ---
CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG = 0x06  # uint8_t (0/1)
CONFIG_TAG_SERIAL_SEND_MS          = 0x07  # uint16_t (ms)
CONFIG_TAG_PWM_DEBUG               = 0x08  # uint8_t (0/1)
CONFIG_TAG_ENABLE_ECHO_DEBUG       = 0x09  # uint8_t (0/1)

CONFIG_TAG_FLOW_WINDOW_MS          = 0x0A  # uint16_t (ms)
CONFIG_TAG_FLOW_PULSES_PER_LITRE   = 0x0B  # uint32_t
CONFIG_TAG_ENABLE_LOOKUP_TABLE     = 0x0C  # uint8_t (0/1)
CONFIG_TAG_PUMP_SAMPLE_TIME_MS     = 0x0D  # uint16_t (ms)

CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG = 0x0E  # uint8_t (0/1)

def build_tlv_field(tag: int, value: bytes) -> bytes:
    """
    Build a single TLV field: [tag][len][value...]
    - tag: 0..255
    - value: bytes object
    """
    if not (0 <= tag <= 0xFF):
        raise ValueError("tag out of range")
    if len(value) > 0xFF:
        raise ValueError("value too long for single TLV field")
    return bytes([tag, len(value)]) + value


def build_config_payload(fields: list) -> bytes:
    """
    Build a MSG_CONFIG payload by concatenating TLV fields.

    fields: iterable of (tag:int, value:bytes)
    returns: bytes (payload)
    """
    out = bytearray()
    for tag, val in fields:
        out += build_tlv_field(tag, bytes(val))
    if len(out) > COMMS_MAX_PAYLOAD:
        raise ValueError("config payload too long")
    return bytes(out)

# Human-readable TLV tag info (used by CLI / tooling)
# tag -> (name, length_expected, human_type)
TLV_TAG_INFO = {
    CONFIG_TAG_TELEMETRY_PERIOD_MS: ("telemetry_period_ms", 2, "uint16_t (ms)"),
    CONFIG_TAG_HEARTBEAT_PERIOD_MS: ("heartbeat_period_ms", 2, "uint16_t (ms)"),
    CONFIG_TAG_PI_KP: ("Pump_Control.kp", 4, "float"),
    CONFIG_TAG_PI_KI: ("Pump_Control.ki", 4, "float"),
    CONFIG_TAG_ENABLE_PI_CONTROL: ("pi_control_enabled", 1, "uint8_t (0/1)"),

    CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG: ("enable_usb_serial_debug", 1, "uint8_t (0/1)"),
    CONFIG_TAG_SERIAL_SEND_MS: ("serial_send_ms", 2, "uint16_t (ms)"),
    CONFIG_TAG_PWM_DEBUG: ("pwm_debug", 1, "uint8_t (0/1)"),
    CONFIG_TAG_ENABLE_ECHO_DEBUG: ("enable_echo_debug", 1, "uint8_t (0/1)"),

    CONFIG_TAG_FLOW_WINDOW_MS: ("flow_window_ms", 2, "uint16_t (ms)"),
    CONFIG_TAG_FLOW_PULSES_PER_LITRE: ("flow_pulses_per_litre", 4, "uint32_t"),
    CONFIG_TAG_ENABLE_LOOKUP_TABLE: ("enable_lookup_table", 1, "uint8_t (0/1)"),
    CONFIG_TAG_PUMP_SAMPLE_TIME_MS: ("pump_sample_time_ms", 2, "uint16_t (ms)"),

    # newly added tag:
    CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG: ("flowmeter_pulse_send_debug_enabled", 1, "uint8_t (0/1)"),
}

def tag_name_to_tag(name: str) -> int:
    """Return numeric tag for a human-readable tag name. Raises KeyError if unknown."""
    for t, info in TLV_TAG_INFO.items():
        if info[0] == name:
            return t
    raise KeyError(name)

# --- telemetry format (new fixed length) ---
TELEMETRY_LEN = 21  # [ts:u32][state:u8][flow1:u32][total1:u32][flow2:u32][total2:u32]

def decode_telemetry(payload: bytes) -> dict:
    """
    Decode telemetry payload (expected 21 bytes).
    Returns dict:
      { 'ts': int,
        'state': int,
        'flow1': int,   # mL/min
        'total1': int,  # mL
        'flow2': int,   # mL/min (secondary)
        'total2': int,  # mL (secondary)
      }
    Raises ValueError on wrong length.
    """
    if len(payload) != TELEMETRY_LEN:
        raise ValueError(f"Telemetry payload must be {TELEMETRY_LEN} bytes, got {len(payload)}")

    # little-endian reads
    ts = u32_from_le(payload[0:4])
    state = payload[4]
    flow1 = u32_from_le(payload[5:9])
    total1 = u32_from_le(payload[9:13])
    flow2 = u32_from_le(payload[13:17])
    total2 = u32_from_le(payload[17:21])

    return {
        "ts": ts,
        "state": state,
        "flow1": flow1,
        "total1": total1,
        "flow2": flow2,
        "total2": total2,
    }