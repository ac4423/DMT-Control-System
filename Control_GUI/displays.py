# dashboard_widget.py
import collections
import time

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

WINDOW_SIZE = 6000
MOTOR_COUNTS_PER_REV = 16384.0
GT2_PITCH_MM = 2.0
PULLEY_TEETH = 30.0
TELEMETRY_COUNTS_PER_MM = MOTOR_COUNTS_PER_REV / (GT2_PITCH_MM * PULLEY_TEETH)
FLOW_PLOT_Y_MAX_ML_MIN = 3000
MAIN_FLOW_PLOT_Y_MAX_L_MIN = 100.0  # main meter: full scale in L/min

_FLOW_READOUT_STYLE = (
    "QLabel { color: #00FF00; background-color: #000000; "
    "font-family: Consolas, 'Courier New', monospace; font-size: 12pt; font-weight: bold; "
    "padding: 6px 10px; border: 1px solid #333; }"
)


def _configure_flow_axis(plot_item: pg.PlotItem) -> None:
    """Label flow in mL/min without PyQtGraph SI 'k' prefix (which reads as kmL/min)."""
    plot_item.setLabel("left", "Flow", units="mL/min")
    axis = plot_item.getAxis("left")
    if hasattr(axis, "enableAutoSIPrefix"):
        axis.enableAutoSIPrefix(False)


def _configure_main_flow_axis(plot_item: pg.PlotItem) -> None:
    """Main flowmeter: axis in L/min (telemetry is still mL/min, scaled when plotting)."""
    plot_item.setLabel("left", "Flow", units="L/min")
    axis = plot_item.getAxis("left")
    if hasattr(axis, "enableAutoSIPrefix"):
        axis.enableAutoSIPrefix(False)


def _style_plot_widget(w: pg.PlotWidget) -> None:
    w.setBackground("k")
    w.showGrid(x=True, y=True)


