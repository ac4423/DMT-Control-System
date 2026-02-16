# ui_linux.py
import sys
import threading
import time
import termios
import tty
import select
import os
import fcntl
import errno
import logging

from mcu_terminal_lib.decode import STATE_NAMES # state name mapping used by UI update_state

logger = logging.getLogger(__name__)

ESC = "\x1b"  # escape constant

# Fixed rows
STATUS_ROW = 1
FIRST_PACKET_ROW = 2  # first row for packet window


class TerminalUI:
    def __init__(self, packet_lines: int = 16, cmd_lines: int = 30):
        self._lock = threading.RLock()

        self.last_state = None
        self.last_state_name = "UNKNOWN"
        self.last_heartbeat_time = None
        self.last_handshake_ack_time = None
        self.packet_count = 0
        self.bad_packets = 0

        # window sizes (mutable at runtime)
        self.packet_lines = max(1, int(packet_lines))
        self.cmd_lines = max(1, int(cmd_lines))

        # buffers for each window
        self._packet_lines_buf = []
        self._cmd_lines_buf = []

        self.running = True

        # command line buffer
        self.cmd_buffer = ""
        self.prompt = "> "
        self.hint = "DMT-6 Nuclear Thermal-Hydraulics Rig v1.0.0"

    # --- terminal control helpers ---
    def enter_alt_screen(self):
        sys.stdout.write(f"{ESC}[?1049h")
        sys.stdout.flush()

    def exit_alt_screen(self):
        sys.stdout.write(f"{ESC}[?1049l")
        sys.stdout.flush()

    def hide_cursor(self):
        sys.stdout.write(f"{ESC}[?25l")
        sys.stdout.flush()

    def show_cursor(self):
        sys.stdout.write(f"{ESC}[?25h")
        sys.stdout.flush()

    # ------- layout helpers (recomputed dynamically) -------
    def packet_start_row(self):
        return FIRST_PACKET_ROW

    def packet_end_row(self):
        return self.packet_start_row() + self.packet_lines - 1

    def cmd_start_row(self):
        return self.separator_row() + 1

    def cmd_end_row(self):
        return self.cmd_start_row() + self.cmd_lines - 1

    def prompt_row(self):
        # one blank row between cmd window and prompt for clarity
        return self.cmd_end_row() + 1

    def _term_width(self) -> int:
        try:
            import shutil
            return shutil.get_terminal_size((120, 24)).columns
        except Exception:
            return 120

    def separator_row(self):
        return self.packet_end_row() + 1

    def draw_separator(self):
        with self._lock:
            w = self._term_width()
            line = "-" * max(10, w - 1)
            r = self.separator_row()
            sys.stdout.write(f"{ESC}[{r};1H{ESC}[2K{line[:120]}")
            sys.stdout.flush()

    # ------- low-level drawing helpers -------
    def clear(self):
        sys.stdout.write(f"{ESC}[2J{ESC}[H")
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
            )

            # Position and write the status bar (no trailing newline)
            sys.stdout.write(f"{ESC}[{STATUS_ROW};1H{ESC}[2K{line[:120]}")
            sys.stdout.flush()

    def _clear_area(self, row_start: int, row_end: int):
        for r in range(row_start, row_end + 1):
            sys.stdout.write(f"{ESC}[{r};1H{ESC}[2K")

    def _redraw_packet_window(self):
        with self._lock:
            start = self.packet_start_row()

            # hide cursor while updating many rows
            self.hide_cursor()

            row = start
            for l in self._packet_lines_buf:
                sys.stdout.write(f"{ESC}[{row};1H{ESC}[2K{l[:120]}")
                row += 1

            # clear leftover rows in packet area
            if row <= self.packet_end_row():
                self._clear_area(row, self.packet_end_row())

            # draw separator (already positions explicitly)
            self.draw_separator()

            sys.stdout.flush()
            self.show_cursor()

    def _redraw_cmd_window(self):
        with self._lock:
            start = self.cmd_start_row()

            self.hide_cursor()

            row = start
            for l in self._cmd_lines_buf:
                sys.stdout.write(f"{ESC}[{row};1H{ESC}[2K{l[:120]}")
                row += 1

            if row <= self.cmd_end_row():
                self._clear_area(row, self.cmd_end_row())

            self.draw_separator()

            sys.stdout.flush()
            self.show_cursor()

    def draw_input_prompt(self):
        with self._lock:
            # hide cursor while assembling the prompt lines to avoid flicker
            self.hide_cursor()

            cmd_display = (self.prompt + self.cmd_buffer)[:120]
            pr = self.prompt_row()

            # write prompt line and hint line without newlines
            sys.stdout.write(f"{ESC}[{pr};1H{ESC}[2K{cmd_display[:120]}")
            hint_line = f" {self.hint}"
            sys.stdout.write(f"{ESC}[{pr + 1};1H{ESC}[2K{hint_line[:120]}")

            # set cursor column after the prompt text
            col = len(self.prompt + self.cmd_buffer) + 1
            if col < 1:
                col = 1

            sys.stdout.write(f"{ESC}[{pr};{col}H")
            sys.stdout.flush()

            # show cursor now that we are positioned
            self.show_cursor()

    # ------- public printing methods -------
    def print_packet(self, text: str):
        with self._lock:
            self._packet_lines_buf.append(text)
            if len(self._packet_lines_buf) > self.packet_lines:
                self._packet_lines_buf.pop(0)

            self._redraw_packet_window()
            self.draw_input_prompt()

    def print_cmd(self, text: str):
        with self._lock:
            self._cmd_lines_buf.append(text)
            if len(self._cmd_lines_buf) > self.cmd_lines:
                self._cmd_lines_buf.pop(0)

            self._redraw_cmd_window()
            self.draw_input_prompt()

    # ------- event methods called from driver callbacks -------
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

    # ------- runtime resize helpers -------
    def set_packet_lines(self, n: int):
        with self._lock:
            n = max(1, int(n))
            if n == self.packet_lines:
                return

            self.packet_lines = n

            if len(self._packet_lines_buf) > self.packet_lines:
                self._packet_lines_buf = self._packet_lines_buf[-self.packet_lines :]

            self._redraw_packet_window()
            self._redraw_cmd_window()
            self.draw_input_prompt()

    def set_cmd_lines(self, n: int):
        with self._lock:
            n = max(1, int(n))
            if n == self.cmd_lines:
                return

            self.cmd_lines = n

            if len(self._cmd_lines_buf) > self.cmd_lines:
                self._cmd_lines_buf = self._cmd_lines_buf[-self.cmd_lines :]

            self._redraw_packet_window()
            self._redraw_cmd_window()
            self.draw_input_prompt()


