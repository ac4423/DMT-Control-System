# dashboard_widget.py
import time
import collections
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout

WINDOW_SIZE = 6000


class DashboardWidget(QWidget):
    """
    Centre panel: four synchronised pyqtgraph plots only.
    All visual chrome (status labels, RPV diagram, laser line) lives in GUI.py.
    """

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.graph_container = pg.GraphicsLayoutWidget()
        self.graph_container.setBackground('k')
        pg.setConfigOptions(antialias=False)

        # Plot 1: Motor height
        self.p_motor = self.graph_container.addPlot(title="Motor (Height)")
        self.p_motor.setLabel('left', "Height", units='mm')
        self.p_motor.showGrid(x=True, y=True)
        self.p_motor.setYRange(0, 150)
        self.curve_motor = self.p_motor.plot(pen=pg.mkPen((0, 255, 255), width=2))
        self.graph_container.nextRow()

        # Plot 2: Pump speed
        self.p_pump = self.graph_container.addPlot(title="Pump")
        self.p_pump.setLabel('left', "Speed", units='RPM')
        self.p_pump.showGrid(x=True, y=True)
        self.p_pump.setYRange(0, 1000)
        self.curve_pump = self.p_pump.plot(pen=pg.mkPen((255, 165, 0), width=2))
        self.graph_container.nextRow()

        # Plot 3: Injection flowmeter
        self.p_flow_inj = self.graph_container.addPlot(title="Flowmeter Injection")
        self.p_flow_inj.setLabel('left', "Flow", units='mL/min')
        self.p_flow_inj.showGrid(x=True, y=True)
        self.p_flow_inj.setYRange(0, 2500)
        self.curve_flow_inj = self.p_flow_inj.plot(pen=pg.mkPen((255, 0, 255), width=2))
        self.graph_container.nextRow()

        # Plot 4: Main flowmeter — x-axis master for all linked plots
        self.p_flow_main = self.graph_container.addPlot(title="Flowmeter Main")
        self.p_flow_main.setLabel('left', "Flow", units='mL/min')
        self.p_flow_main.setLabel('bottom', "Time", units='s')
        self.p_flow_main.showGrid(x=True, y=True)
        self.p_flow_main.setYRange(0, 5000)
        self.curve_flow_main = self.p_flow_main.plot(pen=pg.mkPen((0, 255, 0), width=2))

        # Link all x-axes so panning/zooming one moves all
        self.p_motor.setXLink(self.p_flow_main)
        self.p_pump.setXLink(self.p_flow_main)
        self.p_flow_inj.setXLink(self.p_flow_main)

        # Disable auto-range so manual setXRange() always takes effect
        self.p_flow_main.enableAutoRange(x=False, y=False)
        self.p_flow_main.setXRange(0, 5.0, padding=0)

        layout.addWidget(self.graph_container)

        # ── Data deques ───────────────────────────────────────────────────
        self._base_ts_ms = None
        self.x_data      = collections.deque(maxlen=WINDOW_SIZE)
        self.y_motor     = collections.deque(maxlen=WINDOW_SIZE)
        self.y_pump      = collections.deque(maxlen=WINDOW_SIZE)
        self.y_flow_inj  = collections.deque(maxlen=WINDOW_SIZE)
        self.y_flow_main = collections.deque(maxlen=WINDOW_SIZE)

    # ── Batch update (bulk data / simulation) ─────────────────────────────
    def update_plots(self, times, motors, injs, mains, pumps):
        """
        Extend deques with batches of pre-converted data and redraw.
        motors — raw steps; converted to mm here.
        Returns latest motor_mm so GUI.py can update the laser line.
        """
        self.x_data.extend(times)

        motor_mm = [(m / 16384.0) * 10.0 for m in motors]
        self.y_motor.extend(motor_mm)
        self.y_pump.extend(pumps)
        self.y_flow_inj.extend(injs)
        self.y_flow_main.extend(mains)

        x_list = list(self.x_data)
        self.curve_motor.setData(x_list, list(self.y_motor))
        self.curve_pump.setData(x_list, list(self.y_pump))
        self.curve_flow_inj.setData(x_list, list(self.y_flow_inj))
        self.curve_flow_main.setData(x_list, list(self.y_flow_main))

        if times:
            latest_time = times[-1]
            if latest_time > 5.0:
                self.p_flow_main.setXRange(latest_time - 5.0, latest_time, padding=0)

        return motor_mm[-1] if motor_mm else None

    # ── Single-point update (one telemetry packet from MCU) ───────────────
    def add_telemetry_point(self, ts_ms, motor_steps, flow1_ml_min, flow2_ml_min,
                            pump_rpm=0):
        """
        Append a single telemetry sample and immediately redraw.
        Uses relative time (seconds since first packet) for the x-axis.
        Returns (t, motor_mm) so GUI.py can update the laser line.
        """
        if self._base_ts_ms is None:
            try:
                self._base_ts_ms = float(ts_ms)
            except Exception:
                self._base_ts_ms = time.time() * 1000.0

        try:
            t = (float(ts_ms) - float(self._base_ts_ms)) / 1000.0
            if t < 0:
                self._base_ts_ms = float(ts_ms)
                t = 0.0
        except Exception:
            t = time.time()

        self.x_data.append(t)

        motor_mm = (motor_steps / 16384.0) * 10.0
        self.y_motor.append(motor_mm)
        self.y_pump.append(float(pump_rpm))
        self.y_flow_inj.append(float(flow1_ml_min))
        self.y_flow_main.append(float(flow2_ml_min))

        x_list = list(self.x_data)
        self.curve_motor.setData(x_list, list(self.y_motor))
        self.curve_pump.setData(x_list, list(self.y_pump))
        self.curve_flow_inj.setData(x_list, list(self.y_flow_inj))
        self.curve_flow_main.setData(x_list, list(self.y_flow_main))

        window_seconds = 5.0
        left  = max(0.0, t - window_seconds)
        right = max(window_seconds, t)
        self.p_flow_main.setXRange(left, right, padding=0)

        return t, motor_mm