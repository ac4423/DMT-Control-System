# decode.py
import time
import logging
from mcu_comm.protocol import (
    MSG_ACK,
    MSG_NACK,
    MSG_HANDSHAKE_ACK,
    MSG_HEARTBEAT,
    MSG_TELEMETRY_PUSH,
    MSG_FLOWMETER_PULSE_DEBUG,
    u32_from_le,
)

logger = logging.getLogger(__name__)

STATE_NAMES = {
    0: "SYS_STARTUP_SEQUENCE",
    1: "SYS_PAIRING",
    2: "SYS_RUNNING_PI",
    3: "SYS_DEBUG",
    4: "SYS_STANDALONE_OPERATION",
    5: "SYS_ERROR_SHUTDOWN",
}

def format_hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def decode_and_show(pkt: dict, ui):
    """
    Decode a parsed packet dict produced by PacketParser and display in UI.
    pkt is either {'invalid': bytes} or {'type':.., 'seq':.., 'len':.., 'payload':.., 'crc':..}
    """
    try:
        if "invalid" in pkt:
            ui.inc_bad()
            ui.print_packet(f"[RX INVALID] {format_hex(pkt['invalid'])}")
            return

        msg_type = pkt["type"]
        payload = pkt["payload"]
        seq = pkt["seq"]

        ui.inc_packet()
        desc = f"TYPE=0x{msg_type:02X} SEQ={seq:03d} LEN={len(payload):03d}"

        if msg_type in (MSG_ACK, MSG_NACK, MSG_HANDSHAKE_ACK):
            if len(payload) >= 5:
                ts = u32_from_le(payload[0:4])
                st = payload[4]
                ui.update_state(st)
                desc += f" TS={ts} STATE={STATE_NAMES.get(st, st)}"
                if msg_type == MSG_HANDSHAKE_ACK:
                    ui.mark_handshake_ack()

        elif msg_type == MSG_HEARTBEAT:
            if len(payload) >= 8:
                ts = u32_from_le(payload[0:4])
                st = payload[4]
                startup_step = payload[5]
                ctr = payload[6] | (payload[7] << 8)

                ui.update_state(st)
                ui.mark_heartbeat()

                desc += f" TS={ts} STATE={STATE_NAMES.get(st, st)}"
                if st == 0:
                    desc += f" STARTUP_STEP={startup_step}"
                desc += f" HB_CTR={ctr}"

        elif msg_type == MSG_TELEMETRY_PUSH:
            if len(payload) >= 13:
                ts = u32_from_le(payload[0:4])
                st = payload[4]
                flow = u32_from_le(payload[5:9])
                total = u32_from_le(payload[9:13])

                ui.update_state(st)
                desc += f" TS={ts} STATE={STATE_NAMES.get(st, st)} FLOW={flow}mL/min TOTAL={total}mL"
        elif msg_type == MSG_FLOWMETER_PULSE_DEBUG:
            # payload expected: 9 bytes: [ts:u32][state:u8][pulse_total:u32]
            if len(payload) >= 9:
                ts = u32_from_le(payload[0:4])
                st = payload[4]
                pulse_total = u32_from_le(payload[5:9])

                ui.update_state(st)
                desc += f" TS={ts} STATE={STATE_NAMES.get(st, st)} PULSE_TOTAL={pulse_total}"
                ui.mark_heartbeat()  # optional: treat these as activity
            else:
                desc += " (malformed)"

        # Respect UI-specified packet-type suppression: do not print if filtered.
        try:
            if hasattr(ui, "is_packet_type_filtered") and ui.is_packet_type_filtered(msg_type):
                # do not display this packet type
                return
        except Exception:
            # on error, fall back to showing the packet to avoid silent loss
            pass

        ui.print_packet(f"[RX] {desc} | PAYLOAD: {format_hex(payload)}")

    except Exception:
        logger.exception("Error in decode_and_show")
        ui.print_packet("[ERR] decode_and_show exception (see log)")

