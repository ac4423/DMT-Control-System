import sys
import os
import time
import argparse

from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget,
                             QPushButton, QHBoxLayout, QGroupBox, QDoubleSpinBox,
                             QSpinBox, QLabel, QGridLayout, QScrollArea, QFrame)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
import cv2

from Control_GUI.hardware import DataGeneratorThread, ZWOCameraManager, ScanWriter, CaptureThread
from Control_GUI.displays import DashboardWidget
from Control_GUI.comms_manager import CommsManager
from Control_GUI import comms_manager as comms_mod

_gui_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_gui_dir, "system_t0.ref"), "w") as f:
    f.write(str(time.time()))


class MainWindow(QMainWindow):
    STATUS_ON  = ("background-color: #2ecc71; color: black; border-radius: 6px; "
                  "border: 2px solid white; padding: 5px; font-weight: bold; font-size: 10pt;")
    STATUS_OFF = ("background-color: #c0392b; color: white; border-radius: 6px; "
                  "border: 2px solid #555; padding: 5px; font-weight: bold; font-size: 10pt;")

    # Pixel Y-range for the laser line overlay on the RPV diagram
    _LASER_MIN_Y_PX = 240   # y position when height = 0 mm   (bottom of diagram)
    _LASER_MAX_Y_PX = 10    # y position when height = 150 mm (top of diagram)
    _LASER_MAX_MM   = 150.0

    def __init__(self, comms_port: str | None = None):
        super().__init__()
        self.setWindowTitle("RPV Laser Scanner Control System")
        self.resize(1600, 900)

        self.setStyleSheet("""
            QMainWindow { background-color: #000000; }
            QWidget     { background-color: #000000; color: #00FF00; }
            QGroupBox   { border: 1px solid #333; border-radius: 5px;
                          margin-top: 10px; font-weight: bold; color: #00FF00; }
            QPushButton { background-color: #222; color: #00FF00;
                          border: 1px solid #00FF00; padding: 10px; }
            QPushButton:hover    { background-color: #333; }
            QPushButton:disabled { color: #555; border-color: #555; }
            QDoubleSpinBox, QSpinBox { padding: 5px; background-color: #111;
                          color: #00FF00; border: 1px solid #00FF00; border-radius: 3px; }
            QLabel { color: #00FF00; }
        """)

        self.STYLE_BTN_NORMAL = "QPushButton { padding:8px; border-radius:4px; background-color:#34495e; color:white; } QPushButton:pressed { background-color:#2c3e50; }"
        self.STYLE_BTN_ACTION = "QPushButton { padding:8px; border-radius:4px; background-color:#3498db; color:white; font-weight:bold; } QPushButton:pressed { background-color:#1f618d; }"
        self.STYLE_GREEN  = "font-size:11pt; padding:12px; border-radius:5px; color:white; background-color:#2ecc71; font-weight:bold;"
        self.STYLE_RED    = "font-size:11pt; padding:12px; border-radius:5px; color:white; background-color:#e74c3c; font-weight:bold;"
        self.STYLE_PURPLE = "font-size:11pt; padding:12px; border-radius:5px; color:white; background-color:#9b59b6; font-weight:bold;"
        self.STYLE_GREY   = "font-size:11pt; padding:12px; border-radius:5px; color:white; background-color:#7f8c8d;"

        self.is_running_dynamic = False
        self.is_running_static  = False
        self.scan_active        = False

        # ── Hardware init ─────────────────────────────────────────────────
        current_dir = os.path.dirname(os.path.abspath(__file__))
        dll_path = os.path.normpath(os.path.join(current_dir, "Camera", "ASICamera2.dll"))
        self.camera_manager   = ZWOCameraManager(dll_path)
        self.camera_connected = self.camera_manager.open_camera()
        self.scans_dir = os.path.join(current_dir, "Scans")
        os.makedirs(self.scans_dir, exist_ok=True)

        self.scan_writer    = ScanWriter(self.scans_dir, frame_h=1080, frame_w=1920)
        self.capture_thread = None

        # ── Layout: LEFT | CENTRE | RIGHT ────────────────────────────────
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(8)

        # ── LEFT panel ────────────────────────────────────────────────────
        left_widget = QWidget()
        left_widget.setFixedWidth(660)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)

        # Camera feed
        self.video_label = QLabel("Camera Feed")
        self.video_label.setFixedSize(640, 400)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; border: 2px solid #00FF00;")
        left_layout.addWidget(self.video_label)

        self.btn_snap = QPushButton("SNAP PHOTO")
        self.btn_snap.clicked.connect(self.action_snap_image)
        left_layout.addWidget(self.btn_snap)

        self.lbl_frame_count = QLabel("Frames: 0")
        self.lbl_frame_count.setStyleSheet("color: #00FF00; font-size: 10pt;")
        self.lbl_frame_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.lbl_frame_count)

        # Status indicators
        status_row = QHBoxLayout()
        self.lbl_laser = QLabel("LASERS: OFF")
        self.lbl_laser.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_laser.setStyleSheet(self.STATUS_OFF)
        self.lbl_valve = QLabel("INJECTION VALVE: OFF")
        self.lbl_valve.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_valve.setStyleSheet(self.STATUS_OFF)
        status_row.addWidget(self.lbl_laser)
        status_row.addWidget(self.lbl_valve)
        left_layout.addLayout(status_row)

        # RPV diagram — fills remaining space in the left panel
        # rpv_container uses a real layout so nothing escapes it.
        self.rpv_container = QWidget()
        self.rpv_container.setStyleSheet("background-color: #000; border: 2px solid #555;")
        rpv_layout = QVBoxLayout(self.rpv_container)
        rpv_layout.setContentsMargins(0, 0, 0, 0)
        rpv_layout.setSpacing(0)

        self.lbl_rpv = QLabel()
        self.lbl_rpv.setAlignment(Qt.AlignmentFlag.AlignCenter)

        rpv_paths = [os.path.join("Control_GUI", "assets", "RPV_Diagram.png"),
                     os.path.join(current_dir, "RPV_Diagram.png")]
        rpv_pixmap = QPixmap()
        rpv_loaded = False
        for p in rpv_paths:
            if os.path.exists(p):
                rpv_pixmap.load(p)
                rpv_loaded = True
                break

        if rpv_loaded:
            self.lbl_rpv.setPixmap(rpv_pixmap.scaled(
                636, 260,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            self.lbl_rpv.setText("RPV_Diagram.png not found")
            self.lbl_rpv.setStyleSheet("color: red;")

        rpv_layout.addWidget(self.lbl_rpv)

        # Laser line overlay — child of rpv_container so it floats over the image.
        # Initial position at the bottom (height = 0 mm).
        self.laser_line = QFrame(self.rpv_container)
        self.laser_line.setFixedHeight(3)
        self.laser_line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.laser_line.setStyleSheet("background-color: #330000; border: none;")
        self.laser_line.setGeometry(10, self._LASER_MIN_Y_PX, 620, 3)
        self.laser_line.raise_()

        left_layout.addWidget(self.rpv_container)
        main_layout.addWidget(left_widget)

        # ── CENTRE panel: graphs only ─────────────────────────────────────
        self.dashboard = DashboardWidget()
        main_layout.addWidget(self.dashboard, stretch=2)

        # ── RIGHT panel: scrollable controls ─────────────────────────────
        right_contents = QWidget()
        right_layout = QVBoxLayout(right_contents)
        right_layout.setContentsMargins(4, 12, 4, 4)
        right_layout.setSpacing(8)
        self.create_stepper_group(right_layout)
        self.create_flow_group(right_layout)
        self.create_scan_group(right_layout)
        right_layout.addStretch()
        self.create_run_group(right_layout)

        right_scroll = QScrollArea()
        right_scroll.setWidget(right_contents)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFixedWidth(420)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: #000000; }"
            "QScrollBar:vertical { background: #111; width: 8px; }"
            "QScrollBar::handle:vertical { background: #00FF00; border-radius: 4px; }")
        main_layout.addWidget(right_scroll)

        # ── Comms ─────────────────────────────────────────────────────────
        if comms_port:
            self.comms = CommsManager(port=comms_port)
        else:
            self.comms = CommsManager()
        self.comms.telemetry_data.connect(self._handle_telemetry)
        self.comms.telemetry_data.connect(self._on_telemetry_packet)

        # ── Simulation data generator (only runs when no real comms) ──────
        self.generator = DataGeneratorThread()
        self.generator.data_generated.connect(self._on_batch_plots)
        has_real_comms = (getattr(self.comms, "mcu", None) is not None or
                          getattr(self.comms, "_ser", None) is not None)
        if not has_real_comms:
            self.generator.start()

        # ── Video timer ───────────────────────────────────────────────────
        if self.camera_connected:
            self.video_timer = QTimer()
            self.video_timer.timeout.connect(self.update_frame)
            self.video_timer.start(33)
        else:
            self.video_label.setText("No Camera Connected")

    # ── Laser line ────────────────────────────────────────────────────────

    def _update_laser_line(self, height_mm: float):
        """Move the laser line on the RPV diagram to reflect the current motor height."""
        clamped = max(0.0, min(float(height_mm), self._LASER_MAX_MM))
        y = self._LASER_MIN_Y_PX - (clamped / self._LASER_MAX_MM) * (
            self._LASER_MIN_Y_PX - self._LASER_MAX_Y_PX)
        # Width spans the inner width of rpv_container minus a small margin
        w = self.rpv_container.width() - 20
        self.laser_line.setGeometry(10, int(y), max(w, 10), 3)
        self.laser_line.raise_()

    # ── Status indicators ─────────────────────────────────────────────────

    def update_status(self, lasers_on: bool, valve_on: bool):
        if lasers_on:
            self.lbl_laser.setText("LASERS: ON")
            self.lbl_laser.setStyleSheet(self.STATUS_ON)
            self.laser_line.setStyleSheet(
                "background-color: #ff0000; border: 1px solid #ff9999; border-radius: 2px;")
        else:
            self.lbl_laser.setText("LASERS: OFF")
            self.lbl_laser.setStyleSheet(self.STATUS_OFF)
            self.laser_line.setStyleSheet("background-color: #330000; border: none;")

        if valve_on:
            self.lbl_valve.setText("INJECTION VALVE: ON")
            self.lbl_valve.setStyleSheet(self.STATUS_ON)
        else:
            self.lbl_valve.setText("INJECTION VALVE: OFF")
            self.lbl_valve.setStyleSheet(self.STATUS_OFF)

    # ── UI builders ───────────────────────────────────────────────────────

    def create_stepper_group(self, layout):
        grp = QGroupBox("Stepper Motor Control")
        g = QGridLayout()
        self.btn_home = QPushButton("Home (0 mm)")
        self.btn_home.setStyleSheet(self.STYLE_BTN_NORMAL)
        self.btn_home.clicked.connect(self.action_home)
        self.btn_middle = QPushButton("Middle (75 mm)")
        self.btn_middle.setStyleSheet(self.STYLE_BTN_NORMAL)
        self.btn_middle.clicked.connect(self.action_middle)
        self.spin_target = QDoubleSpinBox()
        self.spin_target.setRange(0.0, 150.0)
        self.spin_target.setDecimals(1)
        self.spin_target.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.btn_set_pos = QPushButton("Set")
        self.btn_set_pos.setFixedWidth(60)
        self.btn_set_pos.setStyleSheet(self.STYLE_BTN_ACTION)
        self.btn_set_pos.clicked.connect(self.action_set_position)
        g.addWidget(self.btn_home,      0, 0, 1, 2)
        g.addWidget(self.btn_middle,    0, 2, 1, 2)
        g.addWidget(QLabel("Set Pos:"), 1, 0)
        g.addWidget(self.spin_target,   1, 1)
        g.addWidget(QLabel("mm"),       1, 2)
        g.addWidget(self.btn_set_pos,   1, 3)
        grp.setLayout(g)
        layout.addWidget(grp)

    def create_flow_group(self, layout):
        grp = QGroupBox("Flow Control")
        v = QVBoxLayout()
        sub_curr = QGroupBox("Current Set Flow")
        cl = QGridLayout()
        self.spin_flow_immediate = QDoubleSpinBox()
        self.spin_flow_immediate.setRange(0.0, 100.0)
        self.spin_flow_immediate.setValue(41.6)
        self.spin_flow_immediate.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.btn_set_flow = QPushButton("Set")
        self.btn_set_flow.setFixedWidth(60)
        self.btn_set_flow.setStyleSheet(self.STYLE_BTN_ACTION)
        self.btn_set_flow.clicked.connect(self.action_set_flow_immediate)
        cl.addWidget(QLabel("Set Rate:"),       0, 0)
        cl.addWidget(self.spin_flow_immediate,  0, 1)
        cl.addWidget(QLabel("mL/s"),            0, 2)
        cl.addWidget(self.btn_set_flow,         0, 3)
        sub_curr.setLayout(cl)
        v.addWidget(sub_curr)
        sub_del = QGroupBox("Delay Set Flow")
        dl = QGridLayout()
        self.spin_flow_delayed = QDoubleSpinBox()
        self.spin_flow_delayed.setRange(0.0, 100.0)
        self.spin_flow_delayed.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.spin_delay_ms = QSpinBox()
        self.spin_delay_ms.setRange(0, 10000)
        self.spin_delay_ms.setValue(1000)
        self.spin_delay_ms.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.btn_set_delay = QPushButton("Set")
        self.btn_set_delay.setStyleSheet(self.STYLE_BTN_ACTION)
        self.btn_set_delay.clicked.connect(self.action_set_flow_delayed)
        dl.addWidget(QLabel("Set Rate:"),      0, 0)
        dl.addWidget(self.spin_flow_delayed,   0, 1)
        dl.addWidget(QLabel("mL/s"),           0, 2)
        dl.addWidget(QLabel("Set Delay:"),     1, 0)
        dl.addWidget(self.spin_delay_ms,       1, 1)
        dl.addWidget(QLabel("ms"),             1, 2)
        dl.addWidget(self.btn_set_delay,       2, 0, 1, 3)
        sub_del.setLayout(dl)
        v.addWidget(sub_del)
        grp.setLayout(v)
        layout.addWidget(grp)

    def create_scan_group(self, layout):
        grp = QGroupBox("Scan Controls")
        v = QVBoxLayout()
        self.btn_start_scan = QPushButton("START SCAN")
        self.btn_start_scan.clicked.connect(self.action_start_scan)
        self.btn_stop_scan = QPushButton("STOP SCAN")
        self.btn_stop_scan.clicked.connect(self.action_stop_scan)
        self.btn_open_scans = QPushButton("OPEN SCANS FOLDER")
        self.btn_open_scans.clicked.connect(self.open_gallery)
        v.addWidget(self.btn_start_scan)
        v.addWidget(self.btn_stop_scan)
        v.addWidget(self.btn_open_scans)
        grp.setLayout(v)
        layout.addWidget(grp)

    def create_run_group(self, layout):
        grp = QGroupBox("Experiment Controls")
        v = QVBoxLayout()
        self.btn_dynamic = QPushButton("Run Dynamic")
        self.btn_dynamic.setStyleSheet(self.STYLE_GREEN)
        self.btn_dynamic.clicked.connect(self.action_run_dynamic_toggle)
        self.btn_static = QPushButton("Run Static")
        self.btn_static.setStyleSheet(self.STYLE_PURPLE)
        self.btn_static.clicked.connect(self.action_run_static_toggle)
        v.addWidget(self.btn_dynamic)
        v.addWidget(self.btn_static)
        grp.setLayout(v)
        layout.addWidget(grp)

    # ── Camera ────────────────────────────────────────────────────────────

    def update_frame(self):
        try:
            frame, _ = self.camera_manager.get_frame()
            if frame is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BAYER_BG2RGB)
                h, w, ch = rgb.shape
                qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                self.video_label.setPixmap(
                    QPixmap.fromImage(qt_img).scaled(
                        self.video_label.width(), self.video_label.height(),
                        Qt.AspectRatioMode.KeepAspectRatio))
        except Exception as e:
            print(f"Video update error: {e}")

    def action_snap_image(self):
        if not self.camera_connected:
            print("Cannot snap - no camera.")
            return
        height_mm = f"{self.spin_target.value():.2f}"
        self.camera_manager.capture_image(motor_height=height_mm, folder=self.scans_dir)
        print(f"Manual snap saved (height={height_mm} mm)")

    # ── Scan (HDF5 continuous capture) ───────────────────────────────────

    def action_start_scan(self):
        if self.scan_active:
            return
        if not self.camera_connected:
            print("Cannot scan - no camera.")
            return
        filepath = self.scan_writer.open_session()
        self.scan_active = True
        self.lbl_frame_count.setText("Frames: 0")
        self.btn_start_scan.setText("SCANNING...")
        self.btn_start_scan.setStyleSheet(self.STYLE_RED)
        self.capture_thread = CaptureThread(self.camera_manager, self.scan_writer)
        self.capture_thread.set_height(self.spin_target.value())
        self.capture_thread.frame_captured.connect(self._on_frame_captured)
        self.capture_thread.error_occurred.connect(lambda e: print(f"Capture error: {e}"))
        self.capture_thread.start_capture()
        print(f"Scan started -> {filepath}")

    def action_stop_scan(self):
        if not self.scan_active:
            return
        self.scan_active = False
        if self.capture_thread:
            self.capture_thread.stop_capture()
            self.capture_thread = None
        self.scan_writer.close_session()
        self.btn_start_scan.setText("START SCAN")
        self.btn_start_scan.setStyleSheet("")
        print("Scan stopped.")

    def _on_frame_captured(self, index: int, height_mm: float):
        if index % 10 == 0:
            self.lbl_frame_count.setText(f"Frames: {index + 1}")

    def open_gallery(self):
        if os.path.exists(self.scans_dir):
            os.startfile(self.scans_dir)

    # ── Plot update adapters ──────────────────────────────────────────────

    def _on_batch_plots(self, times, motors, injs, mains, pumps):
        """Relay batch data to dashboard and update laser line from result."""
        latest_mm = self.dashboard.update_plots(times, motors, injs, mains, pumps)
        if latest_mm is not None:
            self._update_laser_line(latest_mm)

    # ── Telemetry ─────────────────────────────────────────────────────────

    def _handle_telemetry(self, ts, state, flow1, total1, pos):
        """Routes real MCU telemetry to the dashboard and laser line."""
        flow2 = 0
        try:
            mcu = self.comms.get_mcu()
            if mcu:
                latest = mcu.get_latest_telemetry()
                if latest:
                    flow2 = latest.get("flow2", 0)
        except Exception:
            pass
        _t, motor_mm = self.dashboard.add_telemetry_point(
            ts_ms=ts,
            motor_steps=pos,
            flow1_ml_min=flow1,
            flow2_ml_min=flow2,
            pump_rpm=0,
        )
        self._update_laser_line(motor_mm)

    def _on_telemetry_packet(self, *args):
        """Adapter for unit conversion — forwards flow rates to dashboard."""
        primary_ml_per_min   = None
        secondary_ml_per_min = None
        ts = None
        if len(args) == 5:
            ts                 = args[0]
            primary_ml_per_min = args[2]
        elif len(args) == 1 and isinstance(args[0], dict):
            pkt                  = args[0]
            ts                   = pkt.get("ts")
            primary_ml_per_min   = pkt.get("flow1") or pkt.get("flow")
            secondary_ml_per_min = pkt.get("flow2")
        try:
            mcu = self.comms.get_mcu()
            if mcu is not None:
                latest = mcu.get_latest_telemetry()
                if latest:
                    if secondary_ml_per_min is None:
                        secondary_ml_per_min = latest.get("flow2")
                    if primary_ml_per_min is None:
                        primary_ml_per_min   = latest.get("flow1")
        except Exception:
            pass
        if primary_ml_per_min is not None:
            try:
                self.dashboard.update_flow_rates(
                    float(primary_ml_per_min) / 60.0,
                    float(secondary_ml_per_min) / 60.0 if secondary_ml_per_min else None,
                    timestamp=ts)
            except AttributeError:
                pass

    # ── Stepper / flow actions ────────────────────────────────────────────

    def _comms_ok(self):
        return bool(self.comms.mcu or self.comms._ser)

    def action_home(self):
        self.stop_any_run()
        self.generator.set_command("HOME")
        if self._comms_ok():
            self.comms.send_go_home(slave_addr=0x03)

    def action_middle(self):
        self.stop_any_run()
        self.generator.set_command("MIDDLE")
        if self._comms_ok():
            self.comms.send_set_middle()

    def action_set_position(self):
        self.stop_any_run()
        target_mm = self.spin_target.value()
        self.generator.set_command("MOVE_TO", value=target_mm)
        if self._comms_ok():
            self.comms.send_move_to((target_mm / 10.0) * 360.0 / 1.8)
        if self.capture_thread:
            self.capture_thread.set_height(target_mm)

    def action_set_flow_immediate(self):
        self.generator.set_command("SET_FLOW_IMMEDIATE",
                                   value=self.spin_flow_immediate.value())

    def action_set_flow_delayed(self):
        self.generator.set_command("SET_FLOW_DELAYED",
                                   value=self.spin_flow_delayed.value(),
                                   extra=self.spin_delay_ms.value())

    # ── Experiment controls ───────────────────────────────────────────────

    def action_run_dynamic_toggle(self):
        if self.is_running_static:
            return
        if not self.is_running_dynamic:
            self.is_running_dynamic = True
            self.generator.set_command("RUN_DYNAMIC")
            self.btn_dynamic.setText("Stop Dynamic")
            self.btn_dynamic.setStyleSheet(self.STYLE_RED)
            self.btn_static.setEnabled(False)
            self.btn_static.setStyleSheet(self.STYLE_GREY)
            self.update_status(lasers_on=True, valve_on=True)
        else:
            self.stop_any_run()

    def action_run_static_toggle(self):
        if self.is_running_dynamic:
            return
        if not self.is_running_static:
            self.is_running_static = True
            self.btn_static.setText("Stop Static")
            self.btn_static.setStyleSheet(self.STYLE_RED)
            self.btn_dynamic.setEnabled(False)
            self.btn_dynamic.setStyleSheet(self.STYLE_GREY)
            self.update_status(lasers_on=True, valve_on=True)
        else:
            self.stop_any_run()

    def stop_any_run(self):
        self.is_running_dynamic = False
        self.is_running_static  = False
        self.generator.set_command("STOP")
        self.btn_dynamic.setText("Run Dynamic")
        self.btn_dynamic.setStyleSheet(self.STYLE_GREEN)
        self.btn_dynamic.setEnabled(True)
        self.btn_static.setText("Run Static")
        self.btn_static.setStyleSheet(self.STYLE_PURPLE)
        self.btn_static.setEnabled(True)
        self.update_status(lasers_on=False, valve_on=False)

    # ── Shutdown ──────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self.capture_thread:
            self.capture_thread.stop_capture()
        if self.scan_writer.is_open:
            self.scan_writer.close_session()
        if hasattr(self, "video_timer"):
            self.video_timer.stop()
        if hasattr(self, "generator"):
            self.generator.stop()
        if hasattr(self, "comms") and self.comms:
            self.comms.close()
        if hasattr(self, "camera_manager") and self.camera_manager:
            self.camera_manager.close_camera()
        event.accept()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RPV Laser Scanner Control System GUI")
    parser.add_argument("-p", "--port", default=comms_mod.SERIAL_PORT,
                        help=f"Serial port (default: {comms_mod.SERIAL_PORT})")
    parser.add_argument("-b", "--baud", default=None,
                        help="Optional baud rate override")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow(comms_port=args.port)
    window.show()
    sys.exit(app.exec())