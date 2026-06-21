import sys
from pathlib import Path

import cv2
import h5py
import hdf5plugin  # noqa: F401 - registers compressed HDF5 filters
import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


TEST_RESULTS = [
    {
        "name": "Test 1 (1500ml/min)",
        "path": Path(r"E:\RPV Test\camera_20260601_151542_roi_masked_nlm_bgcomp_zstd9.h5"),
        "display_min": 35,
        "display_max": 85,
        "injection_time_s": 11.450753,
        "state_transition_times_s": (14.77, 18.25),
    },
    {
        "name": "Test 2 (1250ml/min)",
        "path": Path(r"E:\RPV Test\camera_20260601_145235_frames_2500_to_2600_roi_masked_nlm_bgcomp_zstd9.h5"),
        "display_min": 25,
        "display_max": 90,
        "injection_time_s": 13.276876,
        "state_transition_times_s": (15.31, 19.78),
    },
    {
        "name": "Test 3 (1000ml/min)",
        "path": Path(r"E:\RPV Test\camera_20260601_120151_roi_masked_nlm_bgcomp_zstd9_v3.h5"),
        "display_min": 20,
        "display_max": 90,
        "injection_time_s": 11.56,
        "state_transition_times_s": (13.77, 21.06),
    },
    {
        "name": "Test 4 (750ml/min)",
        "path": Path(r"E:\RPV Test\camera_20260601_141243_roi_masked_nlm_bgcomp_zstd9.h5"),
        "display_min": 30,
        "display_max": 90,
        "injection_time_s": 18.133829,
        "state_transition_times_s": (20.609, 29.58),
    },
    {
        "name": "Test 5 (500ml/min)",
        "path": Path(r"E:\RPV Test\camera_20260601_154017_from_3500_avg_5600_to_5900_roi_masked_nlm_bgcomp_zstd9.h5"),
        "display_min": 40,
        "display_max": 90,
        "injection_time_s": 5.097,
        "state_transition_times_s": (8.55, 17.21),
    },
]
OVERLAY_IMAGE_PATH = Path(r"E:\RPV Test\RPV Data Display\RPV Image\RPV_Silouette.png")

DISPLAY_SCALE = 0.3
DISPLAY_INTENSITY_MIN = 0
DISPLAY_INTENSITY_MAX = 90
ROI_CENTER_X = 545
ROI_CENTER_Y = 585
ROI_RADIUS = 445
ROI_ROTATION_DEG = 32
GUIDE_CIRCLE_RADIUS = 380
GLOBAL_ROI_CENTER_X = 545
GLOBAL_ROI_CENTER_Y = 585    
ROI_OUTLINE_COLOR_BGR = (0, 0, 0)
ROI_OUTLINE_THICKNESS = 3
OUTSIDE_ROI_COLOR_BGR = (0, 0, 0)

OVERLAY_X = 185
OVERLAY_Y = 250
OVERLAY_SCALE = 1.4
OVERLAY_ALPHA = 1.0

FRAMES_ALREADY_PROCESSED = True
SHOW_ROI_OUTLINE = True
SHOW_GUIDE_CIRCLE = True
SHOW_RPV_OVERLAY = False

DEFAULT_PLAY_FPS = 30.0
SPEED_OPTIONS = (1, 2, 5, 10)
POST_INJECTION_WINDOW_S = 20.0
MULTI_GRID_COLS = 3
MULTI_GRID_SPACING = 8
PANEL_LABEL_HEIGHT = 44


class ImageLabel(QLabel):
    mouse_moved = pyqtSignal(int, int)
    mouse_left = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position()
        self.mouse_moved.emit(int(pos.x()), int(pos.y()))

    def leaveEvent(self, event) -> None:
        self.mouse_left.emit()


def display_intensity_image(
    image: np.ndarray,
    low: float = DISPLAY_INTENSITY_MIN,
    high: float = DISPLAY_INTENSITY_MAX,
) -> np.ndarray:
    low = float(low)
    high = float(high)
    if high <= low:
        high = low + 1.0

    clipped = np.clip(image.astype(np.float32), low, high)
    return ((clipped - low) * (255.0 / (high - low))).astype(np.uint8)


def normalized_intensity(value: float, low: float, high: float) -> float:
    low = float(low)
    high = float(high)
    if high <= low:
        high = low + 1.0
    return float(np.clip((float(value) - low) / (high - low), 0.0, 1.0))


