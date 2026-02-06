#!/usr/bin/env python3
import serial
import time
import argparse
import sys
import select
import termios
import tty
import threading
import signal

COMMS_HDR = 0xA5
COMMS_MAX_PAYLOAD = 128

# Message types (from your firmware)
MSG_ACK = 0x01
MSG_NACK = 0x02
MSG_TELEMETRY_PUSH = 0x03
MSG_HANDSHAKE = 0x10
MSG_CONFIG = 0x11
MSG_HANDSHAKE_ACK = 0x12
MSG_HEARTBEAT = 0x13
MSG_DESIRED_FLOW = 0x20
MSG_DESIRED_FLOW_IMMEDIATE = 0x21

STATE_NAMES = {
    0: "SYS_STARTUP_SEQUENCE",
    1: "SYS_PAIRING",
    2: "SYS_RUNNING_PI",
    3: "SYS_STANDALONE_OPERATION",
    4: "SYS_ERROR_SHUTDOWN",
}


def xor_crc(msg_type, seq, payload: bytes):
    c = msg_type ^ seq
    for b in payload:
        c ^= b
    return c & 0xFF


def build_frame(msg_type, seq, payload: bytes):
    length = len(payload)
    if length > COMMS_MAX_PAYLOAD:
        raise ValueError("Payload too long")

    crc = xor_crc(msg_type, seq, payload)
    return bytes([COMMS_HDR, msg_type, seq, length]) + payload + bytes([crc])


def u16_le(v):
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def u32_from_le(b):
    return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)


class PacketParser:
    def __init__(self):
        self.reset()

    def reset(self):
        self.state = "IDLE"
        self.msg_type = 0
        self.seq = 0
        self.length = 0
        self.payload = bytearray()
        self.buffered_bytes = bytearray()  # collect bytes for invalid data

    def feed(self, b):
        self.buffered_bytes.append(b)

        if self.state == "IDLE":
            if b == COMMS_HDR:
                self.state = "TYPE"
                self.buffered_bytes = bytearray([b])
        elif self.state == "TYPE":
            self.msg_type = b
            self.state = "SEQ"
        elif self.state == "SEQ":
            self.seq = b
            self.state = "LEN"
        elif self.state == "LEN":
            self.length = b
            self.payload = bytearray()
            if self.length == 0:
                self.state = "CRC"
            elif self.length > COMMS_MAX_PAYLOAD:
                # invalid payload length
                invalid_data = bytes(self.buffered_bytes)
                self.reset()
                return {"invalid": invalid_data}
            else:
                self.state = "PAYLOAD"
        elif self.state == "PAYLOAD":
            self.payload.append(b)
            if len(self.payload) >= self.length:
                self.state = "CRC"
        elif self.state == "CRC":
            crc_calc = xor_crc(self.msg_type, self.seq, self.payload)
            crc_recv = b
            pkt = None

            if crc_calc == crc_recv:
                pkt = {
                    "type": self.msg_type,
                    "seq": self.seq,
                    "len": self.length,
                    "payload": bytes(self.payload),
                    "crc": crc_recv,
                }
            else:
                # CRC mismatch, report invalid
                pkt = {"invalid": bytes(self.buffered_bytes)}

            self.reset()
            return pkt

        return None


class TerminalUI:
    def __init__(self):
        self.last_state = None
        self.last_state_name = "UNKNOWN"
        self.last_heartbeat_time = None
        self.last_handshake_ack_time = None
        self.packet_count = 0
        self.bad_packets = 0
        self.running = True

        self._lock = threading.Lock()

    def clear_screen(self):
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

    def draw_status_bar(self):
        with self._lock:
            now = time.time()

            hb_age = "N/A"
            if self.last_heartbeat_time is not None:
                hb_age = f"{now - self.last_heartbeat_time:.2f}s ago"

            hs_age = "N/A"
            if self.last_handshake_ack_time is not None:
                hs_age = f"{now - self.last_handshake_ack_time:.2f}s ago"

            line = (
                f" MCU STATE: {self.last_state_name:<28}"
                f" | Last HB: {hb_age:<12}"
                f" | Last HS_ACK: {hs_age:<12}"
                f" | Packets: {self.packet_count:<6}"
                f" | Bad: {self.bad_packets:<4}"
                f" | Keys: [H]=Handshake [Q]=Quit "
            )

            sys.stdout.write("\033[H\033[2K" + line[:120] + "\n")
            sys.stdout.flush()

    def print_packet_line(self, text):
        with self._lock:
            sys.stdout.write("\033[s\033[2;1H\033[2;999r\033[999;1H" + text + "\n\033[u")
            sys.stdout.flush()

    def update_state(self, state_byte):
        with self._lock:
            self.last_state = state_byte
            self.last_state_name = STATE_NAMES.get(state_byte, f"UNKNOWN({state_byte})")

    def mark_heartbeat(self):
        with self._lock:
            self.last_heartbeat_time = time.time()

    def mark_handshake_ack(self):
        with self._lock:
            self.last_handshake_ack_time = time.time()

    def inc_packet(self):
        with self._lock:
            self.packet_count += 1

    def inc_bad(self):
        with self._lock:
            self.bad_packets += 1


