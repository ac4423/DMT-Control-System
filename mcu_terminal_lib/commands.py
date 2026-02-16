from __future__ import annotations

import argparse
import shlex
import logging
from typing import TYPE_CHECKING

from mcu_terminal_lib.decode import format_hex

if TYPE_CHECKING:
    from mcu_comm.driver import MCUComm
    import threading

# commands.py

logger = logging.getLogger(__name__)


class CommandProcessor:
    def __init__(self, comm: MCUComm, ui, defaults: dict, stop_event: 'threading.Event'):
        self.comm = comm
        self.ui = ui
        self.defaults = defaults
        self.stop_event = stop_event

        self._hs_parser = argparse.ArgumentParser(prog="h", add_help=False)
        self._hs_parser.add_argument("--hb", type=int, help="heartbeat ms")
        self._hs_parser.add_argument("--tel", type=int, help="telemetry ms")
        self._hs_parser.add_argument("--send-ack", type=int, choices=[0, 1], help="send ack flag 0/1")
        self._hs_parser.add_argument("--extra", type=str, help="extra payload as hex string (no 0x)")

    def _parse_kv_args(self, tokens):
        if len(tokens) < 3:
            return None, None
        return tokens[1], tokens[2]

    def execute(self, line: str):
        try:
            line = line.strip()
            if not line:
                return

            try:
                tokens = shlex.split(line)
            except ValueError as e:
                self.ui.print_cmd(f"[CMD ERR] parse error: {e}")
                return

            cmd = tokens[0].lower()

            if cmd in ("q", "quit", "exit"):
                self.ui.print_cmd("[CMD] quitting...")
                self.stop_event.set()
                self.ui.running = False
                return

            if cmd == "help":
                self._show_help()
                return

            if cmd == "status":
                self._show_status()
                return

            if cmd == "set":
                key, val = self._parse_kv_args(tokens)
                if key is None:
                    self.ui.print_cmd("[CMD] usage: set <key> <value>")
                    return

                key = key.lower()

                if key in ("packet_lines", "packet-lines", "packets"):
                    try:
                        n = int(val)
                        self.ui.set_packet_lines(n)
                        self.ui.print_cmd(f"[CMD] packet_lines set to {n}")
                    except ValueError:
                        self.ui.print_cmd("[CMD ERR] packet_lines must be integer > 0")
                    return

                if key in ("cmd_lines", "cmd-lines", "commands"):
                    try:
                        n = int(val)
                        self.ui.set_cmd_lines(n)
                        self.ui.print_cmd(f"[CMD] cmd_lines set to {n}")
                    except ValueError:
                        self.ui.print_cmd("[CMD ERR] cmd_lines must be integer > 0")
                    return

                if key in ("hb", "heartbeat"):
                    try:
                        self.defaults["hb"] = int(val)
                    except ValueError:
                        self.ui.print_cmd("[CMD ERR] hb must be integer ms")
                        return

                elif key in ("tel", "telemetry"):
                    try:
                        self.defaults["tel"] = int(val)
                    except ValueError:
                        self.ui.print_cmd("[CMD ERR] tel must be integer ms")
                        return

                elif key in ("send-ack", "send_ack"):
                    self.defaults["send_ack"] = 1 if val not in ("0", "false", "False") else 0

                elif key == "extra":
                    try:
                        self.defaults["extra"] = bytes.fromhex(val) if val else b""
                    except ValueError:
                        self.ui.print_cmd("[CMD ERR] extra must be hex")
                        return

                elif key == "baud":
                    try:
                        self.defaults["baud"] = int(val)
                    except ValueError:
                        self.ui.print_cmd("[CMD ERR] baud must be integer")
                        return

                else:
                    self.ui.print_cmd(f"[CMD ERR] unknown key {key}")
                    return

                self.ui.print_cmd(f"[CMD] set {key} => {val}")
                return

            if cmd in ("h", "handshake"):
                try:
                    ns, unknown = self._hs_parser.parse_known_args(tokens[1:])
                except SystemExit:
                    self.ui.print_cmd("[CMD ERR] invalid handshake args")
                    return

                hb_ms = ns.hb if ns.hb is not None else self.defaults.get("hb")
                tel_ms = ns.tel if ns.tel is not None else self.defaults.get("tel")
                send_ack = ns.send_ack if ns.send_ack is not None else self.defaults.get("send_ack")

                if ns.extra is not None:
                    try:
                        extra = bytes.fromhex(ns.extra) if ns.extra else b""
                    except ValueError:
                        self.ui.print_cmd("[CMD ERR] extra hex invalid")
                        return
                else:
                    extra = self.defaults.get("extra", b"")

                try:
                    seq = self.comm.send_handshake(int(hb_ms), int(tel_ms), bool(send_ack), extra)
                    self.ui.print_cmd(
                        f"[TX] HANDSHAKE SEQ={seq} HB={hb_ms}ms TEL={tel_ms}ms "
                        f"ACKFLAG={send_ack} EXTRA={format_hex(extra)}"
                    )
                except Exception as e:
                    logger.exception("failed send handshake")
                    self.ui.print_cmd(f"[CMD ERR] handshake send failed: {e}")
                return

            if cmd in ("1", "emu1"):
                pkt = self.comm.build_raw_stepper_gohome_ack()
                with self.comm._lock:
                    if self.comm._ser:
                        self.comm._ser.write(pkt)
                self.ui.print_cmd(f"[TX] Stepper GoHome Ack: {format_hex(pkt)}")
                return

            if cmd in ("2", "emu2"):
                pkt = self.comm.build_raw_stepper_setzero_ack()
                with self.comm._lock:
                    if self.comm._ser:
                        self.comm._ser.write(pkt)
                self.ui.print_cmd(f"[TX] Stepper SetZero Ack: {format_hex(pkt)}")
                return

            if cmd == "send":
                if len(tokens) < 2:
                    self.ui.print_cmd(
                        "[CMD] usage: send <hex> (e.g. send A5 10 00 05 ... or send a5100005...)"
                    )
                    return

                hexpart = " ".join(tokens[1:]).replace(" ", "")
                try:
                    raw = bytes.fromhex(hexpart)
                except ValueError:
                    self.ui.print_cmd("[CMD ERR] invalid hex")
                    return

                with self.comm._lock:
                    if self.comm._ser:
                        self.comm._ser.write(raw)
                        self.ui.print_cmd(f"[TX RAW] {format_hex(raw)}")
                    else:
                        self.ui.print_cmd("[CMD ERR] serial not open")
                return

            self.ui.print_cmd(f"[CMD ERR] unknown command: {cmd}. Type 'help' for commands.")

        except Exception:
            logger.exception("Unhandled exception in CommandProcessor.execute")
            self.ui.print_cmd("[CMD ERR] exception executing command (see log)")

    def _show_help(self):
        lines = [
            "Commands:",
            "  h, handshake [--hb N] [--tel N] [--send-ack 0|1] [--extra HEX]  Send handshake (overrides defaults)",
            "  1, emu1                 Send emulated Stepper GoHome Ack packet (dev)",
            "  2, emu2                 Send emulated Stepper SetZero Ack packet (dev)",
            "  set <key> <value>       Change runtime defaults or UI sizes.",
            "                          Keys: hb, tel, send-ack, extra, baud, packet_lines, cmd_lines",
            "  status                  Show current runtime defaults + UI sizes",
            "  send <hex>              Send raw hex bytes (advanced)",
            "  help                    Show this help",
            "  q, quit, exit           Quit application",
        ]
        for l in lines:
            self.ui.print_cmd("[HELP] " + l)

    def _show_status(self):
        s = self.defaults.copy()
        s["extra"] = format_hex(s.get("extra", b""))

        self.ui.print_cmd(
            f"[STATUS] defaults: hb={s.get('hb')}ms tel={s.get('tel')}ms "
            f"send_ack={s.get('send_ack')} extra={s.get('extra')} "
            f"baud={s.get('baud')} port={s.get('port')}"
        )
        self.ui.print_cmd(f"[STATUS] ui: packet_lines={self.ui.packet_lines} cmd_lines={self.ui.cmd_lines}")

