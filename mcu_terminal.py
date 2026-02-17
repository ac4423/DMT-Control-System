#!/usr/bin/env python3
"""
mcu_terminal.py -- main entrypoint that wires up UI, commands, and MCUComm.

This file is the only intended entrypoint.
The UI backend is selected based on platform.

example commands to run the application:

python3 mcu_terminal.py --port /dev/ttyUSB0

python3 mcu_terminal.py --port /dev/ttyUSB0 --hb 200 --tel 500 --baud 256000 --send-ack 1

IF NO PACKETS DISPLAYED IN THE CLI:
CHECK THAT BAUD RATES MATCH
CHECK THAT CORRECT PORT HAS BEEN CHOSEN ON THE PC

"""
import argparse
import sys
import threading
import time
import logging
import platform

from mcu_comm.driver import MCUComm

from mcu_terminal_lib.commands import CommandProcessor
from mcu_terminal_lib.decode import decode_and_show

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _load_ui_backend():
    """
    Select OS-specific UI module.

    Linux/macOS: ui_linux.py
    Windows: ui_windows.py (not implemented yet, but placeholder for future)
    """
    if sys.platform.startswith("win"):
        # NOTE: we are NOT implementing ui_windows.py yet.
        raise RuntimeError(
            "Windows platform detected but ui_windows.py is not implemented yet."
        )

    # Default to POSIX UI
    from mcu_terminal_lib.ui_linux import TerminalUI, command_input_loop
    return TerminalUI, command_input_loop


def main():
    parser = argparse.ArgumentParser(description="MCU Serial Monitor (with CLI)")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=256000)
    parser.add_argument("--hb", type=int, default=500)
    parser.add_argument("--tel", type=int, default=1000)
    parser.add_argument("--send-ack", type=int, default=1, choices=[0, 1])
    parser.add_argument("--extra", default="")
    parser.add_argument("--packet-lines", type=int, default=16, help="number of packet window lines (top)")
    parser.add_argument("--cmd-lines", type=int, default=30, help="number of command/history window lines (middle)")
    args = parser.parse_args()

    TerminalUI, command_input_loop = _load_ui_backend()

    extra_bytes = bytes.fromhex(args.extra) if args.extra else b""

    defaults = {
        "hb": args.hb,
        "tel": args.tel,
        "send_ack": bool(args.send_ack),
        "extra": extra_bytes,
        "baud": args.baud,
        "port": args.port,
    }

    ui = TerminalUI(packet_lines=args.packet_lines, cmd_lines=args.cmd_lines)
    ui.enter_alt_screen()
    ui.clear()
    ui.draw_status_bar()
    ui.draw_input_prompt()

    stop_event = threading.Event()

    comm = MCUComm(args.port, args.baud)
    try:
        comm.open()
    except Exception:
        logger.exception("failed to open serial port")
        sys.exit(1)

    comm.register_callback(None, lambda pkt: decode_and_show(pkt, ui))

    processor = CommandProcessor(comm, ui, defaults, stop_event)

    input_thread = threading.Thread(
        target=command_input_loop,
        args=(ui, processor, stop_event),
        daemon=True,
    )
    input_thread.start()

    ui.print_cmd("[INFO] CLI ready. Type 'help' for commands.")

    try:
        last_refresh = 0
        while ui.running and not stop_event.is_set():
            now = time.time()
            if now - last_refresh >= 0.2:
                ui.draw_status_bar()
                last_refresh = now
            time.sleep(0.01)

    except KeyboardInterrupt:
        stop_event.set()
        ui.running = False

    finally:
        stop_event.set()
        ui.running = False
        input_thread.join(timeout=1.0)

        try:
            comm.close()
        except Exception:
            logger.exception("error closing comm")

        try:
            ui.show_cursor()
            ui.exit_alt_screen()
        except Exception:
            pass

        sys.stdout.write("\x1b[0m\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

