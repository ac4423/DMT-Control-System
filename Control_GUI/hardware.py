# Control_GUI/hardware.py
"""
Hardware abstraction layer.

Classes:
  DataGeneratorThread  — simulation data generator (runs when no real comms)
  ZWOCameraManager     — ZWO ASI camera wrapper (uses ASICamera2.dll via zwoasi)
  ScanWriter           — HDF5 session writer for continuous frame capture
  CaptureThread        — background thread that pulls frames and writes to ScanWriter
"""

import csv
import json
import os
import time
import threading
import datetime
import logging
logging.getLogger("zwoasi").setLevel(logging.ERROR)
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
logging.disable(logging.WARNING)  # add this just before `import zwoasi`
logging.disable(logging.NOTSET)   # re-enable immediately after
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

class ProgramSession:
    """Manage one timestamped program folder and its CSV telemetry log."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.session_dir = None
        self.frames_dir = None
        self.csv_path = None
        self.meta_path = None
        self.t0_perf = None
        self.t0_wall = None
        self.is_active = False
        self._csv_file = None
        self._writer = None
        os.makedirs(self.root_dir, exist_ok=True)

    def start(self) -> str:
        if self.is_active:
            return self.session_dir

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = os.path.join(self.root_dir, f"program_{stamp}")
        self.frames_dir = os.path.join(self.session_dir, "frames")
        os.makedirs(self.frames_dir, exist_ok=True)

        self.csv_path = os.path.join(self.session_dir, "telemetry.csv")
        self.meta_path = os.path.join(self.session_dir, "metadata.json")
        self.t0_perf = time.perf_counter()
        self.t0_wall = time.time()
        self._csv_file = open(self.csv_path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(
            self._csv_file,
            fieldnames=[
                "time_s", "wall_time", "motor_mm", "motor_steps",
                "flow_inj_ml_min", "flow_main_ml_min", "pump_rpm", "mcu_state",
            ],
        )
        self._writer.writeheader()
        self.is_active = True
        return self.session_dir

    def elapsed_s(self) -> float:
        if self.t0_perf is None:
            return 0.0
        return time.perf_counter() - self.t0_perf

    def log_sample(
        self,
        motor_mm: float,
        motor_steps: int = 0,
        flow_inj_ml_min: float = 0.0,
        flow_main_ml_min: float = 0.0,
        pump_rpm: float = 0.0,
        mcu_state: int = 0,
        time_s: float | None = None,
    ):
        if not self.is_active or self._writer is None:
            return
        if time_s is None:
            time_s = self.elapsed_s()
        self._writer.writerow({
            "time_s": float(time_s),
            "wall_time": time.time(),
            "motor_mm": float(motor_mm),
            "motor_steps": int(motor_steps),
            "flow_inj_ml_min": float(flow_inj_ml_min),
            "flow_main_ml_min": float(flow_main_ml_min),
            "pump_rpm": float(pump_rpm),
            "mcu_state": int(mcu_state),
        })

    def stop(self, frame_count: int = 0):
        if self._csv_file is not None:
            try:
                self._csv_file.flush()
                self._csv_file.close()
            finally:
                self._csv_file = None
                self._writer = None

        if self.session_dir:
            meta = {
                "session_dir": self.session_dir,
                "started_wall_time": self.t0_wall,
                "duration_s": self.elapsed_s(),
                "frame_count": int(frame_count),
                "telemetry_csv": self.csv_path,
            }
            try:
                with open(self.meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception as e:
                print(f"ProgramSession: metadata write error: {e}")

        self.is_active = False


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
        self._ds_time_s = None
        self._ds_heights = None
        self._count   = 0
        self.is_open  = False

    def open_session(self, output_dir: str | None = None, session_label: str = "scan") -> str:
        """Open a new HDF5 file for this scan session. Returns the file path."""
        if not _H5PY_AVAILABLE:
            print("ScanWriter: h5py not installed — scan writing disabled.")
            return ""
        if output_dir is not None:
            self._dir = output_dir
        os.makedirs(self._dir, exist_ok=True)
        ts_str   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self._dir, f"{session_label}_{ts_str}.h5")
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
            self._ds_time_s = self._file.create_dataset(
                "time_s", shape=(0,), maxshape=(None,), dtype=np.float64)
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

    def write_frame(
        self,
        frame: np.ndarray,
        height_mm: float,
        timestamp: float = None,
        time_s: float | None = None,
    ):
        """Append one frame to the open session."""
        if not self.is_open or self._file is None:
            return
        if timestamp is None:
            timestamp = time.time()
        try:
            n = self._count + 1
            self._ds_frames.resize((n, self._frame_h, self._frame_w))
            self._ds_ts.resize((n,))
            self._ds_time_s.resize((n,))
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
            self._ds_time_s[self._count]  = np.nan if time_s is None else float(time_s)
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

    def __init__(
        self,
        camera: ZWOCameraManager,
        writer: ScanWriter,
        get_height_mm=None,
        get_time_s=None,
    ):
        super().__init__()
        self._camera     = camera
        self._writer     = writer
        self._active     = False
        self._height_mm  = 0.0
        self._get_height_mm = get_height_mm
        self._get_time_s = get_time_s
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

                if self._get_height_mm is not None:
                    h = float(self._get_height_mm())
                else:
                    with self._lock:
                        h = self._height_mm
                t_s = self._get_time_s() if self._get_time_s is not None else None

                self._writer.write_frame(frame, height_mm=h, timestamp=ts, time_s=t_s)
                self.frame_captured.emit(index, h)
                index += 1

            except Exception as e:
                self.error_occurred.emit(str(e))
                self.msleep(100)
