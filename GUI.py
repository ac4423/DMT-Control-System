import argparse
import os
import sys
import time

import cv2
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from Control_GUI import comms_manager as comms_mod
from Control_GUI.comms_manager import CommsManager
from Control_GUI.displays import DashboardWidget
from Control_GUI.hardware import (
    CAMERA_CAPTURE_HEIGHT,
    CAMERA_CAPTURE_WIDTH,
    CaptureThread,
    ProgramSession,
    ScanWriter,
    ZWOCameraManager,
)

_gui_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_gui_dir, "system_t0.ref"), "w", encoding="utf-8") as f:
    f.write(str(time.time()))


class MainWindow(QMainWindow):
    STATUS_ON = (
        "background-color: #2ecc71; color: black; border-radius: 6px; "
        "border: 2px solid white; padding: 5px; font-weight: bold; font-size: 10pt;"
    )
    STATUS_OFF = (
        "background-color: #c0392b; color: white; border-radius: 6px; "
        "border: 2px solid #555; padding: 5px; font-weight: bold; font-size: 10pt;"
    )

    _LASER_MIN_Y_PX = 178
    _LASER_MAX_Y_PX = 8
    _LASER_MAX_MM = 225.0

    def __init__(self, comms_port: str | None = None):
        super().__init__()
        self.setWindowTitle("RPV Laser Scanner Control System")
        self.resize(1600, 900)

        self.setStyleSheet("""
            QMainWindow { background-color: #000000; }
            QWidget     { background-color: #000000; color: #00FF00; }
            QGroupBox   { border: 1px solid #333; border-radius: 5px;
                          margin-top: 18px; padding-top: 12px;
                          font-weight: bold; color: #00FF00; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
                               left: 10px; padding: 0 6px; }
            QPushButton { background-color: #222; color: #00FF00;
                          border: 1px solid #00FF00; padding: 8px; }
            QPushButton:hover    { background-color: #333; }
            QPushButton:disabled { color: #555; border-color: #555; }
            QDoubleSpinBox, QSpinBox { padding: 5px; background-color: #111;
                          color: #00FF00; border: 1px solid #00FF00; border-radius: 3px; }
            QLabel { color: #00FF00; }
        """)

        self.STYLE_BTN_NORMAL = "QPushButton { padding:8px; border-radius:4px; background-color:#34495e; color:white; } QPushButton:pressed { background-color:#2c3e50; }"
        self.STYLE_BTN_ACTION = "QPushButton { padding:8px; border-radius:4px; background-color:#3498db; color:white; font-weight:bold; } QPushButton:pressed { background-color:#1f618d; }"
        self.STYLE_GREEN = "font-size:11pt; padding:12px; border-radius:5px; color:white; background-color:#2ecc71; font-weight:bold;"
        self.STYLE_RED = "font-size:11pt; padding:12px; border-radius:5px; color:white; background-color:#e74c3c; font-weight:bold;"
        self.STYLE_PURPLE = "font-size:11pt; padding:12px; border-radius:5px; color:white; background-color:#9b59b6; font-weight:bold;"
        self.STYLE_GREY = "font-size:11pt; padding:12px; border-radius:5px; color:white; background-color:#7f8c8d;"

        self.is_running_dynamic = False
        self.is_running_static = False
        self.current_motor_mm = 0.0
        self._mcu_state = 0

        current_dir = os.path.dirname(os.path.abspath(__file__))
        dll_path = os.path.normpath(os.path.join(current_dir, "Camera", "ASICamera2.dll"))
        self.camera_manager = ZWOCameraManager(dll_path)
        self.camera_connected = self.camera_manager.open_camera()
        self.programs_dir = os.path.join(current_dir, "Programs")
        os.makedirs(self.programs_dir, exist_ok=True)
        self._telemetry_session = ProgramSession(self.programs_dir)
        self._recording = False
        self._scan_writer = None
        self._capture_thread = None
        self._recording_session_dir = None
        self._recording_h5_path = ""
        self._recorded_frame_count = 0

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        left_widget = QWidget()
        left_widget.setFixedWidth(560)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(8)

        self.video_label = QLabel("Camera Feed")
        self.video_label.setFixedSize(540, 540)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; border: 2px solid #00FF00;")
        left_layout.addWidget(self.video_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.create_data_recording_group(left_layout)

        self.rpv_container = QWidget()
        self.rpv_container.setFixedHeight(196)
        self.rpv_container.setStyleSheet("background-color: #000; border: 2px solid #555;")
        rpv_layout = QVBoxLayout(self.rpv_container)
        rpv_layout.setContentsMargins(0, 0, 0, 0)
        rpv_layout.setSpacing(0)

        self.lbl_rpv = QLabel()
        self.lbl_rpv.setAlignment(Qt.AlignmentFlag.AlignCenter)

        rpv_paths = [
            os.path.join(current_dir, "Control_GUI", "assets", "RPV_Diagram.png"),
            os.path.join(current_dir, "RPV_Diagram.png"),
        ]
        rpv_pixmap = QPixmap()
        rpv_loaded = False
        for path in rpv_paths:
            if os.path.exists(path):
                rpv_pixmap.load(path)
                rpv_loaded = True
                break

        if rpv_loaded:
            self.lbl_rpv.setPixmap(
                rpv_pixmap.scaled(
                    540,
                    190,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.lbl_rpv.setText("RPV_Diagram.png not found")
            self.lbl_rpv.setStyleSheet("color: red;")

        rpv_layout.addWidget(self.lbl_rpv)

        self.laser_line = QFrame(self.rpv_container)
        self.laser_line.setFixedHeight(3)
        self.laser_line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.laser_line.setStyleSheet("background-color: #330000; border: none;")
        self.laser_line.setGeometry(10, self._LASER_MIN_Y_PX, 520, 3)
        self.laser_line.raise_()

        left_layout.addWidget(self.rpv_container)
        main_layout.addWidget(left_widget)

        self.dashboard = DashboardWidget()
        main_layout.addWidget(self.dashboard, stretch=1)

        right_contents = QWidget()
        right_layout = QVBoxLayout(right_contents)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(10)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.lbl_laser = QLabel("LASERS: OFF")
        self.lbl_laser.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_laser.setMinimumHeight(54)
        self.lbl_laser.setStyleSheet(self.STATUS_OFF)
        self.lbl_valve = QLabel("INJECTION VALVE: OFF")
        self.lbl_valve.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_valve.setMinimumHeight(54)
        self.lbl_valve.setStyleSheet(self.STATUS_OFF)
        status_row.addWidget(self.lbl_laser)
        status_row.addWidget(self.lbl_valve)
        right_layout.addLayout(status_row)

        self.create_stepper_group(right_layout)
        self.create_flow_group(right_layout)
        self.create_program_group(right_layout)
        right_layout.addStretch()
        self.create_run_group(right_layout)

        right_scroll = QScrollArea()
        right_scroll.setWidget(right_contents)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFixedWidth(440)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: #000000; }"
            "QScrollBar:vertical { background: #111; width: 8px; }"
            "QScrollBar::handle:vertical { background: #00FF00; border-radius: 4px; }"
        )
        main_layout.addWidget(right_scroll)

        self.comms = CommsManager(port=comms_port) if comms_port else CommsManager()
        self.comms.telemetry_data.connect(self._handle_telemetry)
        self.comms.link_alive.connect(self._on_mcu_link_alive)
        self.comms.heartbeat_data.connect(self._on_heartbeat)
        self.comms.handshake_status.connect(self._on_handshake_status)
        self.comms.tx_status.connect(self._on_tx_status)
        self._handshake_text = "Handshake: sent, waiting for ACK"
        self._heartbeat_text = "Heartbeat: none"
        self._tx_text = "TX: idle"
        self._update_mcu_status_label()

        if self.camera_connected:
            self.video_timer = QTimer()
            self.video_timer.timeout.connect(self.update_frame)
            self.video_timer.start(33)
        else:
            self.video_label.setText("No Camera Connected")

    def _on_mcu_link_alive(self, alive: bool):
        self._update_mcu_status_label()

    def _on_heartbeat(self, ts: int, state: int, startup_step: int, counter: int):
        self._heartbeat_text = f"Heartbeat: #{counter} state={state} startup_step={startup_step}"
        self._update_mcu_status_label()

    def _on_handshake_status(self, ok: bool, detail: str):
        self._handshake_text = f"Handshake: {'ACK' if ok else 'not ACKed'} ({detail})"
        self._update_mcu_status_label()

    def _on_tx_status(self, text: str):
        self._tx_text = text
        self._update_mcu_status_label()

    def _update_mcu_status_label(self):
        port = getattr(self.comms, "port", "?")
        if getattr(self.comms, "camera_only", False):
            self.lbl_program_status.setText(
                f"MCU: not connected on {port}\n"
                "Check COM port, cable, and that no terminal already has it open"
            )
            self.lbl_program_status.setStyleSheet("color: #e74c3c; font-size: 9pt;")
            return

        details = f"{self._handshake_text}\n{self._heartbeat_text}\n{self._tx_text}"
        if getattr(self.comms, "telemetry_seen", False):
            self.lbl_program_status.setText(f"MCU: {port} - receiving telemetry\n{details}")
            self.lbl_program_status.setStyleSheet("color: #2ecc71; font-size: 9pt;")
        elif getattr(self.comms, "heartbeat_seen", False):
            self.lbl_program_status.setText(f"MCU: {port} - heartbeat OK, waiting for telemetry\n{details}")
            self.lbl_program_status.setStyleSheet("color: #f39c12; font-size: 9pt;")
        elif getattr(self.comms, "mcu", None) or getattr(self.comms, "_ser", None):
            self.lbl_program_status.setText(
                f"MCU: {port} - port open, waiting for telemetry\n"
                f"{details}\nCheck USB-UART wiring / firmware / TX LED on adapter"
            )
            self.lbl_program_status.setStyleSheet("color: #f39c12; font-size: 9pt;")
        else:
            self.lbl_program_status.setText("MCU: idle")
            self.lbl_program_status.setStyleSheet("color: #00FF00; font-size: 9pt;")

    def _update_laser_line(self, height_mm: float):
        clamped = max(0.0, min(float(height_mm), self._LASER_MAX_MM))
        y = self._LASER_MIN_Y_PX - (clamped / self._LASER_MAX_MM) * (
            self._LASER_MIN_Y_PX - self._LASER_MAX_Y_PX
        )
        w = self.rpv_container.width() - 20
        self.laser_line.setGeometry(10, int(y), max(w, 10), 3)
        self.laser_line.raise_()

    def update_status(self, lasers_on: bool, valve_on: bool):
        if lasers_on:
            self.lbl_laser.setText("LASERS: ON")
            self.lbl_laser.setStyleSheet(self.STATUS_ON)
            self.laser_line.setStyleSheet(
                "background-color: #ff0000; border: 1px solid #ff9999; border-radius: 2px;"
            )
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

    def create_stepper_group(self, layout):
        grp = QGroupBox("Stepper Motor Control")
        g = QGridLayout()
        g.setContentsMargins(12, 12, 12, 12)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(10)
        self.btn_home = QPushButton("Set 0")
        self.btn_home.setStyleSheet(self.STYLE_BTN_NORMAL)
        self.btn_home.clicked.connect(self.action_set_zero)
        self.btn_middle = QPushButton("Middle (75 mm)")
        self.btn_middle.setStyleSheet(self.STYLE_BTN_NORMAL)
        self.btn_middle.clicked.connect(self.action_middle)
        self.spin_target = QDoubleSpinBox()
        self.spin_target.setRange(0.0, 225.0)
        self.spin_target.setDecimals(1)
        self.spin_target.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.btn_set_pos = QPushButton("Set")
        self.btn_set_pos.setFixedWidth(60)
        self.btn_set_pos.setStyleSheet(self.STYLE_BTN_ACTION)
        self.btn_set_pos.clicked.connect(self.action_set_position)
        g.addWidget(self.btn_home, 0, 0, 1, 2)
        g.addWidget(self.btn_middle, 0, 2, 1, 2)
        g.addWidget(QLabel("Set Pos:"), 1, 0)
        g.addWidget(self.spin_target, 1, 1)
        g.addWidget(QLabel("mm"), 1, 2)
        g.addWidget(self.btn_set_pos, 1, 3)
        grp.setLayout(g)
        layout.addWidget(grp)

    def create_flow_group(self, layout):
        grp = QGroupBox("Flow Control")
        v = QVBoxLayout()
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        sub_curr = QGroupBox("Current Set Flow")
        cl = QGridLayout()
        cl.setContentsMargins(10, 10, 10, 10)
        cl.setHorizontalSpacing(8)
        cl.setVerticalSpacing(8)
        self.spin_flow_immediate = QSpinBox()
        self.spin_flow_immediate.setRange(0, 3000)
        self.spin_flow_immediate.setValue(0)
        self.spin_flow_immediate.setSuffix(" mL/min")
        self.spin_flow_immediate.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.btn_set_flow = QPushButton("Set")
        self.btn_set_flow.setFixedWidth(60)
        self.btn_set_flow.setStyleSheet(self.STYLE_BTN_ACTION)
        self.btn_set_flow.clicked.connect(self.action_set_flow_immediate)
        cl.addWidget(QLabel("Set Rate:"), 0, 0)
        cl.addWidget(self.spin_flow_immediate, 0, 1, 1, 2)
        cl.addWidget(self.btn_set_flow, 0, 3)
        sub_curr.setLayout(cl)
        v.addWidget(sub_curr)

        sub_del = QGroupBox("Scheduled Set Flow")
        dl = QGridLayout()
        dl.setContentsMargins(10, 10, 10, 10)
        dl.setHorizontalSpacing(8)
        dl.setVerticalSpacing(8)
        self.spin_flow_delayed = QSpinBox()
        self.spin_flow_delayed.setRange(0, 3000)
        self.spin_flow_delayed.setSuffix(" mL/min")
        self.spin_flow_delayed.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.spin_delay_ms = QSpinBox()
        self.spin_delay_ms.setRange(0, 10000)
        self.spin_delay_ms.setValue(1000)
        self.spin_delay_ms.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.btn_set_delay = QPushButton("Set")
        self.btn_set_delay.setStyleSheet(self.STYLE_BTN_ACTION)
        self.btn_set_delay.clicked.connect(self.action_set_flow_delayed)
        dl.addWidget(QLabel("Set Rate:"), 0, 0)
        dl.addWidget(self.spin_flow_delayed, 0, 1, 1, 2)
        dl.addWidget(QLabel("Set Delay:"), 1, 0)
        dl.addWidget(self.spin_delay_ms, 1, 1)
        dl.addWidget(QLabel("ms"), 1, 2)
        dl.addWidget(self.btn_set_delay, 2, 0, 1, 3)
        sub_del.setLayout(dl)
        v.addWidget(sub_del)

        grp.setLayout(v)
        layout.addWidget(grp)

    def create_program_group(self, layout):
        grp = QGroupBox("Program Controls")
        v = QVBoxLayout()
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        self.lbl_program_status = QLabel("MCU: idle")
        self.lbl_program_status.setStyleSheet("color: #00FF00; font-size: 9pt;")
        self.lbl_program_status.setWordWrap(True)
        self.btn_open_programs = QPushButton("OPEN PROGRAMS FOLDER")
        self.btn_open_programs.clicked.connect(self.open_programs_folder)
        v.addWidget(self.lbl_program_status)
        v.addWidget(self.btn_open_programs)
        grp.setLayout(v)
        layout.addWidget(grp)

    def create_data_recording_group(self, layout):
        grp = QGroupBox("Data Recording")
        v = QVBoxLayout()
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        self.lbl_recording = QLabel(
            "Telemetry is not saved until recording starts.\n"
            f"Folder: {self.programs_dir}"
        )
        self.lbl_recording.setStyleSheet("color: #aaaaaa; font-size: 8pt;")
        self.lbl_recording.setWordWrap(True)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_rec_start = QPushButton("Start recording")
        self.btn_rec_start.setStyleSheet(self.STYLE_GREEN)
        self.btn_rec_start.clicked.connect(self.action_start_recording)
        self.btn_rec_stop = QPushButton("Stop recording")
        self.btn_rec_stop.setStyleSheet(self.STYLE_RED)
        self.btn_rec_stop.setEnabled(False)
        self.btn_rec_stop.clicked.connect(self.action_stop_recording)
        row.addWidget(self.btn_rec_start)
        row.addWidget(self.btn_rec_stop)
        v.addWidget(self.lbl_recording)
        v.addLayout(row)
        grp.setLayout(v)
        layout.addWidget(grp)

    def create_run_group(self, layout):
        grp = QGroupBox("Experiment Controls")
        v = QVBoxLayout()
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
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

    def update_frame(self):
        try:
            frame, _ = self.camera_manager.get_frame()
            if frame is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BAYER_BG2RGB)
                h, w, ch = rgb.shape
                qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
                self.video_label.setPixmap(
                    QPixmap.fromImage(qt_img).scaled(
                        self.video_label.width(),
                        self.video_label.height(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                    )
                )
        except Exception as e:
            print(f"Video update error: {e}")

    def open_programs_folder(self):
        if os.path.exists(self.programs_dir):
            os.startfile(self.programs_dir)

    def action_start_recording(self):
        if self._recording:
            return
        session_dir = self._telemetry_session.start()
        self._recording_session_dir = session_dir
        self._recorded_frame_count = 0
        self._recording_h5_path = self._start_frame_recording()
        self._recording = True
        self.btn_rec_start.setEnabled(False)
        self.btn_rec_stop.setEnabled(True)
        self.lbl_recording.setText(
            f"Recording…\n{session_dir}\ntelemetry.csv (one row per MCU telemetry sample)"
        )
        frame_line = (
            f"frames: {self._recording_h5_path}"
            if self._recording_h5_path
            else "frames: not recording (camera/HDF5 unavailable)"
        )
        self.lbl_recording.setText(
            f"Recording...\n{session_dir}\ntelemetry.csv\n{frame_line}"
        )
        self.lbl_recording.setStyleSheet("color: #2ecc71; font-size: 8pt;")
        print(f"Data recording started: {session_dir}")

    def action_stop_recording(self):
        if not self._recording:
            return
        frame_count = self._stop_frame_recording()
        self._telemetry_session.stop(frame_count=frame_count)
        self._recording = False
        self.btn_rec_start.setEnabled(True)
        self.btn_rec_stop.setEnabled(False)
        self.lbl_recording.setText(
            "Recording stopped. Telemetry is not saved until you start again.\n"
            f"Last / default folder: {self.programs_dir}"
        )
        self.lbl_recording.setStyleSheet("color: #aaaaaa; font-size: 8pt;")
        print(f"Data recording stopped ({frame_count} frames).")

    def _start_frame_recording(self) -> str:
        if not self.camera_connected:
            print("Data recording: camera not connected - HDF5 frames disabled.")
            return ""
        if not self._telemetry_session.frames_dir:
            print("Data recording: session folder not ready - HDF5 frames disabled.")
            return ""

        writer = ScanWriter(
            self._telemetry_session.frames_dir,
            frame_h=CAMERA_CAPTURE_HEIGHT,
            frame_w=CAMERA_CAPTURE_WIDTH,
        )
        h5_path = writer.open_session(session_label="camera")
        if not h5_path:
            return ""

        capture_thread = CaptureThread(
            self.camera_manager,
            writer,
            get_height_mm=lambda: self.current_motor_mm,
            get_time_s=self._telemetry_session.elapsed_s,
        )
        capture_thread.frame_captured.connect(self._on_frame_captured)
        capture_thread.error_occurred.connect(self._on_frame_capture_error)
        capture_thread.start_capture()

        self._scan_writer = writer
        self._capture_thread = capture_thread
        return h5_path

    def _stop_frame_recording(self) -> int:
        if self._capture_thread is not None:
            self._capture_thread.stop_capture()
            self._capture_thread = None

        frame_count = self._recorded_frame_count
        if self._scan_writer is not None:
            frame_count = self._scan_writer.frame_count
            self._scan_writer.close_session()
            self._scan_writer = None
        return frame_count

    def _on_frame_captured(self, index: int, height_mm: float):
        self._recorded_frame_count = int(index) + 1
        if self._recorded_frame_count % 30 != 0:
            return
        if self._recording_session_dir:
            self.lbl_recording.setText(
                f"Recording...\n{self._recording_session_dir}\n"
                f"telemetry.csv\nframes: {self._recorded_frame_count} -> {self._recording_h5_path}"
            )

    def _on_frame_capture_error(self, message: str):
        print(f"Data recording frame capture error: {message}")

    def _handle_telemetry(self, ts, state, flow1, total1, pos):
        flow2 = 0
        motor_steps = int(pos)
        self._mcu_state = int(state)

        try:
            mcu = self.comms.get_mcu()
            latest = mcu.get_latest_telemetry() if mcu else None
            if latest:
                self._mcu_state = int(latest.get("state", state))
                flow1 = latest.get("flow1", flow1)
                flow2 = latest.get("flow2", flow2)
                motor_steps = int(latest.get("stepper_pos", motor_steps))
        except Exception:
            pass

        _t, motor_mm = self.dashboard.add_telemetry_point(
            ts_ms=ts,
            motor_steps=motor_steps,
            flow1_ml_min=flow1,
            flow2_ml_min=flow2,
        )
        self.current_motor_mm = motor_mm
        if self._recording and self._telemetry_session.is_active:
            self._telemetry_session.log_sample(
                motor_mm=motor_mm,
                motor_steps=motor_steps,
                flow_inj_ml_min=float(flow1),
                flow_main_ml_min=float(flow2),
                pump_rpm=0.0,
                mcu_state=self._mcu_state,
            )
        self._update_laser_line(motor_mm)
        self._update_mcu_status_label()

    def _comms_ok(self):
        return bool(getattr(self.comms, "mcu", None) or getattr(self.comms, "_ser", None))

    def action_set_zero(self):
        self.stop_any_run()
        if self._comms_ok():
            self.comms.send_set_zero(slave_addr=0x03)

    def action_middle(self):
        self.stop_any_run()
        if self._comms_ok():
            self.comms.send_set_middle()

    def action_set_position(self):
        self.stop_any_run()
        target_mm = self.spin_target.value()
        if self._comms_ok():
            self.comms.send_move_to(CommsManager.mm_to_steps(target_mm))

    def action_set_flow_immediate(self):
        if self._comms_ok():
            ml_per_min = int(self.spin_flow_immediate.value())
            self.comms.send_desired_flow(ml_per_min, immediate=True)
            print(f"CommsManager: desired flow {ml_per_min} mL/min (immediate)")

    def action_set_flow_delayed(self):
        if self._comms_ok():
            ml_per_min = int(self.spin_flow_delayed.value())
            self.comms.send_desired_flow(ml_per_min, immediate=False)
            print(f"CommsManager: desired flow {ml_per_min} mL/min (scheduled)")

    def action_run_dynamic_toggle(self):
        if self.is_running_static:
            return
        if not self.is_running_dynamic:
            self.is_running_dynamic = True
            if self._comms_ok():
                self.comms.send_stepper_oscillate_start(low_mm=150.0, high_mm=225.0)
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
        was_running = self.is_running_dynamic or self.is_running_static
        self.is_running_dynamic = False
        self.is_running_static = False
        if was_running and self._comms_ok():
            self.comms.send_stepper_oscillate_stop()
        self.btn_dynamic.setText("Run Dynamic")
        self.btn_dynamic.setStyleSheet(self.STYLE_GREEN)
        self.btn_dynamic.setEnabled(True)
        self.btn_static.setText("Run Static")
        self.btn_static.setStyleSheet(self.STYLE_PURPLE)
        self.btn_static.setEnabled(True)
        self.update_status(lasers_on=False, valve_on=False)

    def closeEvent(self, event):
        if self._recording:
            self.action_stop_recording()
        if self.is_running_dynamic or self.is_running_static:
            self.stop_any_run()
        if hasattr(self, "video_timer"):
            self.video_timer.stop()
        if hasattr(self, "comms") and self.comms:
            self.comms.close()
        if hasattr(self, "camera_manager") and self.camera_manager:
            self.camera_manager.close_camera()
        event.accept()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RPV Laser Scanner Control System GUI")
    parser.add_argument(
        "-p",
        "--port",
        default=comms_mod.SERIAL_PORT,
        help=f"Serial port (default: {comms_mod.SERIAL_PORT})",
    )
    parser.add_argument("-b", "--baud", default=None, help="Optional ba ud rate override")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow(comms_port=args.port)
    window.show()
    sys.exit(app.exec())