def command_input_loop(ui: TerminalUI, processor, stop_event: threading.Event):
    """
    POSIX input loop: sets terminal to cbreak + non-blocking read and dispatches
    keys into the CommandProcessor. This remains POSIX-only and will be replaced
    by a Windows-specific implementation when we add ui_windows.py.
    """
    stdin_fd = sys.stdin.fileno()
    old_term = termios.tcgetattr(stdin_fd)
    old_flags = fcntl.fcntl(stdin_fd, fcntl.F_GETFL)

    try:
        tty.setcbreak(stdin_fd)
        fcntl.fcntl(stdin_fd, fcntl.F_SETFL, old_flags | os.O_NONBLOCK)

        while not stop_event.is_set() and ui.running:
            try:
                r, _, _ = select.select([stdin_fd], [], [], 0.1)
            except (ValueError, OSError):
                break

            if not r:
                continue

            try:
                data = os.read(stdin_fd, 1024)
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    continue
                logger.exception("stdin read error")
                break

            if not data:
                continue

            try:
                text = data.decode("utf-8", errors="ignore")
            except Exception:
                text = ""

            for ch in text:
                if ch in ("\r", "\n"):
                    cmdline = ui.cmd_buffer.strip()
                    ui.cmd_buffer = ""
                    ui.draw_input_prompt()

                    if cmdline:
                        ui.print_cmd(f"> {cmdline}")
                        processor.execute(cmdline)
                    continue

                if ch in ("\x7f", "\b"):
                    if ui.cmd_buffer:
                        ui.cmd_buffer = ui.cmd_buffer[:-1]
                        ui.draw_input_prompt()
                    continue

                if ord(ch) >= 32:
                    ui.cmd_buffer += ch
                    ui.draw_input_prompt()

    finally:
        try:
            fcntl.fcntl(stdin_fd, fcntl.F_SETFL, old_flags)
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_term)
        except Exception:
            pass

