from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget


DEFAULT_CSV_PATH = Path(
    r"E:\RPV Test\RPV Data Display\H5 Data\camera_20260601_141243_roi_masked_nlm_bgcomp_zstd9_region_intensity_timeseries.csv"
)
TIME_COLUMN = "time_s"
CORE_FILTERED_COLUMN = "inside_guide_lowpass_intensity"
AVERAGE_WINDOWS_S = ((5.0, 20.0), (32.0, 43.0))
AVERAGE_LINE_EXTENSION_S = 2.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(   
        description="Interactively plot core cleaned intensity values from a region-intensity CSV."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help=f"CSV file to read. Default: {DEFAULT_CSV_PATH}",
    )
    return parser.parse_args()


def load_core_filtered_values(csv_path: Path) -> tuple[np.ndarray, np.ndarray]:
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    table = np.genfromtxt(csv_path, delimiter=",", names=True, dtype=np.float64)
    columns = table.dtype.names or ()

    if TIME_COLUMN not in columns:
        raise KeyError(f"Missing required CSV column: {TIME_COLUMN}")
    if CORE_FILTERED_COLUMN not in columns:
        raise KeyError(f"Missing required CSV column: {CORE_FILTERED_COLUMN}")

    time_s = np.asarray(table[TIME_COLUMN], dtype=np.float64)
    core_filtered = np.asarray(table[CORE_FILTERED_COLUMN], dtype=np.float64)
    return time_s, core_filtered


def window_average(time_s: np.ndarray, values: np.ndarray, start_s: float, end_s: float) -> float:
    in_window = (time_s >= start_s) & (time_s <= end_s)
    if not np.any(in_window):
        raise ValueError(f"No samples found between {start_s:g} and {end_s:g} seconds.")
    return float(np.mean(values[in_window]))


def threshold_crossing_time(
    time_s: np.ndarray,
    values: np.ndarray,
    threshold: float,
    start_s: float,
    end_s: float,
) -> float | None:
    in_window = (time_s >= start_s) & (time_s <= end_s)
    window_time = time_s[in_window]
    window_values = values[in_window]
    if window_time.size < 2:
        return None

    deltas = window_values - threshold
    for index in range(window_time.size - 1):
        y0 = float(deltas[index])
        y1 = float(deltas[index + 1])
        if y0 == 0:
            return float(window_time[index])
        if y0 * y1 <= 0:
            x0 = float(window_time[index])
            x1 = float(window_time[index + 1])
            v0 = float(window_values[index])
            v1 = float(window_values[index + 1])
            if v1 == v0:
                return x0
            fraction = (threshold - v0) / (v1 - v0)
            return x0 + fraction * (x1 - x0)
    return None


def rise_metrics(time_s: np.ndarray, values: np.ndarray) -> dict[str, float | None]:
    (baseline_start_s, baseline_end_s), (final_start_s, final_end_s) = AVERAGE_WINDOWS_S
    baseline_average = window_average(time_s, values, baseline_start_s, baseline_end_s)
    final_average = window_average(time_s, values, final_start_s, final_end_s)
    span = final_average - baseline_average
    ten_percent_value = baseline_average + 0.10 * span
    ninety_percent_value = baseline_average + 0.90 * span

    transition_start_s = baseline_end_s
    transition_end_s = final_start_s
    ten_percent_time = threshold_crossing_time(
        time_s,
        values,
        ten_percent_value,
        transition_start_s,
        transition_end_s,
    )
    ninety_percent_time = threshold_crossing_time(
        time_s,
        values,
        ninety_percent_value,
        transition_start_s,
        transition_end_s,
    )
    rise_time_s = (
        ninety_percent_time - ten_percent_time
        if ten_percent_time is not None and ninety_percent_time is not None
        else None
    )

    return {
        "baseline_average": baseline_average,
        "final_average": final_average,
        "ten_percent_value": ten_percent_value,
        "ninety_percent_value": ninety_percent_value,
        "ten_percent_time": ten_percent_time,
        "ninety_percent_time": ninety_percent_time,
        "rise_time_s": rise_time_s,
        "transition_start_s": transition_start_s,
        "transition_end_s": transition_end_s,
    }


def show_interactive_plot(csv_path: Path, time_s: np.ndarray, core_filtered: np.ndarray) -> None:
    app = QApplication.instance() or QApplication([])

    window = QMainWindow()
    window.setWindowTitle("Interactive Core Clean Intensity")

    canvas = FigureCanvas(Figure(figsize=(11, 6)))
    axis = canvas.figure.subplots()
    canvas.figure.subplots_adjust(left=0.08, right=0.98, bottom=0.12, top=0.9)

    axis.plot(time_s, core_filtered, label="Core Average Intensity", linewidth=1.3)
    cursor_line = axis.axvline(time_s[0], color="black", linewidth=0.9, alpha=0.55)
    point_marker, = axis.plot([time_s[0]], [core_filtered[0]], "o", color="black", markersize=4)

    axis.set_title("Intensity over Time")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Core Intensity")
    axis.set_xlim(left=0.0, right=50.0)
    axis.grid(True, alpha=0.3)
    #axis.legend()

    readout = QLabel()
    readout.setMinimumHeight(28)
    readout.setText("Move the mouse over the plot")

    def update_readout(event) -> None:
        if event.xdata is None:
            return
        index = int(np.argmin(np.abs(time_s - event.xdata)))
        x_value = float(time_s[index])
        y_value = float(core_filtered[index])
        cursor_line.set_xdata([x_value, x_value])
        point_marker.set_data([x_value], [y_value])
        readout.setText(f"t = {x_value:.4f} s | Core Intensity = {y_value:.4f}")
        canvas.draw_idle()

    canvas.mpl_connect("motion_notify_event", update_readout)

    layout = QVBoxLayout()
    layout.addWidget(NavigationToolbar(canvas, window))
    layout.addWidget(canvas)
    layout.addWidget(readout)

    container = QWidget()
    container.setLayout(layout)
    window.setCentralWidget(container)
    window.resize(1150, 720)
    window.show()
    app.exec()


def main() -> None:
    args = parse_args()
    time_s, core_filtered = load_core_filtered_values(args.csv_path)
    print(f"Loaded {time_s.size} samples from: {args.csv_path}")
    for start_s, end_s in AVERAGE_WINDOWS_S:
        average_value = window_average(time_s, core_filtered, start_s, end_s)
        print(f"Average {start_s:g}-{end_s:g} s: {average_value:.6f}")
    metrics = rise_metrics(time_s, core_filtered)
    print(f"10% level: {float(metrics['ten_percent_value']):.6f}")
    print(f"90% level: {float(metrics['ninety_percent_value']):.6f}")
    if metrics["ten_percent_time"] is not None:
        print(f"10% crossing time: {float(metrics['ten_percent_time']):.6f} s")
    else:
        print("10% crossing time: not found")
    if metrics["ninety_percent_time"] is not None:
        print(f"90% crossing time: {float(metrics['ninety_percent_time']):.6f} s")
    else:
        print("90% crossing time: not found")
    if metrics["rise_time_s"] is not None:
        print(f"Rise time: {float(metrics['rise_time_s']):.6f} s")
    else:
        print("Rise time: not available")
    show_interactive_plot(args.csv_path, time_s, core_filtered)


if __name__ == "__main__":
    main()