def make_intensity_legend(
    height: int,
    width: int = 75,
    low: float = DISPLAY_INTENSITY_MIN,
    high: float = DISPLAY_INTENSITY_MAX,
    normalized_labels: bool = True,
) -> np.ndarray:
    bar_width = 28
    tick_len = 8
    label_x = bar_width + tick_len + 8
    legend = np.zeros((height, width, 3), dtype=np.uint8)

    gradient = np.linspace(255, 0, height, dtype=np.uint8).reshape(height, 1)
    gradient = np.repeat(gradient, bar_width, axis=1)
    legend[:, :bar_width] = cv2.applyColorMap(gradient, cv2.COLORMAP_VIRIDIS)

    low = float(low)
    high = float(high)
    if high <= low:
        high = low + 1.0

    for normalized, value in zip(np.linspace(0.0, 1.0, 5), np.linspace(low, high, 5)):
        normalized = (float(value) - low) / max(1.0, high - low)
        y = int(round((1.0 - normalized) * (height - 1)))
        cv2.line(legend, (bar_width, y), (bar_width + tick_len, y), (255, 255, 255), 1)
        label_text = f"{normalized:.2g}" if normalized_labels else f"{value:.0f}"
        cv2.putText(
            legend,
            label_text,
            (label_x, min(height - 4, max(12, y + 5))),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    #legend_label = "N" if normalized_labels else "I"
    cv2.putText(legend, "", (label_x, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return legend


def make_roi_mask(
    shape: tuple[int, int],
    scale: float = 1.0,
    center_x: int = ROI_CENTER_X,
    center_y: int = ROI_CENTER_Y,
    radius: int = ROI_RADIUS,
) -> np.ndarray:
    height, width = shape
    center = (int(round(center_x * scale)), int(round(center_y * scale)))
    radius = int(round(radius * scale))
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.circle(mask, center, radius, 255, -1, cv2.LINE_AA)
    return mask


def rotate_around_roi_center(image: np.ndarray, angle_deg: float) -> np.ndarray:
    if angle_deg == 0:
        return image.copy()

    height, width = image.shape[:2]
    rotation_matrix = cv2.getRotationMatrix2D((ROI_CENTER_X, ROI_CENTER_Y), angle_deg, 1.0)
    return cv2.warpAffine(
        image,
        rotation_matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def translate_image(image: np.ndarray, dx: int, dy: int, interpolation: int) -> np.ndarray:
    if dx == 0 and dy == 0:
        return image.copy()

    height, width = image.shape[:2]
    translation_matrix = np.array([[1.0, 0.0, float(dx)], [0.0, 1.0, float(dy)]], dtype=np.float32)
    return cv2.warpAffine(
        image,
        translation_matrix,
        (width, height),
        flags=interpolation,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def load_overlay_image() -> np.ndarray | None:
    if not OVERLAY_IMAGE_PATH.exists():
        print(f"Overlay image not found: {OVERLAY_IMAGE_PATH}")
        return None

    overlay = cv2.imread(str(OVERLAY_IMAGE_PATH), cv2.IMREAD_UNCHANGED)
    if overlay is None:
        print(f"Could not read overlay image: {OVERLAY_IMAGE_PATH}")
        return None

    if overlay.ndim == 2:
        overlay = cv2.cvtColor(overlay, cv2.COLOR_GRAY2BGRA)
    elif overlay.shape[2] == 3:
        alpha = np.full(overlay.shape[:2] + (1,), 255, dtype=np.uint8)
        overlay = np.dstack((overlay, alpha))

    return overlay


def apply_overlay(base: np.ndarray, overlay: np.ndarray | None, scale: float) -> np.ndarray:
    if overlay is None:
        return base

    output = base.copy()
    overlay_w = max(1, int(round(overlay.shape[1] * OVERLAY_SCALE * scale)))
    overlay_h = max(1, int(round(overlay.shape[0] * OVERLAY_SCALE * scale)))
    overlay_resized = cv2.resize(overlay, (overlay_w, overlay_h), interpolation=cv2.INTER_AREA)

    x0 = int(round(OVERLAY_X * scale))
    y0 = int(round(OVERLAY_Y * scale))
    x1 = x0 + overlay_w
    y1 = y0 + overlay_h

    clip_x0 = max(0, x0)
    clip_y0 = max(0, y0)
    clip_x1 = min(output.shape[1], x1)
    clip_y1 = min(output.shape[0], y1)

    if clip_x0 >= clip_x1 or clip_y0 >= clip_y1:
        return output

    overlay_x0 = clip_x0 - x0
    overlay_y0 = clip_y0 - y0
    overlay_x1 = overlay_x0 + (clip_x1 - clip_x0)
    overlay_y1 = overlay_y0 + (clip_y1 - clip_y0)

    overlay_crop = overlay_resized[overlay_y0:overlay_y1, overlay_x0:overlay_x1]
    overlay_bgr = overlay_crop[:, :, :3].astype(np.float32)
    overlay_alpha = (overlay_crop[:, :, 3].astype(np.float32) / 255.0) * OVERLAY_ALPHA
    overlay_alpha = overlay_alpha[:, :, None]

    roi = output[clip_y0:clip_y1, clip_x0:clip_x1].astype(np.float32)
    blended = overlay_bgr * overlay_alpha + roi * (1.0 - overlay_alpha)
    output[clip_y0:clip_y1, clip_x0:clip_x1] = np.clip(blended, 0, 255).astype(np.uint8)
    return output


def estimate_fps(time_s: np.ndarray) -> float:
    finite = time_s[np.isfinite(time_s)]
    if finite.size < 2:
        return DEFAULT_PLAY_FPS
    duration = finite[-1] - finite[0]
    if duration <= 0:
        return DEFAULT_PLAY_FPS
    return float((finite.size - 1) / duration)


def nearest_frame_for_time(time_s: np.ndarray, target_s: float) -> int:
    return int(np.argmin(np.abs(time_s - target_s)))


def bgr_to_pixmap(image_bgr: np.ndarray) -> QPixmap:
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    image_rgb = np.ascontiguousarray(image_rgb)
    height, width, channels = image_rgb.shape
    qimage = QImage(image_rgb.data, width, height, channels * width, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


def state_for_time(display_time_s: float, transition_times_s: tuple[float, float] | None) -> tuple[str, tuple[int, int, int]]:
    if transition_times_s is None:
        return "Unknown", (160, 160, 160)

    initial_end_s, steady_start_s = transition_times_s
    if display_time_s < initial_end_s:
        return "Initial", (0, 0, 220)
    if display_time_s < steady_start_s:
        return "Transience", (0, 210, 230)
    return "Steady State", (0, 175, 0)


def injection_relative_transitions(result: dict) -> tuple[float, float] | None:
    transition_times_s = result.get("state_transition_times_s")
    if transition_times_s is None:
        return None
    injection_time_s = float(result.get("injection_time_s") or 0.0)
    return (
        float(transition_times_s[0]) - injection_time_s,
        float(transition_times_s[1]) - injection_time_s,
    )


class H5VideoViewer(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.h5 = None
        self.frames = None
        self.results_data = []
        self.time_s = np.array([], dtype=float)
        self.display_time_s = np.array([], dtype=float)
        self.visible_frame_indices = np.array([], dtype=int)
        self.heights = np.array([], dtype=float)

        self.frame_count = 0
        self.frame_h = 1080
        self.frame_w = 1080
        self.roi_center_x = ROI_CENTER_X
        self.roi_center_y = ROI_CENTER_Y
        self.roi_radius = ROI_RADIUS
        self.guide_circle_radius = GUIDE_CIRCLE_RADIUS
        self.align_dx = 0
        self.align_dy = 0
        self.display_h = max(1, int(round(self.frame_h * DISPLAY_SCALE)))
        self.display_w = max(1, int(round(self.frame_w * DISPLAY_SCALE)))
        self.tile_w = self.display_w + 90
        self.tile_h = self.display_h + PANEL_LABEL_HEIGHT
        self.grid_cols = MULTI_GRID_COLS
        self.grid_rows = int(np.ceil(len(TEST_RESULTS) / self.grid_cols))
        self.composite_w = self.grid_cols * self.tile_w + (self.grid_cols - 1) * MULTI_GRID_SPACING
        self.composite_h = self.grid_rows * self.tile_h + (self.grid_rows - 1) * MULTI_GRID_SPACING
        self.display_intensity_min = DISPLAY_INTENSITY_MIN
        self.display_intensity_max = DISPLAY_INTENSITY_MAX
        self.legend = make_intensity_legend(
            self.display_h,
            low=self.display_intensity_min,
            high=self.display_intensity_max,
        )
        self.display_roi_mask = make_roi_mask((self.display_h, self.display_w), scale=DISPLAY_SCALE)
        self.source_roi_mask = make_roi_mask((self.frame_h, self.frame_w), scale=1.0)
        self.display_keep_mask = cv2.resize(
            self.source_roi_mask,
            (self.display_w, self.display_h),
            interpolation=cv2.INTER_NEAREST,
        )
        self.overlay_image = load_overlay_image()

        self.display_roi_center = (
            int(round(GLOBAL_ROI_CENTER_X * DISPLAY_SCALE)),
            int(round(GLOBAL_ROI_CENTER_Y * DISPLAY_SCALE)),
        )
        self.display_roi_radius = int(round(ROI_RADIUS * DISPLAY_SCALE))
        self.display_guide_circle_radius = int(round(GUIDE_CIRCLE_RADIUS * DISPLAY_SCALE))
        self.base_fps = DEFAULT_PLAY_FPS
        self.frame_index = 0
        self.visible_index = 0
        self.current_time_s = 0.0
        self.max_display_time_s = POST_INJECTION_WINDOW_S
        self.time_step_s = 1.0 / DEFAULT_PLAY_FPS
        self.injection_time_s = None
        self.last_rotated_frame = None
        self.syncing_controls = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance_playback)

        self.build_ui()
        self.open_all_results()

    def build_ui(self) -> None:
        self.setWindowTitle("H5 Video Viewer")
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #000000;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QScrollArea {
                background: #000000;
                border: 1px solid #333333;
            }
            QScrollArea > QWidget > QWidget {
                background: #000000;
            }
            QComboBox, QSpinBox, QDoubleSpinBox, QPushButton {
                background: #1f1f1f;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #4a4a4a;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                margin: -5px 0;
                background: #d8d8d8;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #2e9afe;
                border-radius: 3px;
            }
            """
        )

        self.image_label = ImageLabel()
        self.image_label.setFixedSize(self.composite_w, self.composite_h)
        self.image_label.mouse_moved.connect(self.update_hover_readout)
        self.image_label.mouse_left.connect(lambda: self.hover_label.setText("Hover:"))
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(False)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.valueChanged.connect(self.on_slider_changed)

        self.frame_input = QSpinBox()
        self.frame_input.setRange(0, 0)
        self.frame_input.valueChanged.connect(self.on_frame_input_changed)

        self.seconds_input = QDoubleSpinBox()
        self.seconds_input.setDecimals(1)
        self.seconds_input.setSingleStep(0.1)
        self.seconds_input.setRange(0.0, 0.0)
        self.seconds_input.valueChanged.connect(self.on_seconds_input_changed)

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_playback)

        self.speed_combo = QComboBox()
        for speed in SPEED_OPTIONS:
            self.speed_combo.addItem(f"{speed}x", speed)
        self.speed_combo.currentIndexChanged.connect(self.update_timer_interval)

        self.status_label = QLabel()
        self.hover_label = QLabel("Hover:")

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Step"))
        controls.addWidget(self.frame_input)
        controls.addWidget(QLabel("Seconds"))
        controls.addWidget(self.seconds_input)
        controls.addWidget(self.play_button)
        controls.addWidget(QLabel("Speed"))
        controls.addWidget(self.speed_combo)
        controls.addStretch(1)

        layout = QVBoxLayout()
        layout.addWidget(self.scroll_area)
        layout.addWidget(self.slider)
        layout.addLayout(controls)
        layout.addWidget(self.status_label)
        layout.addWidget(self.hover_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.update_timer_interval()

    def make_result_data(self, result: dict) -> dict:
        path = result["path"]
        if not path.exists():
            raise FileNotFoundError(path)

        h5 = h5py.File(path, "r")
        frames = h5["frames"]
        time_s = np.asarray(h5["time_s"][:], dtype=float) if "time_s" in h5 else np.arange(frames.shape[0])
        heights = (
            np.asarray(h5["heights_mm"][:], dtype=float)
            if "heights_mm" in h5
            else np.full(frames.shape[0], np.nan)
        )

        frame_count, frame_h, frame_w = frames.shape
        roi_center_x = int(h5.attrs.get("roi_center_x", ROI_CENTER_X))
        roi_center_y = int(h5.attrs.get("roi_center_y", ROI_CENTER_Y))
        roi_radius = int(h5.attrs.get("roi_radius", ROI_RADIUS))
        guide_circle_radius = int(h5.attrs.get("guide_circle_radius", GUIDE_CIRCLE_RADIUS))
        align_dx = GLOBAL_ROI_CENTER_X - roi_center_x
        align_dy = GLOBAL_ROI_CENTER_Y - roi_center_y

        display_h = max(1, int(round(frame_h * DISPLAY_SCALE)))
        display_w = max(1, int(round(frame_w * DISPLAY_SCALE)))
        display_intensity_min = float(result.get("display_min", h5.attrs.get("display_intensity_min", DISPLAY_INTENSITY_MIN)))
        display_intensity_max = float(result.get("display_max", h5.attrs.get("display_intensity_max", DISPLAY_INTENSITY_MAX)))
        legend = make_intensity_legend(display_h, low=display_intensity_min, high=display_intensity_max)

        if "keep_mask" in h5:
            source_roi_mask = np.asarray(h5["keep_mask"][:], dtype=np.uint8)
        else:
            source_roi_mask = make_roi_mask(
                (frame_h, frame_w),
                scale=1.0,
                center_x=roi_center_x,
                center_y=roi_center_y,
                radius=roi_radius,
            )
        source_roi_mask = translate_image(source_roi_mask, align_dx, align_dy, cv2.INTER_NEAREST)
        display_keep_mask = cv2.resize(
            source_roi_mask,
            (display_w, display_h),
            interpolation=cv2.INTER_NEAREST,
        )

        injection_time_s = result.get("injection_time_s")
        if injection_time_s is None:
            display_time_s = time_s.copy()
            visible_frame_indices = np.flatnonzero((display_time_s >= 0.0) & (display_time_s <= POST_INJECTION_WINDOW_S))
        else:
            display_time_s = time_s - float(injection_time_s)
            visible_frame_indices = np.flatnonzero(
                (display_time_s >= 0.0) & (display_time_s <= POST_INJECTION_WINDOW_S)
            )
        if visible_frame_indices.size == 0:
            h5.close()
            raise ValueError(f"No visible frames found for {result['name']}")

        return {
            "result": result,
            "h5": h5,
            "frames": frames,
            "time_s": time_s,
            "display_time_s": display_time_s,
            "visible_frame_indices": visible_frame_indices.astype(int),
            "heights": heights,
            "frame_count": frame_count,
            "frame_h": frame_h,
            "frame_w": frame_w,
            "display_h": display_h,
            "display_w": display_w,
            "display_intensity_min": display_intensity_min,
            "display_intensity_max": display_intensity_max,
            "legend": legend,
            "source_roi_mask": source_roi_mask,
            "display_keep_mask": display_keep_mask,
            "display_roi_center": (
                int(round(GLOBAL_ROI_CENTER_X * DISPLAY_SCALE)),
                int(round(GLOBAL_ROI_CENTER_Y * DISPLAY_SCALE)),
            ),
            "display_roi_radius": int(round(roi_radius * DISPLAY_SCALE)),
            "display_guide_circle_radius": int(round(guide_circle_radius * DISPLAY_SCALE)),
            "align_dx": align_dx,
            "align_dy": align_dy,
            "injection_time_s": injection_time_s,
            "state_transition_display_s": injection_relative_transitions(result),
            "last_frame": None,
            "last_frame_index": int(visible_frame_indices[0]),
        }

    def open_all_results(self) -> None:
        self.pause_playback()
        for data in self.results_data:
            data["h5"].close()
        self.results_data = [self.make_result_data(result) for result in TEST_RESULTS]

        first = self.results_data[0]
        self.frame_h = first["frame_h"]
        self.frame_w = first["frame_w"]
        self.display_h = first["display_h"]
        self.display_w = first["display_w"]
        self.tile_w = self.display_w + first["legend"].shape[1]
        self.tile_h = self.display_h + PANEL_LABEL_HEIGHT
        self.grid_rows = int(np.ceil(len(self.results_data) / self.grid_cols))
        self.composite_w = self.grid_cols * self.tile_w + (self.grid_cols - 1) * MULTI_GRID_SPACING
        self.composite_h = self.grid_rows * self.tile_h + (self.grid_rows - 1) * MULTI_GRID_SPACING
        self.image_label.setFixedSize(self.composite_w, self.composite_h)

        visible_times = [data["display_time_s"][data["visible_frame_indices"]] for data in self.results_data]
        self.base_fps = max(estimate_fps(times) for times in visible_times)
        self.time_step_s = 1.0 / max(self.base_fps, 1.0)
        self.max_display_time_s = POST_INJECTION_WINDOW_S
        self.visible_index = 0
        self.current_time_s = 0.0

        max_step = int(round(self.max_display_time_s / self.time_step_s))
        self.syncing_controls = True
        self.slider.setRange(0, max_step)
        self.slider.setValue(0)
        self.frame_input.setRange(0, max_step)
        self.frame_input.setValue(0)
        self.seconds_input.setRange(0.0, self.max_display_time_s)
        self.seconds_input.setValue(0.0)
        self.syncing_controls = False

        self.update_timer_interval()
        self.update_frame(0)

    def on_result_changed(self, index: int) -> None:
        if self.syncing_controls:
            return
        self.open_result(index)

    def open_result(self, result_index: int) -> None:
        self.pause_playback()
        result = TEST_RESULTS[result_index]
        path = result["path"]
        if not path.exists():
            raise FileNotFoundError(path)

        if self.h5 is not None:
            self.h5.close()

        self.h5 = h5py.File(path, "r")
        self.frames = self.h5["frames"]
        self.display_intensity_min = float(result.get("display_min", self.h5.attrs.get("display_intensity_min", DISPLAY_INTENSITY_MIN)))
        self.display_intensity_max = float(result.get("display_max", self.h5.attrs.get("display_intensity_max", DISPLAY_INTENSITY_MAX)))
        self.injection_time_s = result.get("injection_time_s")
        self.legend = make_intensity_legend(
            self.display_h,
            low=self.display_intensity_min,
            high=self.display_intensity_max,
        )
        self.time_s = np.asarray(self.h5["time_s"][:], dtype=float) if "time_s" in self.h5 else np.arange(self.frames.shape[0])
        if self.injection_time_s is None:
            self.display_time_s = self.time_s.copy()
            self.visible_frame_indices = np.arange(self.frames.shape[0], dtype=int)
        else:
            injection_time_s = float(self.injection_time_s)
            self.display_time_s = self.time_s - injection_time_s
            visible = (self.display_time_s >= 0.0) & (self.display_time_s <= POST_INJECTION_WINDOW_S)
            self.visible_frame_indices = np.flatnonzero(visible).astype(int)
            if self.visible_frame_indices.size == 0:
                raise ValueError(
                    f"No frames found from injection time {injection_time_s:g}s "
                    f"to {injection_time_s + POST_INJECTION_WINDOW_S:g}s in {path}"
                )
        self.heights = (
            np.asarray(self.h5["heights_mm"][:], dtype=float)
            if "heights_mm" in self.h5
            else np.full(self.frames.shape[0], np.nan)
        )

        self.frame_count, self.frame_h, self.frame_w = self.frames.shape
        self.roi_center_x = int(self.h5.attrs.get("roi_center_x", ROI_CENTER_X))
        self.roi_center_y = int(self.h5.attrs.get("roi_center_y", ROI_CENTER_Y))
        self.roi_radius = int(self.h5.attrs.get("roi_radius", ROI_RADIUS))
        self.guide_circle_radius = int(self.h5.attrs.get("guide_circle_radius", GUIDE_CIRCLE_RADIUS))
        self.align_dx = GLOBAL_ROI_CENTER_X - self.roi_center_x
        self.align_dy = GLOBAL_ROI_CENTER_Y - self.roi_center_y

        expected_h = max(1, int(round(self.frame_h * DISPLAY_SCALE)))
        expected_w = max(1, int(round(self.frame_w * DISPLAY_SCALE)))
        if expected_h != self.display_h or expected_w != self.display_w:
            self.display_h = expected_h
            self.display_w = expected_w
            self.legend = make_intensity_legend(
                self.display_h,
                low=self.display_intensity_min,
                high=self.display_intensity_max,
            )
            self.image_label.setFixedSize(self.display_w + self.legend.shape[1], self.display_h)

        self.display_roi_mask = make_roi_mask(
            (self.display_h, self.display_w),
            scale=DISPLAY_SCALE,
            center_x=self.roi_center_x,
            center_y=self.roi_center_y,
            radius=self.roi_radius,
        )

        if "keep_mask" in self.h5:
            self.source_roi_mask = np.asarray(self.h5["keep_mask"][:], dtype=np.uint8)
        else:
            self.source_roi_mask = make_roi_mask(
                (self.frame_h, self.frame_w),
                scale=1.0,
                center_x=self.roi_center_x,
                center_y=self.roi_center_y,
                radius=self.roi_radius,
            )
        self.source_roi_mask = translate_image(
            self.source_roi_mask,
            self.align_dx,
            self.align_dy,
            cv2.INTER_NEAREST,
        )
        self.display_keep_mask = cv2.resize(
            self.source_roi_mask,
            (self.display_w, self.display_h),
            interpolation=cv2.INTER_NEAREST,
        )

        self.display_roi_center = (
            int(round(GLOBAL_ROI_CENTER_X * DISPLAY_SCALE)),
            int(round(GLOBAL_ROI_CENTER_Y * DISPLAY_SCALE)),
        )
        self.display_roi_radius = int(round(self.roi_radius * DISPLAY_SCALE))
        self.display_guide_circle_radius = int(round(self.guide_circle_radius * DISPLAY_SCALE))
        self.base_fps = estimate_fps(self.display_time_s[self.visible_frame_indices])
        self.visible_index = 0
        self.frame_index = int(self.visible_frame_indices[self.visible_index])
        self.last_rotated_frame = None

        max_time_s = round(float(self.display_time_s[self.visible_frame_indices[-1]]), 1)

        self.syncing_controls = True
        self.slider.setRange(0, self.visible_frame_indices.size - 1)
        self.slider.setValue(0)
        self.frame_input.setRange(0, self.visible_frame_indices.size - 1)
        self.frame_input.setValue(0)
        self.seconds_input.setRange(0.0, max_time_s)
        self.seconds_input.setValue(0.0)
        if self.result_combo.currentIndex() != result_index:
            self.result_combo.setCurrentIndex(result_index)
        self.syncing_controls = False

        self.update_timer_interval()
        self.update_frame(0)

    def nearest_visible_frame_index(self, data: dict, display_time_s: float) -> int:
        visible_indices = data["visible_frame_indices"]
        visible_times = data["display_time_s"][visible_indices]
        if display_time_s <= visible_times[0]:
            return int(visible_indices[0])
        if display_time_s >= visible_times[-1]:
            return int(visible_indices[-1])
        return int(visible_indices[nearest_frame_for_time(visible_times, display_time_s)])

    def render_result_tile(self, data: dict, display_time_s: float) -> np.ndarray:
        frame_index = self.nearest_visible_frame_index(data, display_time_s)
        frame = np.asarray(data["frames"][frame_index])
        if frame.ndim == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if not FRAMES_ALREADY_PROCESSED:
            frame = rotate_around_roi_center(frame, ROI_ROTATION_DEG)
        frame = translate_image(frame, data["align_dx"], data["align_dy"], cv2.INTER_NEAREST)
        data["last_frame"] = frame
        data["last_frame_index"] = frame_index

        panel = cv2.resize(
            display_intensity_image(frame, data["display_intensity_min"], data["display_intensity_max"]),
            (data["display_w"], data["display_h"]),
            interpolation=cv2.INTER_AREA,
        )
        panel_color = cv2.applyColorMap(panel, cv2.COLORMAP_VIRIDIS)
        panel_color[data["display_keep_mask"] == 0] = OUTSIDE_ROI_COLOR_BGR
        if SHOW_ROI_OUTLINE:
            cv2.circle(
                panel_color,
                data["display_roi_center"],
                data["display_roi_radius"],
                ROI_OUTLINE_COLOR_BGR,
                ROI_OUTLINE_THICKNESS,
                cv2.LINE_AA,
            )
        if SHOW_GUIDE_CIRCLE:
            cv2.circle(
                panel_color,
                data["display_roi_center"],
                data["display_guide_circle_radius"],
                ROI_OUTLINE_COLOR_BGR,
                ROI_OUTLINE_THICKNESS,
                cv2.LINE_AA,
            )
        if SHOW_RPV_OVERLAY:
            panel_color = apply_overlay(panel_color, self.overlay_image, DISPLAY_SCALE)

        tile = np.zeros((self.tile_h, self.tile_w, 3), dtype=np.uint8)
        tile[PANEL_LABEL_HEIGHT:PANEL_LABEL_HEIGHT + data["display_h"], :data["display_w"]] = panel_color
        tile[
            PANEL_LABEL_HEIGHT:PANEL_LABEL_HEIGHT + data["display_h"],
            data["display_w"]:data["display_w"] + data["legend"].shape[1],
        ] = data["legend"]

        result = data["result"]
        raw_time_s = data["time_s"][frame_index]
        state_label, state_color = state_for_time(display_time_s, data["state_transition_display_s"])
        badge_w = 96 if state_label != "Steady State" else 116
        title = result["name"]
        cv2.putText(
            tile,
            title,
            (6, 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.rectangle(tile, (6, 22), (6 + badge_w, PANEL_LABEL_HEIGHT - 5), state_color, -1)
        cv2.rectangle(tile, (6, 22), (6 + badge_w, PANEL_LABEL_HEIGHT - 5), (255, 255, 255), 1)
        cv2.putText(
            tile,
            state_label,
            (12, 37),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        metadata = (
            f"t={display_time_s:.2f}s  "
            f"raw={raw_time_s:.2f}s  "
        )
        cv2.putText(
            tile,
            metadata,
            (badge_w + 16, 37),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        return tile

    def render_composite(self, display_time_s: float) -> np.ndarray:
        composite = np.zeros((self.composite_h, self.composite_w, 3), dtype=np.uint8)
        for result_index, data in enumerate(self.results_data):
            row = result_index // self.grid_cols
            col = result_index % self.grid_cols
            x0 = col * (self.tile_w + MULTI_GRID_SPACING)
            y0 = row * (self.tile_h + MULTI_GRID_SPACING)
            tile = self.render_result_tile(data, display_time_s)
            composite[y0:y0 + self.tile_h, x0:x0 + self.tile_w] = tile
        return composite

    def update_frame(self, index: int) -> None:
        if not self.results_data:
            return

        self.visible_index = max(0, min(self.slider.maximum(), int(index)))
        self.current_time_s = min(self.max_display_time_s, self.visible_index * self.time_step_s)
        display = self.render_composite(self.current_time_s)
        self.image_label.setPixmap(bgr_to_pixmap(display))

        self.syncing_controls = True
        self.slider.setValue(self.visible_index)
        self.frame_input.setValue(self.visible_index)
        self.seconds_input.setValue(round(float(self.current_time_s), 1))
        self.syncing_controls = False

        available = []
        for data in self.results_data:
            max_time_s = float(data["display_time_s"][data["visible_frame_indices"][-1]])
            if self.current_time_s <= max_time_s:
                available.append(data["result"]["name"].split("(")[-1].rstrip(")"))
        self.status_label.setText(
            f"All tests    "
            f"Step {self.visible_index} / {self.slider.maximum()}    "
            f"Injection-relative time {self.current_time_s:.3f} s    "
            f"FPS {self.base_fps:.2f}    "
            f"Available at this time: {', '.join(available) if available else 'none'}"
        )

    def on_slider_changed(self, value: int) -> None:
        if self.syncing_controls:
            return
        self.pause_playback()
        self.update_frame(value)

    def on_frame_input_changed(self, value: int) -> None:
        if self.syncing_controls:
            return
        self.pause_playback()
        self.update_frame(value)

    def on_seconds_input_changed(self, value: float) -> None:
        if self.syncing_controls:
            return
        self.pause_playback()
        rounded = round(float(value), 1)
        self.update_frame(int(round(rounded / self.time_step_s)))

    def selected_speed(self) -> int:
        return int(self.speed_combo.currentData())

    def update_timer_interval(self) -> None:
        interval_ms = max(1, int(round(1000.0 / max(self.base_fps, 1.0))))
        self.timer.setInterval(interval_ms)

    def toggle_playback(self) -> None:
        if self.timer.isActive():
            self.pause_playback()
        else:
            self.play_button.setText("Pause")
            self.timer.start()

    def pause_playback(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
        self.play_button.setText("Play")

    def advance_playback(self) -> None:
        if not self.results_data:
            return

        next_index = self.visible_index + self.selected_speed()
        if next_index >= self.slider.maximum():
            next_index = self.slider.maximum()
            self.pause_playback()
        self.update_frame(next_index)

    def update_hover_readout(self, x: int, y: int) -> None:
        if not self.results_data:
            self.hover_label.setText("Hover:")
            return

        if x < 0 or y < 0 or x >= self.composite_w or y >= self.composite_h:
            self.hover_label.setText("Hover:")
            return

        col = x // (self.tile_w + MULTI_GRID_SPACING)
        row = y // (self.tile_h + MULTI_GRID_SPACING)
        if col >= self.grid_cols:
            self.hover_label.setText("Hover:")
            return
        result_index = int(row * self.grid_cols + col)
        if result_index < 0 or result_index >= len(self.results_data):
            self.hover_label.setText("Hover:")
            return

        tile_x0 = int(col * (self.tile_w + MULTI_GRID_SPACING))
        tile_y0 = int(row * (self.tile_h + MULTI_GRID_SPACING))
        panel_x = x - tile_x0
        panel_y = y - tile_y0 - PANEL_LABEL_HEIGHT
        data = self.results_data[result_index]

        if panel_x < 0 or panel_y < 0 or panel_x >= data["display_w"] or panel_y >= data["display_h"]:
            self.hover_label.setText("Hover:")
            return

        src_x = min(data["frame_w"] - 1, int(panel_x / DISPLAY_SCALE))
        src_y = min(data["frame_h"] - 1, int(panel_y / DISPLAY_SCALE))
        if not data["source_roi_mask"][src_y, src_x]:
            self.hover_label.setText("Hover:")
            return

        if data["last_frame"] is None:
            return

        intensity = int(data["last_frame"][src_y, src_x])
        normalized = normalized_intensity(
            intensity,
            data["display_intensity_min"],
            data["display_intensity_max"],
        )
        self.hover_label.setText(
            f"Hover: {data['result']['name']} ({src_x}, {src_y}) "
            f"N={normalized:.3f} raw={intensity} "
            f"t={self.current_time_s:.3f}s frame={data['last_frame_index']}"
        )

    def closeEvent(self, event) -> None:
        self.pause_playback()
        for data in self.results_data:
            data["h5"].close()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    viewer = H5VideoViewer()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
