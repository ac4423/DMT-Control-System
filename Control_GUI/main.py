import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                             QPushButton, QHBoxLayout, QGroupBox, QDoubleSpinBox, 
                             QSpinBox, QLabel, QGridLayout)
from PyQt6.QtCore import Qt, QTimer
from hardware import DataGeneratorThread
from displays import DashboardWidget
from comms_manager import CommsManager 

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RPV Laser Scanner Control System")
        self.resize(1280, 900)
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; color: white; }
            QGroupBox { 
                font-weight: bold; border: 1px solid #555; border-radius: 6px; 
                margin-top: 10px; padding-top: 15px; color: #ddd; 
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLabel { color: #ccc; }
            QDoubleSpinBox, QSpinBox { 
                padding: 5px; background-color: #444; color: white; border: 1px solid #666; border-radius: 3px;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0px; }
        """)

        # --- Styles ---
        self.STYLE_BTN_NORMAL = """
            QPushButton { padding: 8px; border-radius: 4px; background-color: #34495e; color: white; }
            QPushButton:pressed { background-color: #2c3e50; }
        """
        self.STYLE_BTN_ACTION = """
            QPushButton { padding: 8px; border-radius: 4px; background-color: #3498db; color: white; font-weight: bold; }
            QPushButton:pressed { background-color: #1f618d; } 
        """
        self.STYLE_GREEN  = "font-size: 11pt; padding: 12px; border-radius: 5px; color: white; background-color: #2ecc71; font-weight: bold;"
        self.STYLE_RED    = "font-size: 11pt; padding: 12px; border-radius: 5px; color: white; background-color: #e74c3c; font-weight: bold;"
        self.STYLE_PURPLE = "font-size: 11pt; padding: 12px; border-radius: 5px; color: white; background-color: #9b59b6; font-weight: bold;"
        self.STYLE_GREY   = "font-size: 11pt; padding: 12px; border-radius: 5px; color: white; background-color: #7f8c8d;"

        # --- Layout Setup ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left Panel
        left_panel = QWidget()
        left_panel.setFixedWidth(340)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 10, 0)

        self.create_stepper_group(left_layout)
        self.create_flow_group(left_layout)
        left_layout.addStretch()
        self.create_run_group(left_layout)
        main_layout.addWidget(left_panel)

        # Right Panel
        self.dashboard = DashboardWidget()
        main_layout.addWidget(self.dashboard, stretch=1) 

        # Hardware & Comms
        self.is_running_dynamic = False
        self.is_running_static = False
        
        self.generator = DataGeneratorThread()
        self.generator.data_generated.connect(self.dashboard.update_plots)
        self.generator.start()

        self.comms = CommsManager() 

    # --- UI Helpers (Unchanged) ---
    def create_stepper_group(self, layout):
        grp = QGroupBox("Stepper Motor Control")
        g_layout = QGridLayout()
        
        self.btn_home = QPushButton("Home (0mm)")
        self.btn_home.setStyleSheet(self.STYLE_BTN_NORMAL)
        self.btn_home.clicked.connect(self.action_home)
        
        self.btn_middle = QPushButton("Middle (75mm)")
        self.btn_middle.setStyleSheet(self.STYLE_BTN_NORMAL)
        self.btn_middle.clicked.connect(self.action_middle)

        lbl_setpos = QLabel("Set Pos:")
        self.spin_target = QDoubleSpinBox()
        self.spin_target.setRange(0.0, 150.0)
        self.spin_target.setDecimals(1)
        self.spin_target.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        lbl_unit = QLabel("mm")
        
        self.btn_set_pos = QPushButton("Set")
        self.btn_set_pos.setFixedWidth(60)
        self.btn_set_pos.setStyleSheet(self.STYLE_BTN_ACTION)
        self.btn_set_pos.clicked.connect(self.action_set_position)

        g_layout.addWidget(self.btn_home, 0, 0, 1, 2)
        g_layout.addWidget(self.btn_middle, 0, 2, 1, 2)
        g_layout.addWidget(lbl_setpos, 1, 0)
        g_layout.addWidget(self.spin_target, 1, 1)
        g_layout.addWidget(lbl_unit, 1, 2)
        g_layout.addWidget(self.btn_set_pos, 1, 3)

        grp.setLayout(g_layout)
        layout.addWidget(grp)

    def create_flow_group(self, layout):
        grp = QGroupBox("Flow Control")
        v_layout = QVBoxLayout()

        sub_curr = QGroupBox("Current Set Flow")
        curr_layout = QGridLayout()
        lbl_curr_rate = QLabel("Set Rate:")
        self.spin_flow_immediate = QDoubleSpinBox()
        self.spin_flow_immediate.setRange(0.0, 100.0)
        self.spin_flow_immediate.setValue(41.6)
        self.spin_flow_immediate.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        lbl_unit_curr = QLabel("mL/s")
        self.btn_set_flow = QPushButton("Set")
        self.btn_set_flow.setFixedWidth(60)
        self.btn_set_flow.setStyleSheet(self.STYLE_BTN_ACTION)
        self.btn_set_flow.clicked.connect(self.action_set_flow_immediate)
        curr_layout.addWidget(lbl_curr_rate, 0, 0)
        curr_layout.addWidget(self.spin_flow_immediate, 0, 1)
        curr_layout.addWidget(lbl_unit_curr, 0, 2)
        curr_layout.addWidget(self.btn_set_flow, 0, 3)
        sub_curr.setLayout(curr_layout)
        v_layout.addWidget(sub_curr)

        sub_del = QGroupBox("Delay Set Flow")
        del_layout = QGridLayout()
        lbl_del_flow = QLabel("Set Rate:")
        self.spin_flow_delayed = QDoubleSpinBox()
        self.spin_flow_delayed.setRange(0.0, 100.0)
        self.spin_flow_delayed.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        lbl_unit_del_flow = QLabel("mL/s")
        lbl_del_time = QLabel("Set Delay:")
        self.spin_delay_ms = QSpinBox()
        self.spin_delay_ms.setRange(0, 10000)
        self.spin_delay_ms.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.spin_delay_ms.setValue(1000)
        lbl_unit_del_time = QLabel("ms")
        self.btn_set_delay = QPushButton("Set")
        self.btn_set_delay.setStyleSheet(self.STYLE_BTN_ACTION)
        self.btn_set_delay.clicked.connect(self.action_set_flow_delayed)
        del_layout.addWidget(lbl_del_flow, 0, 0)
        del_layout.addWidget(self.spin_flow_delayed, 0, 1)
        del_layout.addWidget(lbl_unit_del_flow, 0, 2)
        del_layout.addWidget(lbl_del_time, 1, 0)
        del_layout.addWidget(self.spin_delay_ms, 1, 1)
        del_layout.addWidget(lbl_unit_del_time, 1, 2)
        del_layout.addWidget(self.btn_set_delay, 2, 0, 1, 3)
        sub_del.setLayout(del_layout)
        v_layout.addWidget(sub_del)

        grp.setLayout(v_layout)
        layout.addWidget(grp)

    def create_run_group(self, layout):
        grp = QGroupBox("Experiment Controls")
        run_layout = QVBoxLayout()

        self.btn_dynamic = QPushButton("Run Dynamic")
        self.btn_dynamic.setStyleSheet(self.STYLE_GREEN)
        self.btn_dynamic.clicked.connect(self.action_run_dynamic_toggle)
        
        self.btn_static = QPushButton("Run Static")
        self.btn_static.setStyleSheet(self.STYLE_PURPLE)
        self.btn_static.clicked.connect(self.action_run_static_toggle)

        run_layout.addWidget(self.btn_dynamic)
        run_layout.addWidget(self.btn_static)
        grp.setLayout(run_layout)
        layout.addWidget(grp)

    # ==========================================================
    # ACTIONS
    # ==========================================================

    def action_home(self):
        self.stop_any_run()
        self.generator.set_command("HOME")
        self.comms.send_go_home(slave_addr=0x03)

    def action_middle(self):
        self.stop_any_run()
        self.generator.set_command("MIDDLE")
        self.comms.send_set_middle()

    def action_set_position(self):
        """
        Calculates steps based on mm input and sends command.
        Formula: (mm / 10) * 360 / 1.8
        """
        self.stop_any_run()
        target_mm = self.spin_target.value()
        
        # 1. Update Simulation (Graph)
        self.generator.set_command("MOVE_TO", value=target_mm)

        # 2. Calculate Steps
        # (mm -> cm) * (360 degrees/cm) / (1.8 degrees/step)
        steps = (target_mm / 10.0) * 360.0 / 1.8
        
        # 3. Send Serial Command
        self.comms.send_move_to(steps)

    def action_set_flow_immediate(self):
        val = self.spin_flow_immediate.value()
        self.generator.set_command("SET_FLOW_IMMEDIATE", value=val)

    def action_set_flow_delayed(self):
        rate = self.spin_flow_delayed.value()
        delay = self.spin_delay_ms.value()
        self.generator.set_command("SET_FLOW_DELAYED", value=rate, extra=delay)

    def action_run_dynamic_toggle(self):
        if self.is_running_static: return 
        if not self.is_running_dynamic:
            self.is_running_dynamic = True
            self.generator.set_command("RUN_DYNAMIC")
            self.btn_dynamic.setText("Stop Dynamic")
            self.btn_dynamic.setStyleSheet(self.STYLE_RED)
            self.btn_static.setEnabled(False) 
            self.btn_static.setStyleSheet(self.STYLE_GREY)
            self.dashboard.update_status(lasers_on=True, valve_on=True)
        else:
            self.stop_any_run()

    def action_run_static_toggle(self):
        if self.is_running_dynamic: return
        if not self.is_running_static:
            self.is_running_static = True
            self.btn_static.setText("Stop Static")
            self.btn_static.setStyleSheet(self.STYLE_RED)
            self.btn_dynamic.setEnabled(False) 
            self.btn_dynamic.setStyleSheet(self.STYLE_GREY)
            self.dashboard.update_status(lasers_on=True, valve_on=True)
        else:
            self.stop_any_run()

    def stop_any_run(self):
        self.is_running_dynamic = False
        self.is_running_static = False
        self.generator.set_command("STOP")
        self.btn_dynamic.setText("Run Dynamic")
        self.btn_dynamic.setStyleSheet(self.STYLE_GREEN)
        self.btn_dynamic.setEnabled(True)
        self.btn_static.setText("Run Static")
        self.btn_static.setStyleSheet(self.STYLE_PURPLE)
        self.btn_static.setEnabled(True)
        self.dashboard.update_status(lasers_on=False, valve_on=False)

    def closeEvent(self, event):
        self.comms.close()
        self.generator.stop()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())