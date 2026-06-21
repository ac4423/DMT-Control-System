from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget


TIME_COLUMN = "time_s"
CORE_FILTERED_COLUMN = "inside_guide_lowpass_intensity"
DEFAULT_X_MAX_S = 30.0


@dataclass(frozen=True)
class CsvSeries:
    label: str
    path: Path
    injection_time_s: float | None = None


DEFAULT_SERIES = (
    CsvSeries(
        "1500 ml/min",
        Path(r"E:\RPV Test\RPV Data Display\H5 Data\camera_20260601_151542_roi_masked_nlm_bgcomp_zstd9_region_intensity_timeseries.csv"),
        11.450753,
    ),
    CsvSeries(
        "1250 ml/min",
        Path(r"E:\RPV Test\RPV Data Display\H5 Data\camera_20260601_145235_frames_2500_to_2600_roi_masked_nlm_bgcomp_zstd9_region_intensity_timeseries.csv"),
        13.276876,
    ),
    CsvSeries(
        "1000 ml/min",
        Path(r"E:\RPV Test\RPV Data Display\H5 Data\camera_20260601_120151_roi_masked_nlm_bgcomp_zstd9_v3_region_intensity_timeseries.csv"),
        10,
    ),
    CsvSeries(
        "750 ml/min",
        Path(r"E:\RPV Test\RPV Data Display\H5 Data\camera_20260601_141243_roi_masked_nlm_bgcomp_zstd9_region_intensity_timeseries.csv"),
        18.133829,
    ),
    CsvSeries(
        "500 ml/min",
        Path(r"E:\RPV Test\RPV Data Display\H5 Data\camera_20260601_154017_from_3500_avg_5600_to_5900_roi_masked_nlm_bgcomp_zstd9_region_intensity_timeseries.csv"),
        5.097,
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plot filtered core intensity from multiple region-intensity CSV files."
    )
    parser.add_argument(
        "--x-max-s",
        type=float,
        default=DEFAULT_X_MAX_S,
        help=f"Maximum displayed time in seconds. Default: {DEFAULT_X_MAX_S}; use 0 for full range.",
    )
    return parser.parse_args()


def load_filtered_core(path: Path) -> tuple[np.ndarray, np.ndarray]:
    if not path.exists():
        raise FileNotFoundError(path)

    table = np.genfromtxt(path, delimiter=",", names=True, dtype=np.float64)
    columns = table.dtype.names or ()
    if TIME_COLUMN not in columns:
        raise KeyError(f"{path} is missing required column: {TIME_COLUMN}")
    if CORE_FILTERED_COLUMN not in columns:
        raise KeyError(f"{path} is missing required column: {CORE_FILTERED_COLUMN}")

    return (
        np.asarray(table[TIME_COLUMN], dtype=np.float64),
        np.asarray(table[CORE_FILTERED_COLUMN], dtype=np.float64),
    )


def align_to_injection(
    time_s: np.ndarray,
    values: np.ndarray,
    injection_time_s: float | None,
) -> tuple[np.ndarray, np.ndarray]:
    if injection_time_s is None:
        return time_s, values

    shifted_time_s = time_s - injection_time_s
    after_injection = shifted_time_s >= 0.0
    if not np.any(after_injection):
        raise ValueError(f"No samples remain after injection time {injection_time_s:g} s.")
    return shifted_time_s[after_injection], values[after_injection]


def show_interactive_plot(
    loaded_series: list[tuple[CsvSeries, np.ndarray, np.ndarray]],
    x_max_s: float,
) -> None:
    app = QApplication.instance() or QApplication([])

    window = QMainWindow()
    window.setWindowTitle("Filtered Core Intensity Comparison")

    canvas = FigureCanvas(Figure(figsize=(11, 6)))
    axis = canvas.figure.subplots()
    canvas.figure.subplots_adjust(left=0.08, right=0.98, bottom=0.12, top=0.9)

    for series, time_s, core_filtered in loaded_series:
        axis.plot(time_s, core_filtered, label=series.label, linewidth=1.3)

    all_times = np.concatenate([time_s for _, time_s, _ in loaded_series])
    x_right = x_max_s if x_max_s > 0 else float(np.max(all_times))
    axis.set_xlim(left=0.0, right=x_right)
    axis.set_title("Filtered Core Intensity over Time")
    axis.set_xlabel("Time from Injection (s)")
    axis.set_ylabel("Filtered core intensity")
    axis.grid(True, alpha=0.3)
    axis.legend()

    cursor_line = axis.axvline(0.0, color="black", linewidth=0.9, alpha=0.55)
    readout = QLabel()
    readout.setMinimumHeight(42)
    readout.setText("Move the mouse over the plot")

    def update_readout(event) -> None:
        if event.xdata is None:
            return

        x_value = max(0.0, min(float(event.xdata), x_right))
        cursor_line.set_xdata([x_value, x_value])

        values = []
        for series, time_s, core_filtered in loaded_series:
            index = int(np.argmin(np.abs(time_s - x_value)))
            values.append(f"{series.label}: {core_filtered[index]:.4f}")
        readout.setText(f"t = {x_value:.4f} s | " + " | ".join(values))
        canvas.draw_idle()

    canvas.mpl_connect("motion_notify_event", update_readout)

    layout = QVBoxLayout()
    layout.addWidget(NavigationToolbar(canvas, window))
    layout.addWidget(canvas)
    layout.addWidget(readout)

    container = QWidget()
    container.setLayout(layout)
    window.setCentralWidget(container)
    window.resize(1200, 760)
    window.show()
    app.exec()


def main() -> None:
    args = parse_args()
    loaded_series = []
    for series in DEFAULT_SERIES:
        time_s, core_filtered = load_filtered_core(series.path)
        time_s, core_filtered = align_to_injection(time_s, core_filtered, series.injection_time_s)
        loaded_series.append((series, time_s, core_filtered))
        alignment = (
            f"injection aligned at {series.injection_time_s:g} s"
            if series.injection_time_s is not None
            else "not injection aligned"
        )
        print(
            f"{series.label}: {time_s.size} samples, "
            f"time {time_s[0]:.4f}-{time_s[-1]:.4f} s, "
            f"filtered range {np.min(core_filtered):.4f}-{np.max(core_filtered):.4f}, "
            f"{alignment}"
        )

    show_interactive_plot(loaded_series, args.x_max_s)


if __name__ == "__main__":
    main()
