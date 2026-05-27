# dashboard_widget.py
import collections
import time

import pyqtgraph as pg
from PyQt6.QtWidgets import QVBoxLayout, QWidget

WINDOW_SIZE = 6000
MOTOR_COUNTS_PER_REV = 16384.0
GT2_PITCH_MM = 2.0
PULLEY_TEETH = 30.0
TELEMETRY_COUNTS_PER_MM = MOTOR_COUNTS_PER_REV / (GT2_PITCH_MM * PULLEY_TEETH)


class DashboardWidget(QWidget):
    """Centre panel: MCU telemetry plots only."""

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.graph_container = pg.GraphicsLayoutWidget()
        self.graph_container.setBackground("k")
        pg.setConfigOptions(antialias=False)

        self.p_motor = self.graph_container.addPlot(title="Motor Height")
        self.p_motor.setLabel("left", "Height", units="mm")
        self.p_motor.showGrid(x=True, y=True)
        self.p_motor.setYRange(0, 150)
        self.curve_motor = self.p_motor.plot(pen=pg.mkPen((0, 255, 255), width=2))
        self.graph_container.nextRow()

        self.p_flow_inj = self.graph_container.addPlot(title="Flowmeter Injection")
        self.p_flow_inj.setLabel("left", "Flow", units="mL/min")
        self.p_flow_inj.showGrid(x=True, y=True)
        self.p_flow_inj.setYRange(0, 2500)
        self.curve_flow_inj = self.p_flow_inj.plot(pen=pg.mkPen((255, 0, 255), width=2))
        self.graph_container.nextRow()

        self.p_flow_main = self.graph_container.addPlot(title="Flowmeter Main")
        self.p_flow_main.setLabel("left", "Flow", units="mL/min")
        self.p_flow_main.setLabel("bottom", "Time", units="s")
        self.p_flow_main.showGrid(x=True, y=True)
        self.p_flow_main.setYRange(0, 5000)
        self.curve_flow_main = self.p_flow_main.plot(pen=pg.mkPen((0, 255, 0), width=2))

        self.p_motor.setXLink(self.p_flow_main)
        self.p_flow_inj.setXLink(self.p_flow_main)

        self.p_flow_main.enableAutoRange(x=False, y=False)
        self.p_flow_main.setXRange(0, 5.0, padding=0)

        layout.addWidget(self.graph_container)

        self._base_ts_ms = None
        self.x_data = collections.deque(maxlen=WINDOW_SIZE)
        self.y_motor = collections.deque(maxlen=WINDOW_SIZE)
        self.y_flow_inj = collections.deque(maxlen=WINDOW_SIZE)
        self.y_flow_main = collections.deque(maxlen=WINDOW_SIZE)

    def add_telemetry_point(self, ts_ms, motor_steps, flow1_ml_min, flow2_ml_min):
        """
        Append one MCU telemetry sample and redraw the three plots.

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

        self.x_data.append(t_s)
        self.y_motor.append(motor_mm)
        self.y_flow_inj.append(float(flow1_ml_min))
        self.y_flow_main.append(float(flow2_ml_min))

        x_list = list(self.x_data)
        self.curve_motor.setData(x_list, list(self.y_motor))
        self.curve_flow_inj.setData(x_list, list(self.y_flow_inj))
        self.curve_flow_main.setData(x_list, list(self.y_flow_main))

        window_seconds = 5.0
        left = max(0.0, t_s - window_seconds)
        right = max(window_seconds, t_s)
        self.p_flow_main.setXRange(left, right, padding=0)

        return t_s, motor_mm
