# mcu_comm/protocol.py
"""Protocol helpers: constants, CRC, frame builder, PacketParser, config TLV, telemetry decoder.

Responsibilities:
- Framing constants and message type IDs
- CRC calculation and frame construction
- Streaming PacketParser
- Config TLV tag definitions, builders, and metadata
- Telemetry payload decoder

Higher-level application logic (routing, state machines) stays in driver.py and above.
"""
from typing import Optional


# ── Framing ───────────────────────────────────────────────────────────────────

COMMS_HDR         = 0xA5
COMMS_MAX_PAYLOAD = 128


# ── Message type IDs (keep in sync with MCU firmware) ────────────────────────

# Core protocol
MSG_ACK           = 0x01
MSG_NACK          = 0x02
MSG_TELEMETRY_PUSH = 0x03
MSG_HANDSHAKE     = 0x10
MSG_CONFIG        = 0x11
MSG_HANDSHAKE_ACK = 0x12
MSG_HEARTBEAT     = 0x13

# Flow control (PC → MCU)
MSG_DESIRED_FLOW           = 0x20
MSG_DESIRED_FLOW_IMMEDIATE = 0x21

# Pump / debug control (PC → MCU)
MSG_SET_PUMP_PWM   = 0x30   # payload: [duty: u8]
MSG_EXIT_SYS_DEBUG = 0x31   # payload: none

# Flowmeter debug (MCU → PC)
MSG_FLOWMETER_PULSE_DEBUG = 0x32  # payload: [ts: u32][state: u8][pulse_total: u32]

# Stepper motor (PC → MCU)
MSG_GO_HOME        = 0x41
MSG_SET_MIDDLE     = 0x42
MSG_POSITION_MODE2 = 0x43   # Move to absolute position (steps)


# ── CRC and framing helpers ───────────────────────────────────────────────────

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


# ── Integer encoding helpers ──────────────────────────────────────────────────

def u16_le(v: int) -> bytes:
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def u32_le(v: int) -> bytes:
    """Return 4-byte little-endian representation of an unsigned 32-bit integer."""
    return bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])


def u32_from_le(b: bytes) -> int:
    if len(b) < 4:
        raise ValueError("need 4 bytes")
    return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)


# ── PacketParser ──────────────────────────────────────────────────────────────

