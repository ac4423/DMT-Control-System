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