class DashboardWidget(QWidget):
    """Centre panel: MCU telemetry plots and instantaneous flow readouts."""

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)
        pg.setConfigOptions(antialias=False)

        # Motor — full width
        row_motor = QWidget()
        h_motor = QHBoxLayout(row_motor)
        h_motor.setContentsMargins(0, 0, 0, 0)
        h_motor.setSpacing(8)
        self.lbl_motor = QLabel("Height\n0.0 mm")
        self.lbl_motor.setFixedWidth(132)
        self.lbl_motor.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.lbl_motor.setStyleSheet(_FLOW_READOUT_STYLE)
        self.lbl_motor.setWordWrap(True)
        self.w_motor = pg.PlotWidget()
        _style_plot_widget(self.w_motor)
        self.p_motor = self.w_motor.getPlotItem()
        self.p_motor.setTitle("Motor Height")
        self.p_motor.setLabel("left", "Height", units="mm")
        self.p_motor.setLabel("bottom", "Time", units="s")
        self.p_motor.setYRange(0, 150)
        self.curve_motor = self.p_motor.plot(pen=pg.mkPen((0, 255, 255), width=2))
        h_motor.addWidget(self.lbl_motor)
        h_motor.addWidget(self.w_motor, stretch=1)
        layout.addWidget(row_motor, stretch=1)

        # Injection flow — readout | chart
        row_inj = QWidget()
        h_inj = QHBoxLayout(row_inj)
        h_inj.setContentsMargins(0, 0, 0, 0)
        h_inj.setSpacing(8)
        self.lbl_flow_inj = QLabel("Injection\n0 mL/min")
        self.lbl_flow_inj.setFixedWidth(132)
        self.lbl_flow_inj.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.lbl_flow_inj.setStyleSheet(_FLOW_READOUT_STYLE)
        self.lbl_flow_inj.setWordWrap(True)
        self.w_flow_inj = pg.PlotWidget()
        _style_plot_widget(self.w_flow_inj)
        self.p_flow_inj = self.w_flow_inj.getPlotItem()
        self.p_flow_inj.setTitle("Flowmeter Injection")
        _configure_flow_axis(self.p_flow_inj)
        self.p_flow_inj.setLabel("bottom", "Time", units="s")
        self.p_flow_inj.setYRange(0, FLOW_PLOT_Y_MAX_ML_MIN)
        self.curve_flow_inj = self.p_flow_inj.plot(pen=pg.mkPen((255, 0, 255), width=2))
        h_inj.addWidget(self.lbl_flow_inj)
        h_inj.addWidget(self.w_flow_inj, stretch=1)
        layout.addWidget(row_inj, stretch=1)

        # Main flow — readout | chart
        row_main = QWidget()
        h_main = QHBoxLayout(row_main)
        h_main.setContentsMargins(0, 0, 0, 0)
        h_main.setSpacing(8)
        self.lbl_flow_main = QLabel("Main\n0.00 L/min")
        self.lbl_flow_main.setFixedWidth(132)
        self.lbl_flow_main.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.lbl_flow_main.setStyleSheet(_FLOW_READOUT_STYLE)
        self.lbl_flow_main.setWordWrap(True)
        self.w_flow_main = pg.PlotWidget()
        _style_plot_widget(self.w_flow_main)
        self.p_flow_main = self.w_flow_main.getPlotItem()
        self.p_flow_main.setTitle("Flowmeter Main")
        _configure_main_flow_axis(self.p_flow_main)
        self.p_flow_main.setLabel("bottom", "Time", units="s")
        self.p_flow_main.setYRange(0, MAIN_FLOW_PLOT_Y_MAX_L_MIN)
        self.curve_flow_main = self.p_flow_main.plot(pen=pg.mkPen((0, 255, 0), width=2))
        h_main.addWidget(self.lbl_flow_main)
        h_main.addWidget(self.w_flow_main, stretch=1)
        layout.addWidget(row_main, stretch=1)

        self.p_motor.setXLink(self.p_flow_main)
        self.p_flow_inj.setXLink(self.p_flow_main)

        self.p_flow_main.enableAutoRange(x=False, y=False)
        self.p_flow_main.setXRange(0, 5.0, padding=0)

        self._base_ts_ms = None
        self.x_data = collections.deque(maxlen=WINDOW_SIZE)
        self.y_motor = collections.deque(maxlen=WINDOW_SIZE)
        self.y_flow_inj = collections.deque(maxlen=WINDOW_SIZE)
        self.y_flow_main = collections.deque(maxlen=WINDOW_SIZE)

    def add_telemetry_point(self, ts_ms, motor_steps, flow1_ml_min, flow2_ml_min):
        """
        Append one MCU telemetry sample and redraw the three plots.

        flow1 / injection: mL/min. flow2 / main: plotted as L/min (MCU sends mL/min).

        Returns (t_s, motor_mm) so the main window can update the laser line.
        """
        if self._base_ts_ms is None:
            try:
                self._base_ts_ms = float(ts_ms)
            except Exception:
                self._base_ts_ms = time.time() * 1000.0
            t_s = 0.0
        else:
            try:
                t_s = (float(ts_ms) - float(self._base_ts_ms)) / 1000.0
                if t_s < 0:
                    self._base_ts_ms = float(ts_ms)
                    t_s = 0.0
            except Exception:
                t_s = time.time()

        motor_mm = float(motor_steps) / TELEMETRY_COUNTS_PER_MM
        f1 = float(flow1_ml_min)
        f2_l_min = float(flow2_ml_min) / 1000.0

        self.lbl_motor.setText(f"Height\n{motor_mm:.1f} mm")
        self.lbl_flow_inj.setText(f"Injection\n{f1:,.0f} mL/min")
        self.lbl_flow_main.setText(f"Main\n{f2_l_min:.2f} L/min")

        self.x_data.append(t_s)
        self.y_motor.append(motor_mm)
        self.y_flow_inj.append(f1)
        self.y_flow_main.append(f2_l_min)

        x_list = list(self.x_data)
        self.curve_motor.setData(x_list, list(self.y_motor))
        self.curve_flow_inj.setData(x_list, list(self.y_flow_inj))
        self.curve_flow_main.setData(x_list, list(self.y_flow_main))

        window_seconds = 5.0
        left = max(0.0, t_s - window_seconds)
        right = max(window_seconds, t_s)
        self.p_flow_main.setXRange(left, right, padding=0)

        return t_s, motor_mm
