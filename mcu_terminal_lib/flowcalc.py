# mcu_terminal_lib/flowcalc.py
"""
FlowCalculator: reconstruct instantaneous flow from routed MSG_FLOWMETER_PULSE_DEBUG
packets coming over serial from the STM32. Each packet corresponds to a single
flowmeter pulse and contains a timestamp (u32, ms tick) and pulse total (u32).

This mirrors the MCU UpdateInstantaneous algorithm (windowed timestamps).
"""

import threading
from typing import Optional
from mcu_comm.protocol import u32_from_le, MSG_FLOWMETER_PULSE_DEBUG, CONFIG_TAG_FLOW_WINDOW_MS, CONFIG_TAG_FLOW_PULSES_PER_LITRE

# Defaults chosen to be reasonable; user may override via config commands.
DEFAULT_FLOW_WINDOW_MS = 250
DEFAULT_PULSES_PER_LITRE = 5880  # change to match your hardware

class FlowCalculator:
    def __init__(self,
                 flow_window_ms: int = DEFAULT_FLOW_WINDOW_MS,
                 flow_pulses_per_litre: int = DEFAULT_PULSES_PER_LITRE,
                 short_term_pulse_buffer_size: int = 256):
        self.lock = threading.RLock()
        self.buf_size = int(short_term_pulse_buffer_size)
        if self.buf_size <= 0:
            raise ValueError("buffer size must be > 0")

        # circular buffer storing timestamps (u32 ms) for recent pulses
        self.timestamps = [0] * self.buf_size
        self.short_term_index = 0  # next write index
        self.short_term_count = 0  # number of valid entries in buffer

        # config
        self.flow_window_ms = int(flow_window_ms)
        self.flow_pulses_per_litre = int(flow_pulses_per_litre)

        # output
        self.last_flow_mlmin = 0

        # enabled only when MCU is requested to send pulses; user toggles via config
        self.enabled = False

    # ---- public API ----
    def packet_cb(self, pkt: dict):
        """
        Callback to register with MCUComm for MSG_FLOWMETER_PULSE_DEBUG.
        pkt is the parsed packet dict as produced by PacketParser.
        We'll accept wildcard packets and ignore non-matching types.
        """
        try:
            if pkt.get("type") != MSG_FLOWMETER_PULSE_DEBUG:
                return
            payload = pkt.get("payload", b"")
            if not payload or len(payload) < 9:
                return

            # parse ts:u32 (little endian), state:u8, pulse_total:u32
            ts = u32_from_le(payload[0:4])
            # st = payload[4]  # not used here
            # pulse_total = u32_from_le(payload[5:9])

            # append timestamp as a pulse event
            if not self.enabled:
                # ignore if not enabled
                return

            self._append_pulse_timestamp(ts)
            # after adding, update instantaneous flow
            self._compute_instantaneous_locked()

        except Exception:
            # safe guard: don't let exceptions bubble out of reader thread
            import logging
            logging.getLogger(__name__).exception("FlowCalculator.packet_cb error")

    def _append_pulse_timestamp(self, ts_ms: int):
        with self.lock:
            self.timestamps[self.short_term_index] = int(ts_ms)
            self.short_term_index = (self.short_term_index + 1) % self.buf_size
            if self.short_term_count < self.buf_size:
                self.short_term_count += 1

    def _compute_instantaneous_locked(self):
        """
        Compute and store last_flow_mlmin into self.last_flow_mlmin.
        This mirrors MCU FlowMeter_UpdateInstantaneous logic exactly:
         - form window_start = now - flow_window_ms (now is taken from last pulse timestamp for determinism)
         - count pulses >= window_start
         - if pulses_in_window < 2 => flow = 0
         - t_first = min t in window, t_last = max t in window
         - delta_ms = t_last - t_first (clamp to 1)
         - ml = (pulses_in_window - 1) * 1000 / pulses_per_litre
         - flow_mlmin = (ml * 60000) / delta_ms
        """
        # assumes lock already held
        if self.short_term_count == 0:
            self.last_flow_mlmin = 0
            return

        # copy active entries into local list (stable snapshot under lock)
        count = self.short_term_count
        idx = self.short_term_index
        oldest_index = (idx + self.buf_size - count) % self.buf_size

        now = self.timestamps[(idx - 1) % self.buf_size]  # most recent pulse ts
        window_start = now - self.flow_window_ms

        # count pulses_in_window
        pulses_in_window = 0
        # We'll also collect min and max timestamps
        t_first = 0xFFFFFFFF
        t_last = 0

        for i in range(count):
            buf_idx = (oldest_index + i) % self.buf_size
            t = self.timestamps[buf_idx]
            if t >= window_start:
                pulses_in_window += 1
                if t < t_first:
                    t_first = t
                if t > t_last:
                    t_last = t

        if pulses_in_window < 2 or t_last == 0 or t_first == 0xFFFFFFFF:
            self.last_flow_mlmin = 0
            return

        delta_ms = t_last - t_first
        if delta_ms == 0:
            delta_ms = 1

        # replicate MCU integer math:
        ml = ((pulses_in_window - 1) * 1000) // max(1, int(self.flow_pulses_per_litre))
        flow_mlmin = (ml * 60000) // delta_ms
        self.last_flow_mlmin = int(flow_mlmin)

    def get_last_flow(self) -> int:
        with self.lock:
            return int(self.last_flow_mlmin)

    def set_enabled(self, enabled: bool):
        with self.lock:
            self.enabled = bool(enabled)

    def set_flow_window_ms(self, ms: int):
        with self.lock:
            self.flow_window_ms = int(ms)

    def set_flow_pulses_per_litre(self, v: int):
        with self.lock:
            self.flow_pulses_per_litre = int(v)