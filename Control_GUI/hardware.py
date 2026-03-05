# Control_GUI/hardware.py
"""
Hardware abstraction layer.

Classes:
  DataGeneratorThread  — simulation data generator (runs when no real comms)
  ZWOCameraManager     — ZWO ASI camera wrapper (uses ASICamera2.dll via zwoasi)
  ScanWriter           — HDF5 session writer for continuous frame capture
  CaptureThread        — background thread that pulls frames and writes to ScanWriter
"""

import os
import time
import random
import threading
import datetime

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, QMutex

# ── Optional imports — graceful degradation if libraries missing ──────────────
try:
    import zwoasi as asi
    _ZWO_AVAILABLE = True
except ImportError:
    asi = None
    _ZWO_AVAILABLE = False

try:
    import h5py
    _H5PY_AVAILABLE = True
except ImportError:
    h5py = None
    _H5PY_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
# DataGeneratorThread — simulation / no-hardware mode
# ══════════════════════════════════════════════════════════════════════════════

# --- Configuration ---
UNITS_PER_MM       = 1638.4
MIN_ENCODER_VAL    = int(10  * UNITS_PER_MM)
MAX_ENCODER_VAL    = int(140 * UNITS_PER_MM)
MIDDLE_ENCODER_VAL = int(75  * UNITS_PER_MM)

WAVE_VELOCITY = (MAX_ENCODER_VAL - MIN_ENCODER_VAL) / 1.0
JOG_VELOCITY  = WAVE_VELOCITY * 0.5

# Sensor defaults
PUMP_MID         = 500
PUMP_NOISE       = 50
FLOW_INJ_MID     = 1250
FLOW_INJ_NOISE   = 125
FLOW_MAIN_DEFAULT = 2500
FLOW_MAIN_NOISE  = 250

# Timing
PHYSICS_TICK_MS = 1
GUI_FPS         = 30

# Motor states
STATE_HOLD        = 0
STATE_LINEAR_MOVE = 1
STATE_WAVE_RUN    = 2
MOTOR_NOISE_RANGE = 15


class DataGeneratorThread(QThread):
    """
    Simulates motor, pump, and flowmeter data at PHYSICS_TICK_MS resolution,
    batching results and emitting at GUI_FPS for smooth plotting.
    Used automatically when no real MCU comms are available.
    """
    data_generated = pyqtSignal(list, list, list, list, list)

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.mutex = QMutex()

        self.start_time        = 0.0
        self.last_physics_time = 0.0

        # Motor state
        self.motor_val      = float(MIN_ENCODER_VAL)
        self.motor_target   = float(MIN_ENCODER_VAL)
        self.mode           = STATE_HOLD
        self.wave_direction = 1

        # Flow state
        self.flow_setpoint          = float(FLOW_MAIN_DEFAULT)
        self.pending_flow_setpoint  = None
        self.flow_delay_expiry      = 0.0

    def set_command(self, command, value=None, extra=None):
        self.mutex.lock()
        try:
            if command == "HOME":
                self.mode         = STATE_LINEAR_MOVE
                self.motor_target = MIN_ENCODER_VAL

            elif command == "MIDDLE":
                self.mode         = STATE_LINEAR_MOVE
                self.motor_target = MIDDLE_ENCODER_VAL

            elif command == "MOVE_TO":
                if value is not None:
                    self.mode         = STATE_LINEAR_MOVE
                    target_encoder    = value * UNITS_PER_MM
                    self.motor_target = max(0, min(target_encoder, 150 * UNITS_PER_MM))

            elif command == "SET_FLOW_IMMEDIATE":
                if value is not None:
                    self.flow_setpoint = value * 60.0

            elif command == "SET_FLOW_DELAYED":
                if value is not None and extra is not None:
                    self.pending_flow_setpoint = value * 60.0
                    self.flow_delay_expiry     = time.perf_counter() + (extra / 1000.0)

            elif command == "RUN_DYNAMIC":
                self.mode           = STATE_WAVE_RUN
                self.wave_direction = 1

            elif command == "STOP":
                self.mode                  = STATE_HOLD
                self.motor_target          = self.motor_val
                self.pending_flow_setpoint = None
        finally:
            self.mutex.unlock()

    def run(self):
        self.start_time        = time.perf_counter()
        self.last_physics_time = self.start_time
        last_gui_update        = self.start_time

        buf_time, buf_motor, buf_inj, buf_main, buf_pump = [], [], [], [], []

        while self.is_running:
            current_time           = time.perf_counter()
            dt                     = current_time - self.last_physics_time
            self.last_physics_time = current_time
            elapsed                = current_time - self.start_time

            self.mutex.lock()
            try:
                # Delayed flow
                if self.pending_flow_setpoint is not None:
                    if current_time >= self.flow_delay_expiry:
                        self.flow_setpoint         = self.pending_flow_setpoint
                        self.pending_flow_setpoint = None

                # Motor physics
                if self.mode == STATE_LINEAR_MOVE:
                    step = JOG_VELOCITY * dt
                    diff = self.motor_target - self.motor_val
                    if abs(diff) <= step:
                        self.motor_val = self.motor_target
                        self.mode      = STATE_HOLD
                    else:
                        self.motor_val += step * (1 if diff > 0 else -1)

                elif self.mode == STATE_WAVE_RUN:
                    self.motor_val += WAVE_VELOCITY * dt * self.wave_direction
                    if self.motor_val >= MAX_ENCODER_VAL:
                        self.motor_val      = MAX_ENCODER_VAL
                        self.wave_direction = -1
                    elif self.motor_val <= MIN_ENCODER_VAL:
                        self.motor_val      = MIN_ENCODER_VAL
                        self.wave_direction = 1

                flow_setpoint_snap = self.flow_setpoint
                motor_snap         = self.motor_val
            finally:
                self.mutex.unlock()

            # Sensor noise
            val_pump      = PUMP_MID      + random.uniform(-PUMP_NOISE,      PUMP_NOISE)
            val_flow_inj  = FLOW_INJ_MID  + random.uniform(-FLOW_INJ_NOISE,  FLOW_INJ_NOISE)
            val_flow_main = max(0, flow_setpoint_snap + random.uniform(-FLOW_MAIN_NOISE, FLOW_MAIN_NOISE))
            noisy_motor   = int(motor_snap + random.randint(-MOTOR_NOISE_RANGE, MOTOR_NOISE_RANGE))

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


