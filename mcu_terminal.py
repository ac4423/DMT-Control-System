#!/usr/bin/env python3
"""Terminal UI using mcu_comm.MCUComm

Small, curses-free terminal UI. Keyboard shortcuts:
- H: send handshake
- Q: quit
- 1/2: send emulated stepper packets (development)

The UI remains single-threaded for drawing; driver receives packets in background
and calls back into the UI safely.
"""
import argparse
import sys
import threading
import time
import termios
import tty
import select
import logging

from mcu_comm.driver import MCUComm
from mcu_comm.protocol import MSG_ACK, MSG_NACK, MSG_HANDSHAKE_ACK, MSG_HEARTBEAT, MSG_TELEMETRY_PUSH
from mcu_comm.protocol import u32_from_le

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATE_NAMES = {
    0: "SYS_STARTUP_SEQUENCE",
    1: "SYS_PAIRING",
    2: "SYS_RUNNING_PI",
    3: "SYS_STANDALONE_OPERATION",
    4: "SYS_ERROR_SHUTDOWN",
}


class TerminalUI:
    def __init__(self):
        self._lock = threading.Lock()
        self.last_state = None
        self.last_state_name = "UNKNOWN"
        self.last_heartbeat_time = None
        self.last_handshake_ack_time = None
        self.packet_count = 0
        self.bad_packets = 0
        self._lines = []
        self.running = True

    def clear(self):
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
                f" | Keys: [H]=Handshake [Q]=Quit"
            )
            sys.stdout.write("\033[H\033[2K" + line[:120] + "\n")
            sys.stdout.flush()

    def print_line(self, text: str):
        with self._lock:
            # keep last N lines
            self._lines.append(text)
            if len(self._lines) > 10:
                self._lines.pop(0)
            # print lines at bottom
            sys.stdout.write("\033[s")
            # write starting at row 2
            row = 2
            for l in self._lines:
                sys.stdout.write(f"\033[{row};1H\033[2K" + l + "\n")
                row += 1
            sys.stdout.write("\033[u")
            sys.stdout.flush()

    # event methods called from driver callbacks
    def inc_packet(self):
        with self._lock:
            self.packet_count += 1

    def inc_bad(self):
        with self._lock:
            self.bad_packets += 1

    def update_state(self, st: int):
        with self._lock:
            self.last_state = st
            self.last_state_name = STATE_NAMES.get(st, f"UNKNOWN({st})")

    def mark_heartbeat(self):
        with self._lock:
            self.last_heartbeat_time = time.time()

    def mark_handshake_ack(self):
        with self._lock:
            self.last_handshake_ack_time = time.time()


def format_hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def decode_and_show(pkt: dict, ui: TerminalUI):
    if "invalid" in pkt:
        ui.inc_bad()
        ui.print_line(f"[RX INVALID] {format_hex(pkt['invalid'])}")
        return
    msg_type = pkt['type']
    payload = pkt['payload']
    seq = pkt['seq']
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
        if len(payload) >= 7:
            ts = u32_from_le(payload[0:4])
            st = payload[4]
            startup_step = payload[5]
            ctr = payload[6]
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

    ui.print_line(f"[RX] {desc} | PAYLOAD: {format_hex(payload)}")


def keyboard_loop(ui: TerminalUI, comm: MCUComm, hb_ms: int, tel_ms: int, send_ack: bool, extra_bytes: bytes, stop_event: threading.Event):
    old = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        seq = 0
        while not stop_event.is_set():
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not r:
                continue
            ch = sys.stdin.read(1)
            if not ch:
                continue
            ch = ch.lower()
            if ch == 'q':
                stop_event.set()
                ui.running = False
                return
            if ch == 'h':
                seq = comm.send_handshake(hb_ms, tel_ms, send_ack, extra_bytes)
                ui.print_line(f"[TX] HANDSHAKE SEQ={seq} HB={hb_ms}ms TEL={tel_ms}ms ACKFLAG={send_ack} EXTRA={format_hex(extra_bytes)}")
            elif ch == '1':
                pkt = comm.build_raw_stepper_gohome_ack()
                with comm._lock:
                    # direct low-level write for dev emulation
                    if comm._ser:
                        comm._ser.write(pkt)
                ui.print_line(f"[TX] Stepper GoHome Ack: {format_hex(pkt)}")
            elif ch == '2':
                pkt = comm.build_raw_stepper_setzero_ack()
                with comm._lock:
                    if comm._ser:
                        comm._ser.write(pkt)
                ui.print_line(f"[TX] Stepper SetZero Ack: {format_hex(pkt)}")
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)


def main():
    parser = argparse.ArgumentParser(description="MCU Serial Monitor")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--hb", type=int, default=500)
    parser.add_argument("--tel", type=int, default=1000)
    parser.add_argument("--send-ack", type=int, default=1)
    parser.add_argument("--extra", default="")
    args = parser.parse_args()

    extra_bytes = bytes.fromhex(args.extra) if args.extra else b""

    ui = TerminalUI()
    ui.clear()
    ui.draw_status_bar()

    stop_event = threading.Event()

    comm = MCUComm(args.port, args.baud)
    try:
        comm.open()
    except Exception as e:
        logger.exception("failed to open serial port")
        sys.exit(1)

    # register packet callback
    comm.register_callback(None, lambda pkt: decode_and_show(pkt, ui))

    kb = threading.Thread(target=keyboard_loop, args=(ui, comm, args.hb, args.tel, bool(args.send_ack), extra_bytes, stop_event), daemon=True)
    kb.start()

    try:
        last_refresh = 0
        while ui.running and not stop_event.is_set():
            now = time.time()
            if now - last_refresh >= 0.2:
                ui.draw_status_bar()
                last_refresh = now
            time.sleep(0.01)
    finally:
        stop_event.set()
        ui.running = False
        kb.join(timeout=1.0)
        comm.close()
        sys.stdout.write("\033[0m\033[r\n")
        sys.stdout.flush()


if __name__ == '__main__':
    main()
