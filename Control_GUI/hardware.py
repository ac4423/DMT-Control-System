import time
import random
from PyQt6.QtCore import QThread, pyqtSignal, QMutex

# --- Configuration ---
UNITS_PER_MM = 1638.4
MIN_ENCODER_VAL = int(10 * UNITS_PER_MM)   
MAX_ENCODER_VAL = int(140 * UNITS_PER_MM)  
MIDDLE_ENCODER_VAL = int(75 * UNITS_PER_MM) 

WAVE_VELOCITY = (MAX_ENCODER_VAL - MIN_ENCODER_VAL) / 1.0 
JOG_VELOCITY = WAVE_VELOCITY * 0.5 

# Sensors Defaults
PUMP_MID = 500
PUMP_NOISE = 50
FLOW_INJ_MID = 1250
FLOW_INJ_NOISE = 125
FLOW_MAIN_DEFAULT = 2500 
FLOW_MAIN_NOISE = 250

# Timing
PHYSICS_TICK_MS = 1      
GUI_FPS = 30             

# States
STATE_HOLD = 0
STATE_LINEAR_MOVE = 1
STATE_WAVE_RUN = 2
MOTOR_NOISE_RANGE = 15

class DataGeneratorThread(QThread):
    data_generated = pyqtSignal(list, list, list, list, list)

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.mutex = QMutex()
        
        self.start_time = 0.0
        self.last_physics_time = 0.0
        
        # Motor State
        self.motor_val = float(MIN_ENCODER_VAL)
        self.motor_target = float(MIN_ENCODER_VAL)
        self.mode = STATE_HOLD
        self.wave_direction = 1 

        # Flow State
        self.flow_setpoint = FLOW_MAIN_DEFAULT 
        self.pending_flow_setpoint = None
        self.flow_delay_expiry = 0.0

    def set_command(self, command, value=None, extra=None):
        self.mutex.lock()
        
        if command == "HOME":
            self.mode = STATE_LINEAR_MOVE
            self.motor_target = MIN_ENCODER_VAL
        
        elif command == "MIDDLE":
            self.mode = STATE_LINEAR_MOVE
            self.motor_target = MIDDLE_ENCODER_VAL
            
        elif command == "MOVE_TO":
            if value is not None:
                self.mode = STATE_LINEAR_MOVE
                target_encoder = value * UNITS_PER_MM
                self.motor_target = max(0, min(target_encoder, 150 * UNITS_PER_MM))

        elif command == "SET_FLOW_IMMEDIATE":
            if value is not None:
                self.flow_setpoint = value * 60.0

        elif command == "SET_FLOW_DELAYED":
            if value is not None and extra is not None:
                self.pending_flow_setpoint = value * 60.0
                self.flow_delay_expiry = time.perf_counter() + (extra / 1000.0)

        elif command == "RUN_DYNAMIC":
            self.mode = STATE_WAVE_RUN
            self.wave_direction = 1
            
        elif command == "STOP":
            self.mode = STATE_HOLD
            self.motor_target = self.motor_val 
            self.pending_flow_setpoint = None
            
        self.mutex.unlock()

    def run(self):
        self.start_time = time.perf_counter()
        self.last_physics_time = self.start_time
        last_gui_update = self.start_time
        
        buf_time, buf_motor, buf_inj, buf_main, buf_pump = [], [], [], [], []

        while self.is_running:
            current_time = time.perf_counter()
            dt = current_time - self.last_physics_time
            self.last_physics_time = current_time
            elapsed = current_time - self.start_time
            
            self.mutex.lock() 
            
            # Flow Delay Logic
            if self.pending_flow_setpoint is not None:
                if current_time >= self.flow_delay_expiry:
                    self.flow_setpoint = self.pending_flow_setpoint
                    self.pending_flow_setpoint = None
            
            # Motor Logic
            if self.mode == STATE_LINEAR_MOVE:
                step = JOG_VELOCITY * dt
                diff = self.motor_target - self.motor_val
                if abs(diff) <= step:
                    self.motor_val = self.motor_target
                    self.mode = STATE_HOLD
                else:
                    direction = 1 if diff > 0 else -1
                    self.motor_val += (step * direction)
            
            elif self.mode == STATE_WAVE_RUN:
                step = WAVE_VELOCITY * dt
                self.motor_val += (step * self.wave_direction)
                if self.motor_val >= MAX_ENCODER_VAL:
                    self.motor_val = MAX_ENCODER_VAL
                    self.wave_direction = -1 
                elif self.motor_val <= MIN_ENCODER_VAL:
                    self.motor_val = MIN_ENCODER_VAL
                    self.wave_direction = 1 
            
            self.mutex.unlock()

            # Sensors
            val_pump = PUMP_MID + random.uniform(-PUMP_NOISE, PUMP_NOISE)
            val_flow_inj = FLOW_INJ_MID + random.uniform(-FLOW_INJ_NOISE, FLOW_INJ_NOISE)
            val_flow_main = self.flow_setpoint + random.uniform(-FLOW_MAIN_NOISE, FLOW_MAIN_NOISE)
            val_flow_main = max(0, val_flow_main)
            
            noisy_motor = int(self.motor_val + random.randint(-MOTOR_NOISE_RANGE, MOTOR_NOISE_RANGE))

            buf_time.append(elapsed)
            buf_motor.append(noisy_motor)
            buf_inj.append(val_flow_inj)
            buf_main.append(val_flow_main)
            buf_pump.append(val_pump)

            if (current_time - last_gui_update) >= (1.0 / GUI_FPS):
                self.data_generated.emit(buf_time, buf_motor, buf_inj, buf_main, buf_pump)
                buf_time, buf_motor, buf_inj, buf_main, buf_pump = [], [], [], [], []
                last_gui_update = current_time

            self.msleep(PHYSICS_TICK_MS)

    def stop(self):
        self.is_running = False
        self.wait()