# ══════════════════════════════════════════════════════════════════════════════
# ZWOCameraManager — ZWO ASI camera wrapper
# ══════════════════════════════════════════════════════════════════════════════

# Camera settings — adjust to match your ASI camera model
CAMERA_EXPOSURE_US  = 10000   # 10 ms
CAMERA_GAIN         = 200
CAMERA_WB_R         = 70
CAMERA_WB_B         = 90
CAMERA_BANDWIDTH    = 80      # %
CAMERA_IMAGE_TYPE   = None    # set after init from camera caps


class ZWOCameraManager:
    """
    Wraps the ZWO ASI camera SDK (via the zwoasi Python binding).
    Falls back gracefully if the DLL or library is not available,
    so the rest of the GUI still runs without a camera attached.
    """

    def __init__(self, dll_path: str = ""):
        self._camera    = None
        self._connected = False
        self._dll_path  = dll_path
        self._lock      = threading.Lock()

        if not _ZWO_AVAILABLE:
            print("ZWOCameraManager: zwoasi not installed — camera disabled.")
            return

        if dll_path and os.path.exists(dll_path):
            try:
                asi.init(dll_path)
            except Exception as e:
                print(f"ZWOCameraManager: asi.init failed: {e}")

    def open_camera(self) -> bool:
        """Open the first available ZWO camera. Returns True on success."""
        if not _ZWO_AVAILABLE:
            return False
        try:
            num = asi.get_num_cameras()
            if num == 0:
                print("ZWOCameraManager: no cameras found.")
                return False

            cameras = asi.list_cameras()
            print(f"ZWOCameraManager: found {num} camera(s): {cameras}")

            self._camera = asi.Camera(0)
            info         = self._camera.get_camera_property()
            print(f"ZWOCameraManager: opened '{info['Name']}'")

            # Apply settings
            self._camera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, CAMERA_BANDWIDTH)
            self._camera.disable_dark_subtract()
            self._camera.set_control_value(asi.ASI_GAIN,       CAMERA_GAIN,        auto=False)
            self._camera.set_control_value(asi.ASI_EXPOSURE,   CAMERA_EXPOSURE_US, auto=False)
            self._camera.set_control_value(asi.ASI_WB_R,       CAMERA_WB_R,        auto=False)
            self._camera.set_control_value(asi.ASI_WB_B,       CAMERA_WB_B,        auto=False)
            self._camera.set_control_value(asi.ASI_FLIP,       0,                  auto=False)
            self._camera.set_image_type(asi.ASI_IMG_RAW8)

            self._camera.start_video_capture()
            self._connected = True
            return True

        except Exception as e:
            print(f"ZWOCameraManager: open_camera error: {e}")
            self._camera    = None
            self._connected = False
            return False

    def get_frame(self):
        """
        Capture one frame from the live video stream.
        Returns (frame: np.ndarray | None, timestamp: float).
        """
        if not self._connected or self._camera is None:
            return None, time.time()
        try:
            with self._lock:
                frame = self._camera.capture_video_frame(timeout=500)
            return frame, time.time()
        except Exception as e:
            print(f"ZWOCameraManager: get_frame error: {e}")
            return None, time.time()

    def capture_image(self, motor_height: str = "0.00", folder: str = "."):
        """
        Save a single JPEG snapshot with timestamp and height in the filename.
        Used by the manual SNAP PHOTO button.
        """
        frame, ts = self.get_frame()
        if frame is None:
            print("ZWOCameraManager: capture_image — no frame available.")
            return None

        import cv2
        ts_str   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"snap_{ts_str}_z{motor_height}mm.jpg"
        filepath = os.path.join(folder, filename)
        try:
            cv2.imwrite(filepath, frame)
            print(f"ZWOCameraManager: saved snap -> {filepath}")
            return filepath
        except Exception as e:
            print(f"ZWOCameraManager: capture_image write error: {e}")
            return None

    def close_camera(self):
        if self._camera is not None:
            try:
                self._camera.stop_video_capture()
                self._camera.close()
            except Exception:
                pass
            self._camera    = None
            self._connected = False
            print("ZWOCameraManager: camera closed.")


