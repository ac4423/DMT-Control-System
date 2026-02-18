import os
import collections
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

WINDOW_SIZE = 6000 

class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        
        # --- Main Layout ---
        main_layout = QHBoxLayout(self)

        # --- Left: Graphs ---
        self.graph_container = pg.GraphicsLayoutWidget()
        self.graph_container.setBackground('k')
        pg.setConfigOptions(antialias=False) 

        # Plot 1: Motor
        self.p_motor = self.graph_container.addPlot(title="Motor (Height)")
        self.p_motor.setLabel('left', "Height", units='mm')
        self.p_motor.showGrid(x=True, y=True)
        self.p_motor.setYRange(0, 150)
        self.curve_motor = self.p_motor.plot(pen=pg.mkPen((0, 255, 255), width=2))
        self.graph_container.nextRow()

        # Plot 2: Pump
        self.p_pump = self.graph_container.addPlot(title="Pump")
        self.p_pump.setLabel('left', "Speed", units='RPM')
        self.p_pump.showGrid(x=True, y=True)
        self.p_pump.setYRange(0, 1000)
        self.curve_pump = self.p_pump.plot(pen=pg.mkPen((255, 165, 0), width=2))
        self.graph_container.nextRow()

        # Plot 3: Flow Inj
        self.p_flow_inj = self.graph_container.addPlot(title="Flowmeter Injection")
        self.p_flow_inj.setLabel('left', "Flow", units='mL/min')
        self.p_flow_inj.showGrid(x=True, y=True)
        self.p_flow_inj.setYRange(0, 2500)
        self.curve_flow_inj = self.p_flow_inj.plot(pen=pg.mkPen((255, 0, 255), width=2))
        self.graph_container.nextRow()

        # Plot 4: Flow Main
        self.p_flow_main = self.graph_container.addPlot(title="Flowmeter Main")
        self.p_flow_main.setLabel('left', "Flow", units='mL/min')
        self.p_flow_main.setLabel('bottom', "Time", units='s')
        self.p_flow_main.showGrid(x=True, y=True)
        self.p_flow_main.setYRange(0, 5000)
        self.curve_flow_main = self.p_flow_main.plot(pen=pg.mkPen((0, 255, 0), width=2))
        
        # Linking axes
        self.p_motor.setXLink(self.p_flow_main)
        self.p_pump.setXLink(self.p_flow_main)
        self.p_flow_inj.setXLink(self.p_flow_main)
        self.p_flow_main.setXRange(0, 5.0, padding=0)

        main_layout.addWidget(self.graph_container, 2)

        # --- Right: Visuals ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_title = QLabel("RPV Laser Scanner")
        self.lbl_title.setStyleSheet("font-size: 16pt; font-weight: bold; margin-bottom: 20px;")
        right_layout.addWidget(self.lbl_title)

        # Status Labels
        status_layout = QHBoxLayout()
        self.STATUS_ON = "background-color: #2ecc71; color: black; border-radius: 8px; border: 2px solid white; padding: 5px; font-weight: bold; font-size: 11pt;"
        self.STATUS_OFF = "background-color: #c0392b; color: white; border-radius: 8px; border: 2px solid #555; padding: 5px; font-weight: bold; font-size: 11pt;"

        self.lbl_laser = QLabel(" LASERS: OFF ")
        self.lbl_laser.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_laser.setStyleSheet(self.STATUS_OFF)
        status_layout.addWidget(self.lbl_laser)

        self.lbl_valve = QLabel(" INJECTION VALVE: OFF ")
        self.lbl_valve.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_valve.setStyleSheet(self.STATUS_OFF)
        status_layout.addWidget(self.lbl_valve)

        right_layout.addLayout(status_layout)
        right_layout.addSpacing(10)

        # Image Container
        self.filter_container = QWidget()
        self.filter_container.setFixedSize(400, 600)
        self.filter_container.setStyleSheet("background-color: #000000; border: 2px solid #555;")
        
        self.lbl_image = QLabel(self.filter_container)
        
        # Image Loading (Relative path 'assets' or current dir)
        base_path = os.path.dirname(os.path.abspath(__file__))
        # Checking both potential locations for robustness
        paths = [
            os.path.join(base_path, "assets", "RPV_Diagram.png"),
            os.path.join(base_path, "RPV_Diagram.png")
        ]
        
        pixmap = QPixmap()
        loaded = False
        for p in paths:
            if os.path.exists(p):
                pixmap.load(p)
                loaded = True
                break
        
        if not loaded:
            self.lbl_image.setText("Image not found\nRPV_Diagram.png")
            self.lbl_image.setStyleSheet("color: red; font-size: 14pt;")
        else:
            self.lbl_image.setPixmap(pixmap.scaled(400, 600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setGeometry(0, 0, 400, 600)

        # Laser Line
        self.laser_line = QFrame(self.filter_container)
        self.laser_line.setFixedHeight(4)
        self.laser_line.setStyleSheet("background-color: #330000; border: none;") 
        self.laser_line.setGeometry(50, 550, 300, 4) 

        right_layout.addWidget(self.filter_container)
        main_layout.addWidget(right_panel, 1)

        # Data Collections
        self.x_data = collections.deque(maxlen=WINDOW_SIZE)
        self.y_motor = collections.deque(maxlen=WINDOW_SIZE)
        self.y_pump = collections.deque(maxlen=WINDOW_SIZE)
        self.y_flow_inj = collections.deque(maxlen=WINDOW_SIZE)
        self.y_flow_main = collections.deque(maxlen=WINDOW_SIZE)

    def update_status(self, lasers_on, valve_on):
        if lasers_on:
            self.lbl_laser.setText(" LASERS: ON ")
            self.lbl_laser.setStyleSheet(self.STATUS_ON)
            self.laser_line.setStyleSheet("background-color: #ff0000; border: 1px solid #ff9999; border-radius: 2px;")
        else:
            self.lbl_laser.setText(" LASERS: OFF ")
            self.lbl_laser.setStyleSheet(self.STATUS_OFF)
            self.laser_line.setStyleSheet("background-color: #330000; border: none;")
            
        if valve_on:
            self.lbl_valve.setText(" INJECTION VALVE: ON ")
            self.lbl_valve.setStyleSheet(self.STATUS_ON)
        else:
            self.lbl_valve.setText(" INJECTION VALVE: OFF ")
            self.lbl_valve.setStyleSheet(self.STATUS_OFF)

    def update_plots(self, times, motors, injs, mains, pumps):
        # Update Deques
        self.x_data.extend(times)
        
        motor_mm = [(m / 16384.0) * 10.0 for m in motors]
        self.y_motor.extend(motor_mm)
        
        self.y_pump.extend(pumps)
        self.y_flow_inj.extend(injs)
        self.y_flow_main.extend(mains)
        
        # Draw Curves
        x_list = list(self.x_data)
        self.curve_motor.setData(x_list, list(self.y_motor))
        self.curve_pump.setData(x_list, list(self.y_pump))
        self.curve_flow_inj.setData(x_list, list(self.y_flow_inj))
        self.curve_flow_main.setData(x_list, list(self.y_flow_main))
        
        # Scroll X-Axis
        if times:
            latest_time = times[-1]
            if latest_time > 5.0:
                self.p_flow_main.setXRange(latest_time - 5.0, latest_time, padding=0)

            # Update Laser Visual
            latest_height_mm = motor_mm[-1]
            min_y_px = 550 
            max_y_px = 50 
            y_pos = min_y_px - (latest_height_mm / 150.0) * (min_y_px - max_y_px)
            self.laser_line.setGeometry(50, int(y_pos), 300, 4)