class PacketParser:
    """Streaming byte-by-byte parser for the framed MCU protocol.

    Usage:
        p = PacketParser()
        for b in incoming_bytes:
            pkt = p.feed(b)
            if pkt is not None:
                # valid:   {'type': int, 'seq': int, 'len': int, 'payload': bytes, 'crc': int}
                # invalid: {'invalid': bytes}   — raw bytes of the rejected frame
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.state    = "IDLE"
        self.msg_type = 0
        self.seq      = 0
        self.length   = 0
        self.payload  = bytearray()
        self.buffered = bytearray()

    def feed(self, b: int) -> Optional[dict]:
        self.buffered.append(b)

        if self.state == "IDLE":
            if b == COMMS_HDR:
                self.state    = "TYPE"
                self.buffered = bytearray([b])
            return None

        if self.state == "TYPE":
            self.msg_type = b
            self.state    = "SEQ"
            return None

        if self.state == "SEQ":
            self.seq   = b
            self.state = "LEN"
            return None

        if self.state == "LEN":
            self.length  = b
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
            if crc_calc == b:
                pkt = {
                    "type":    self.msg_type,
                    "seq":     self.seq,
                    "len":     self.length,
                    "payload": bytes(self.payload),
                    "crc":     b,
                }
            else:
                pkt = {"invalid": bytes(self.buffered)}
            self.reset()
            return pkt

        return None


# ── Config TLV tag definitions (mirror STM32 config.h) ───────────────────────

CONFIG_TAG_TELEMETRY_PERIOD_MS     = 0x01  # uint16_t  ms
CONFIG_TAG_HEARTBEAT_PERIOD_MS     = 0x02  # uint16_t  ms
CONFIG_TAG_PI_KP                   = 0x03  # float
CONFIG_TAG_PI_KI                   = 0x04  # float
CONFIG_TAG_ENABLE_PI_CONTROL       = 0x05  # uint8_t   0/1

CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG = 0x06  # uint8_t   0/1
CONFIG_TAG_SERIAL_SEND_MS          = 0x07  # uint16_t  ms
CONFIG_TAG_PWM_DEBUG               = 0x08  # uint8_t   0/1
CONFIG_TAG_ENABLE_ECHO_DEBUG       = 0x09  # uint8_t   0/1

CONFIG_TAG_FLOW_WINDOW_MS          = 0x0A  # uint16_t  ms
CONFIG_TAG_FLOW_PULSES_PER_LITRE   = 0x0B  # uint32_t
CONFIG_TAG_ENABLE_LOOKUP_TABLE     = 0x0C  # uint8_t   0/1
CONFIG_TAG_PUMP_SAMPLE_TIME_MS     = 0x0D  # uint16_t  ms

CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG = 0x0E  # uint8_t  0/1


# ── Config TLV builders ───────────────────────────────────────────────────────

def build_tlv_field(tag: int, value: bytes) -> bytes:
    """Build a single TLV field: [tag: u8][len: u8][value: bytes]."""
    if not (0 <= tag <= 0xFF):
        raise ValueError("tag out of range")
    if len(value) > 0xFF:
        raise ValueError("value too long for single TLV field")
    return bytes([tag, len(value)]) + value


def build_config_payload(fields: list) -> bytes:
    """
    Build a MSG_CONFIG payload by concatenating TLV fields.

    fields: iterable of (tag: int, value: bytes)
    Returns: bytes payload ready to pass to build_frame / send_frame.
    Raises ValueError if the resulting payload exceeds COMMS_MAX_PAYLOAD.
    """
    out = bytearray()
    for tag, val in fields:
        out += build_tlv_field(tag, bytes(val))
    if len(out) > COMMS_MAX_PAYLOAD:
        raise ValueError("config payload too long")
    return bytes(out)


# ── TLV metadata (used by CLI / tooling) ──────────────────────────────────────

# tag → (field_name, expected_length_bytes, human_type_description)
TLV_TAG_INFO = {
    CONFIG_TAG_TELEMETRY_PERIOD_MS:     ("telemetry_period_ms",             2, "uint16_t (ms)"),
    CONFIG_TAG_HEARTBEAT_PERIOD_MS:     ("heartbeat_period_ms",             2, "uint16_t (ms)"),
    CONFIG_TAG_PI_KP:                   ("Pump_Control.kp",                 4, "float"),
    CONFIG_TAG_PI_KI:                   ("Pump_Control.ki",                 4, "float"),
    CONFIG_TAG_ENABLE_PI_CONTROL:       ("pi_control_enabled",              1, "uint8_t (0/1)"),
    CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG: ("enable_usb_serial_debug",         1, "uint8_t (0/1)"),
    CONFIG_TAG_SERIAL_SEND_MS:          ("serial_send_ms",                  2, "uint16_t (ms)"),
    CONFIG_TAG_PWM_DEBUG:               ("pwm_debug",                       1, "uint8_t (0/1)"),
    CONFIG_TAG_ENABLE_ECHO_DEBUG:       ("enable_echo_debug",               1, "uint8_t (0/1)"),
    CONFIG_TAG_FLOW_WINDOW_MS:          ("flow_window_ms",                  2, "uint16_t (ms)"),
    CONFIG_TAG_FLOW_PULSES_PER_LITRE:   ("flow_pulses_per_litre",           4, "uint32_t"),
    CONFIG_TAG_ENABLE_LOOKUP_TABLE:     ("enable_lookup_table",             1, "uint8_t (0/1)"),
    CONFIG_TAG_PUMP_SAMPLE_TIME_MS:     ("pump_sample_time_ms",             2, "uint16_t (ms)"),
    CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG: ("flowmeter_pulse_send_debug_enabled", 1, "uint8_t (0/1)"),
}


def tag_name_to_tag(name: str) -> int:
    """Return the numeric tag for a human-readable field name. Raises KeyError if unknown."""
    for t, info in TLV_TAG_INFO.items():
        if info[0] == name:
            return t
    raise KeyError(name)


# ── Telemetry decoder ─────────────────────────────────────────────────────────

TELEMETRY_LEN = 21  # [ts: u32][state: u8][flow1: u32][total1: u32][flow2: u32][total2: u32]


def decode_telemetry(payload: bytes) -> dict:
    """
    Decode a MSG_TELEMETRY_PUSH payload (must be exactly TELEMETRY_LEN bytes).

    Returns:
        {
            'ts':     int,   # timestamp (ms, MCU uptime)
            'state':  int,   # MCU state enum value
            'flow1':  int,   # primary flow rate   (mL/min)
            'total1': int,   # primary total volume (mL)
            'flow2':  int,   # secondary flow rate  (mL/min)
            'total2': int,   # secondary total volume (mL)
        }

    Raises ValueError if the payload length is wrong.
    """
    if len(payload) != TELEMETRY_LEN:
        raise ValueError(
            f"Telemetry payload must be {TELEMETRY_LEN} bytes, got {len(payload)}"
        )

    ts     = u32_from_le(payload[0:4])
    state  = payload[4]
    flow1  = u32_from_le(payload[5:9])
    total1 = u32_from_le(payload[9:13])
    flow2  = u32_from_le(payload[13:17])
    total2 = u32_from_le(payload[17:21])

    return {
        "ts":     ts,
        "state":  state,
        "flow1":  flow1,
        "total1": total1,
        "flow2":  flow2,
        "total2": total2,
    }