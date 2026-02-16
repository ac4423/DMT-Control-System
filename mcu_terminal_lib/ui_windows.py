# ui_windows.py
"""
Windows curses-based UI for the MCU terminal.
Requires 'windows-curses' on Windows:
    pip install windows-curses

This module exposes the same public API as ui_linux.py:
 - class TerminalUI(...)
 - def command_input_loop(ui, processor, stop_event)

The UI creates 4 logical regions:
 - status (1 row at top)
 - packet window (packet_lines rows)
 - separator (1 row)
 - command/history window (cmd_lines rows)
 - prompt area (2 rows at bottom): prompt + hint
"""

from __future__ import annotations

import curses
import threading
import time
import logging
from typing import Optional

from mcu_terminal_lib.decode import STATE_NAMES

logger = logging.getLogger(__name__)

# constants to mirror linux layout semantics (1-based rows there)
STATUS_ROWS = 1
SEPARATOR_ROWS = 1
PROMPT_ROWS = 2

ESC = "\x1b"  # kept for compatibility (not used by curses)

# Map some keys we care about
_BACKSPACE_KEYS = {curses.KEY_BACKSPACE, 127, 8}
_ENTER_KEYS = {10, 13, curses.KEY_ENTER}


class TerminalUI:
    def __init__(self, packet_lines: int = 16, cmd_lines: int = 30):
        self._lock = threading.RLock()

        # runtime state
        self.last_state = None
        self.last_state_name = "UNKNOWN"
        self.last_heartbeat_time = None
        self.last_handshake_ack_time = None
        self.packet_count = 0
        self.bad_packets = 0

        # sizes (mutable)
        self.packet_lines = max(1, int(packet_lines))
        self.cmd_lines = max(1, int(cmd_lines))

        # buffers
        self._packet_lines_buf: list[str] = []
        self._cmd_lines_buf: list[str] = []

        # prompt state
        self.cmd_buffer = ""
        self.prompt = "> "
        self.hint = "DMT-6 Nuclear Thermal-Hydraulics Rig v1.0.0"

        # curses objects (initialized in enter_alt_screen)
        self.stdscr: Optional["curses._CursesWindow"] = None
        self.status_win = None
        self.packet_win = None
        self.sep_win = None
        self.cmd_win = None
        self.prompt_win = None

        self.running = True

        # internal cached dimensions
        self._height = 0
        self._width = 0

    # ----------------- curses lifecycle helpers -----------------
    def enter_alt_screen(self):
        """
        Initialize curses and create windows.
        Call once from the main thread before starting input/read threads.
        """
        with self._lock:
            # initialize curses
            self.stdscr = curses.initscr()
            curses.noecho()
            curses.cbreak()
            try:
                curses.curs_set(0)  # hide cursor initially
            except Exception:
                pass
            self.stdscr.keypad(True)

            # allow non-blocking getch with short timeout
            self.stdscr.nodelay(True)

            # create windows layout
            self._recreate_windows()
            self.clear()
            self.draw_status_bar()
            self.draw_input_prompt()

    def exit_alt_screen(self):
        """
        Restore terminal to original state.
        """
        with self._lock:
            try:
                if self.stdscr:
                    self.stdscr.keypad(False)
                curses.nocbreak()
                curses.echo()
                try:
                    curses.curs_set(1)
                except Exception:
                    pass
            except Exception:
                logger.exception("error cleaning curses mode")
            finally:
                try:
                    curses.endwin()
                except Exception:
                    pass
                # release window refs
                self.stdscr = None
                self.status_win = None
                self.packet_win = None
                self.sep_win = None
                self.cmd_win = None
                self.prompt_win = None

    def hide_cursor(self):
        with self._lock:
            try:
                curses.curs_set(0)
            except Exception:
                pass

    def show_cursor(self):
        with self._lock:
            try:
                curses.curs_set(1)
            except Exception:
                pass

    # ----------------- window geometry helpers -----------------
    def _recreate_windows(self):
        """
        Create or resize windows according to current terminal size and configured
        packet/cmd lines.
        """
        if not self.stdscr:
            return

        self._height, self._width = self.stdscr.getmaxyx()  # (rows, cols)

        # ensure we have enough rows for the layout
        min_needed = (
            STATUS_ROWS
            + self.packet_lines
            + SEPARATOR_ROWS
            + self.cmd_lines
            + PROMPT_ROWS
        )
        if self._height < min_needed:
            # if terminal too small, reduce cmd_lines to fit
            available = max(1, self._height - (STATUS_ROWS + self.packet_lines + SEPARATOR_ROWS + PROMPT_ROWS))
            self.cmd_lines = max(1, available)

        # coordinates (0-based)
        status_y = 0
        packet_y = status_y + STATUS_ROWS
        sep_y = packet_y + self.packet_lines
        cmd_y = sep_y + SEPARATOR_ROWS
        prompt_y = cmd_y + self.cmd_lines

        # create windows
        # status bar: height 1
        self.status_win = curses.newwin(STATUS_ROWS, self._width, status_y, 0)
        # packet window: packet_lines rows
        self.packet_win = curses.newwin(self.packet_lines, self._width, packet_y, 0)
        # separator: single row
        self.sep_win = curses.newwin(SEPARATOR_ROWS, self._width, sep_y, 0)
        # cmd/history window
        self.cmd_win = curses.newwin(self.cmd_lines, self._width, cmd_y, 0)
        # prompt area: 2 rows
        self.prompt_win = curses.newwin(PROMPT_ROWS, self._width, prompt_y, 0)

        # ensure scrolling for packet and cmd windows
        try:
            self.packet_win.scrollok(True)
            self.cmd_win.scrollok(True)
        except Exception:
            pass

    # ----------------- drawing helpers -----------------
    def clear(self):
        with self._lock:
            if not self.stdscr:
                return
            self.stdscr.erase()
            self._recreate_windows()
            self.stdscr.refresh()

    def draw_status_bar(self):
        with self._lock:
            if not self.status_win:
                return

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

            try:
                self.status_win.erase()
                # trim to window width
                self.status_win.addnstr(0, 0, line, self._width - 1)
                self.status_win.noutrefresh()
                curses.doupdate()
            except Exception:
                logger.exception("draw_status_bar failed")

    def _clear_area(self, win, height):
        try:
            win.erase()
        except Exception:
            pass

    def _redraw_packet_window(self):
        with self._lock:
            if not self.packet_win:
                return
            try:
                self.packet_win.erase()
                # show only last packet_lines entries
                start = max(0, len(self._packet_lines_buf) - self.packet_lines)
                visible = self._packet_lines_buf[start : start + self.packet_lines]
                for idx, line in enumerate(visible):
                    # addnstr trims automatically if line longer than width
                    self.packet_win.addnstr(idx, 0, line, self._width - 1)
                self.packet_win.noutrefresh()
                curses.doupdate()
            except Exception:
                logger.exception("packet redraw failed")

    def _redraw_cmd_window(self):
        with self._lock:
            if not self.cmd_win:
                return
            try:
                self.cmd_win.erase()
                start = max(0, len(self._cmd_lines_buf) - self.cmd_lines)
                visible = self._cmd_lines_buf[start : start + self.cmd_lines]
                for idx, line in enumerate(visible):
                    self.cmd_win.addnstr(idx, 0, line, self._width - 1)
                self.cmd_win.noutrefresh()
                curses.doupdate()
            except Exception:
                logger.exception("cmd redraw failed")

    def draw_separator(self):
        with self._lock:
            if not self.sep_win:
                return
            try:
                self.sep_win.erase()
                sep_line = "-" * max(10, self._width - 1)
                self.sep_win.addnstr(0, 0, sep_line, self._width - 1)
                self.sep_win.noutrefresh()
                curses.doupdate()
            except Exception:
                logger.exception("draw_separator failed")

    def draw_input_prompt(self):
        with self._lock:
            if not self.prompt_win:
                return
            try:
                self.prompt_win.erase()

                # Compose the prompt display and hint
                cmd_display = (self.prompt + self.cmd_buffer)[: self._width - 1]
                hint_line = f" {self.hint}"[: self._width - 1]

                # First line: prompt + buffer
                self.prompt_win.addnstr(0, 0, cmd_display, self._width - 1)
                # Second line: hint
                self.prompt_win.addnstr(1, 0, hint_line, self._width - 1)

                # Move cursor to correct position within prompt window
                # curses uses absolute coordinates, so compute global row/col
                # getbegyx returns (y, x) of the prompt_win
                begy, begx = self.prompt_win.getbegyx()
                cursor_x = min(len(self.prompt + self.cmd_buffer), self._width - 1)
                cursor_y = begy
                # position cursor visually
                try:
                    curses.setsyx(cursor_y, cursor_x)
                    curses.doupdate()
                except Exception:
                    pass

                self.prompt_win.noutrefresh()
                curses.doupdate()
            except Exception:
                logger.exception("draw_input_prompt failed")

    # ----------------- public printing methods -----------------
    def print_packet(self, text: str):
        with self._lock:
            self._packet_lines_buf.append(text)
            if len(self._packet_lines_buf) > 1000:
                # keep a bounded history to avoid memory bloat
                self._packet_lines_buf = self._packet_lines_buf[-1000:]
            # trim to the configured view size handled by redraw
            self._redraw_packet_window()
            self.draw_input_prompt()

    def print_cmd(self, text: str):
        with self._lock:
            self._cmd_lines_buf.append(text)
            if len(self._cmd_lines_buf) > 1000:
                self._cmd_lines_buf = self._cmd_lines_buf[-1000:]
            self._redraw_cmd_window()
            self.draw_input_prompt()

    # ----------------- event methods called from driver callbacks -----------------
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

    # ----------------- runtime resize helpers -----------------
    def set_packet_lines(self, n: int):
        with self._lock:
            n = max(1, int(n))
            if n == self.packet_lines:
                return
            self.packet_lines = n
            # trim buffers if necessary
            if len(self._packet_lines_buf) > self.packet_lines:
                self._packet_lines_buf = self._packet_lines_buf[-self.packet_lines :]
            self._recreate_windows()
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
            self._recreate_windows()
            self._redraw_packet_window()
            self._redraw_cmd_window()
            self.draw_input_prompt()