def format_hex(b: bytes):
    return " ".join(f"{x:02X}" for x in b)


def decode_packet(pkt, ui: TerminalUI):
    if "invalid" in pkt:
        ui.inc_bad()
        return f"[RX INVALID] {format_hex(pkt['invalid'])}"

    msg_type = pkt["type"]
    seq = pkt["seq"]
    payload = pkt["payload"]

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
        if len(payload) >= 6:
            ts = u32_from_le(payload[0:4])
            st = payload[4]
            ctr = payload[5]
            ui.update_state(st)
            ui.mark_heartbeat()
            desc += f" TS={ts} STATE={STATE_NAMES.get(st, st)} HB_CTR={ctr}"

    elif msg_type == MSG_TELEMETRY_PUSH:
        if len(payload) >= 13:
            ts = u32_from_le(payload[0:4])
            st = payload[4]
            flow = u32_from_le(payload[5:9])
            total = u32_from_le(payload[9:13])
            ui.update_state(st)
            desc += f" TS={ts} STATE={STATE_NAMES.get(st, st)} FLOW={flow}mL/min TOTAL={total}mL"

    return f"[RX] {desc} | PAYLOAD: {format_hex(payload)}"


def keyboard_thread(ui: TerminalUI, ser: serial.Serial, hb_ms, tel_ms, send_ack, extra_bytes, stop_event):
    seq = 0
    old_settings = termios.tcgetattr(sys.stdin)

    try:
        tty.setcbreak(sys.stdin.fileno())

        while not stop_event.is_set():
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not r:
                continue

            ch = sys.stdin.read(1)
            if not ch:
                continue

            ch = ch.lower()

            if ch == "q":
                stop_event.set()
                ui.running = False
                return

            if ch == "h":
                payload = bytearray()
                payload += u16_le(hb_ms)
                payload += u16_le(tel_ms)
                payload.append(1 if send_ack else 0)

                if extra_bytes:
                    payload += extra_bytes

                frame = build_frame(MSG_HANDSHAKE, seq, payload)
                ser.write(frame)

                ui.print_packet_line(
                    f"[TX] HANDSHAKE SEQ={seq} HB={hb_ms}ms TEL={tel_ms}ms ACKFLAG={send_ack} EXTRA={format_hex(extra_bytes)}"
                )

                seq = (seq + 1) & 0xFF

    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


def main():
    parser = argparse.ArgumentParser(description="MCU Serial Monitor with Handshake Trigger (press H)")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--hb", type=int, default=500)
    parser.add_argument("--tel", type=int, default=1000)
    parser.add_argument("--send-ack", type=int, default=1)
    parser.add_argument("--extra", default="")

    args = parser.parse_args()

    extra_bytes = bytes.fromhex(args.extra) if args.extra else b""

    ser = serial.Serial(args.port, args.baud, timeout=0.01)

    ui = TerminalUI()
    ui.clear_screen()
    ui.draw_status_bar()

    stop_event = threading.Event()
    kb = threading.Thread(
        target=keyboard_thread,
        args=(ui, ser, args.hb, args.tel, args.send_ack, extra_bytes, stop_event),
        daemon=True
    )
    kb.start()

    parser_obj = PacketParser()
    last_status_refresh = 0

    def sigint_handler(sig, frame):
        stop_event.set()
        ui.running = False

    signal.signal(signal.SIGINT, sigint_handler)

    try:
        while ui.running and not stop_event.is_set():
            data = ser.read(256)
            if data:
                for b in data:
                    pkt = parser_obj.feed(b)
                    if pkt is not None:
                        if "invalid" in pkt:
                            ui.inc_bad()
                            line = f"[RX INVALID] {format_hex(pkt['invalid'])}"
                        else:
                            ui.inc_packet()
                            line = decode_packet(pkt, ui)
                        ui.print_packet_line(line)

            now = time.time()
            if now - last_status_refresh > 0.2:
                ui.draw_status_bar()
                last_status_refresh = now

            time.sleep(0.001)

    finally:
        stop_event.set()
        ui.running = False
        kb.join(timeout=1.0)
        ser.close()
        sys.stdout.write("\033[0m\033[r\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