# ══════════════════════════════════════════════════════════════════════════════
# ScanWriter — HDF5 session writer
# ══════════════════════════════════════════════════════════════════════════════

class ScanWriter:
    """
    Writes captured frames into an HDF5 file as an appendable dataset.

    File structure:
        /frames         — dataset (N, H, W) uint8, resizable
        /timestamps     — dataset (N,) float64, Unix time
        /heights_mm     — dataset (N,) float32, motor position at capture
        /metadata       — attributes: session_start, frame_h, frame_w
    """

    def __init__(self, output_dir: str, frame_h: int = 1080, frame_w: int = 1920):
        self._dir     = output_dir
        self._frame_h = frame_h
        self._frame_w = frame_w
        self._file    = None
        self._ds_frames = None
        self._ds_ts     = None
        self._ds_heights = None
        self._count   = 0
        self.is_open  = False

    def open_session(self) -> str:
        """Open a new HDF5 file for this scan session. Returns the file path."""
        if not _H5PY_AVAILABLE:
            print("ScanWriter: h5py not installed — scan writing disabled.")
            return ""
        ts_str   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self._dir, f"scan_{ts_str}.h5")
        try:
            self._file = h5py.File(filepath, "w")
            self._ds_frames = self._file.create_dataset(
                "frames",
                shape=(0, self._frame_h, self._frame_w),
                maxshape=(None, self._frame_h, self._frame_w),
                dtype=np.uint8,
                chunks=(1, self._frame_h, self._frame_w),
                compression="gzip", compression_opts=1,
            )
            self._ds_ts = self._file.create_dataset(
                "timestamps", shape=(0,), maxshape=(None,), dtype=np.float64)
            self._ds_heights = self._file.create_dataset(
                "heights_mm",  shape=(0,), maxshape=(None,), dtype=np.float32)
            self._file.attrs["session_start"] = ts_str
            self._file.attrs["frame_h"]       = self._frame_h
            self._file.attrs["frame_w"]       = self._frame_w
            self._count  = 0
            self.is_open = True
            print(f"ScanWriter: session opened -> {filepath}")
            return filepath
        except Exception as e:
            print(f"ScanWriter: open_session error: {e}")
            self.is_open = False
            return ""

    def write_frame(self, frame: np.ndarray, height_mm: float, timestamp: float = None):
        """Append one frame to the open session."""
        if not self.is_open or self._file is None:
            return
        if timestamp is None:
            timestamp = time.time()
        try:
            n = self._count + 1
            self._ds_frames.resize((n, self._frame_h, self._frame_w))
            self._ds_ts.resize((n,))
            self._ds_heights.resize((n,))

            # Resize frame if needed
            h, w = frame.shape[:2]
            if h != self._frame_h or w != self._frame_w:
                import cv2
                frame = cv2.resize(frame, (self._frame_w, self._frame_h))

            if frame.ndim == 3:
                import cv2
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            self._ds_frames[self._count]  = frame
            self._ds_ts[self._count]      = timestamp
            self._ds_heights[self._count] = height_mm
            self._count += 1
        except Exception as e:
            print(f"ScanWriter: write_frame error: {e}")

    def close_session(self):
        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            except Exception:
                pass
            self._file   = None
            self.is_open = False
            print(f"ScanWriter: session closed ({self._count} frames written).")
        self._count = 0


# ══════════════════════════════════════════════════════════════════════════════
# CaptureThread — background frame capture
# ══════════════════════════════════════════════════════════════════════════════

class CaptureThread(QThread):
    """
    Continuously pulls frames from ZWOCameraManager and passes them to
    ScanWriter on a background thread so the GUI stays responsive.

    Signals:
        frame_captured(index: int, height_mm: float)  — emitted every frame
        error_occurred(message: str)                  — emitted on exception
    """
    frame_captured = pyqtSignal(int, float)
    error_occurred = pyqtSignal(str)

    def __init__(self, camera: ZWOCameraManager, writer: ScanWriter):
        super().__init__()
        self._camera     = camera
        self._writer     = writer
        self._active     = False
        self._height_mm  = 0.0
        self._lock       = threading.Lock()

    def set_height(self, height_mm: float):
        """Update the height tag written to the next frames."""
        with self._lock:
            self._height_mm = float(height_mm)

    def start_capture(self):
        self._active = True
        self.start()

    def stop_capture(self):
        self._active = False
        self.wait(2000)

    def run(self):
        index = 0
        while self._active:
            try:
                frame, ts = self._camera.get_frame()
                if frame is None:
                    self.msleep(10)
                    continue

                with self._lock:
                    h = self._height_mm

                self._writer.write_frame(frame, height_mm=h, timestamp=ts)
                self.frame_captured.emit(index, h)
                index += 1

            except Exception as e:
                self.error_occurred.emit(str(e))
                self.msleep(100)