# ----------------- Input loop -----------------
def command_input_loop(ui: TerminalUI, processor, stop_event: threading.Event):
    """
    Non-blocking input loop using curses.get_wch/getch.
    This loop runs in a separate thread (same as POSIX loop).
    It reads keys, updates ui.cmd_buffer, and calls processor.execute when user presses Enter.
    """
    # Use a small poll interval to avoid high CPU usage
    poll_interval = 0.02  # 20ms

    while not stop_event.is_set() and ui.running:
        try:
            # If curses windows were resized externally, we can attempt to recreate windows.
            # (A more robust approach is to catch curses.KEY_RESIZE, but in a threaded loop this is
            # less reliable, so we occasionally ensure windows match terminal size.)
            if ui.stdscr:
                try:
                    h, w = ui.stdscr.getmaxyx()
                    if h != ui._height or w != ui._width:
                        with ui._lock:
                            ui._recreate_windows()
                            ui._redraw_packet_window()
                            ui._redraw_cmd_window()
                            ui.draw_status_bar()
                            ui.draw_input_prompt()
                except Exception:
                    pass

            # Try to read one key (non-blocking)
            ch = None
            if ui.stdscr:
                try:
                    # get_wch returns wide char or raises curses.error if no input
                    ch = ui.stdscr.get_wch()
                except curses.error:
                    ch = None
                except Exception as e:
                    # Some terminals/platforms may return ints
                    try:
                        val = ui.stdscr.getch()
                        if val == -1:
                            ch = None
                        else:
                            ch = val
                    except Exception:
                        ch = None

            if ch is None:
                time.sleep(poll_interval)
                continue

            # Normalize input
            # curses.KEY_* constants are ints; get_wch may return str for normal keys
            key_code = None
            key_str = None

            if isinstance(ch, str):
                key_str = ch
                # newline
                if ch in ("\r", "\n"):
                    key_code = 13
            elif isinstance(ch, int):
                key_code = ch
            else:
                # unknown, ignore
                continue

            # Handle Enter
            if key_code in _ENTER_KEYS or key_str in ("\r", "\n"):
                cmdline = ui.cmd_buffer.strip()
                ui.cmd_buffer = ""
                ui.draw_input_prompt()
                if cmdline:
                    ui.print_cmd(f"> {cmdline}")
                    try:
                        processor.execute(cmdline)
                    except Exception:
                        logger.exception("processor.execute raised")
                continue

            # Handle Backspace
            if (key_code in _BACKSPACE_KEYS) or (key_str in ("\x7f", "\b")):
                if ui.cmd_buffer:
                    ui.cmd_buffer = ui.cmd_buffer[:-1]
                    ui.draw_input_prompt()
                continue

            # Printable characters: append
            if key_str is not None:
                # ignore control chars
                if ord(key_str) >= 32:
                    ui.cmd_buffer += key_str
                    ui.draw_input_prompt()
                continue

            # If integer key (like function keys), ignore for now
            # Sleep briefly to avoid tight loop
            time.sleep(poll_interval)

        except Exception:
            logger.exception("error in windows command_input_loop")
            time.sleep(poll_interval)


