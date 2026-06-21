from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import h5py
import hdf5plugin  # noqa: F401 - registers compressed HDF5 filters
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, sosfiltfilt


DEFAULT_INPUT_H5_PATH = Path(
    r"E:\RPV Test\RPV Data Display\H5 Data\camera_20260601_120151_roi_masked_nlm_bgcomp_zstd9_v3.h5"
)
DEFAULT_CHUNK_FRAMES = 64
DEFAULT_OUTLIER_WINDOW_S = 0.5
DEFAULT_OUTLIER_MAD_Z = 6.0
DEFAULT_LOWPASS_CUTOFF_HZ = 1.0
DEFAULT_LOWPASS_ORDER = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot average frame intensity over time for pixels inside the guide circle "
            "and pixels between the guide circle and ROI circle."
        )
    )
    parser.add_argument(
        "input_h5",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT_H5_PATH,
        help=f"Processed H5 file to analyze. Default: {DEFAULT_INPUT_H5_PATH}",
    )
    parser.add_argument(
        "--output-png",
        type=Path,
        default=None,
        help="Where to save the plot PNG. Default: <input stem>_region_intensity_timeseries.png",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Where to save the CSV table. Default: <input stem>_region_intensity_timeseries.csv",
    )
    parser.add_argument(
        "--chunk-frames",
        type=int,
        default=DEFAULT_CHUNK_FRAMES,
        help=f"Number of frames to process per chunk. Default: {DEFAULT_CHUNK_FRAMES}",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open an interactive PyQt plot window after saving.",
    )
    parser.add_argument(
        "--interactive-only",
        action="store_true",
        help="Open the interactive PyQt plot without saving CSV or PNG outputs.",
    )
    parser.add_argument(
        "--outlier-window-s",
        type=float,
        default=DEFAULT_OUTLIER_WINDOW_S,
        help=(
            "Rolling window, in seconds, used to detect outliers with median absolute deviation. "
            f"Default: {DEFAULT_OUTLIER_WINDOW_S}"
        ),
    )
    parser.add_argument(
        "--outlier-mad-z",
        type=float,
        default=DEFAULT_OUTLIER_MAD_Z,
        help=(
            "Outlier threshold in robust MAD-scaled z-score units. "
            f"Default: {DEFAULT_OUTLIER_MAD_Z}; use 0 to disable outlier filtering."
        ),
    )
    parser.add_argument(
        "--lowpass-cutoff-hz",
        type=float,
        default=DEFAULT_LOWPASS_CUTOFF_HZ,
        help=(
            "Butterworth low-pass cutoff frequency in Hz. "
            f"Default: {DEFAULT_LOWPASS_CUTOFF_HZ}; use 0 to disable low-pass filtering."
        ),
    )
    parser.add_argument(
        "--lowpass-order",
        type=int,
        default=DEFAULT_LOWPASS_ORDER,
        help=(
            "Butterworth low-pass filter order. "
            f"Default: {DEFAULT_LOWPASS_ORDER}"
        ),
    )
    return parser.parse_args()


def make_disk_mask(shape: tuple[int, int], center_x: int, center_y: int, radius: int) -> np.ndarray:
    height, width = shape
    yy, xx = np.ogrid[:height, :width]
    return (xx - center_x) ** 2 + (yy - center_y) ** 2 <= radius**2


def load_region_masks(h5: h5py.File, frame_shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    center_x = int(h5.attrs["roi_center_x"])
    center_y = int(h5.attrs["roi_center_y"])
    roi_radius = int(h5.attrs["roi_radius"])
    guide_radius = int(h5.attrs["guide_circle_radius"])

    if "keep_mask" in h5:
        valid_pixels = np.asarray(h5["keep_mask"][:], dtype=np.uint8) > 0
    elif "roi_mask" in h5:
        valid_pixels = np.asarray(h5["roi_mask"][:], dtype=np.uint8) > 0
    else:
        valid_pixels = make_disk_mask(frame_shape, center_x, center_y, roi_radius)

    guide_disk = make_disk_mask(frame_shape, center_x, center_y, guide_radius)
    roi_disk = make_disk_mask(frame_shape, center_x, center_y, roi_radius)

    if "guide_ring_mask" in h5:
        guide_ring_line = np.asarray(h5["guide_ring_mask"][:], dtype=np.uint8) > 0
    else:
        guide_ring_line = np.zeros(frame_shape, dtype=bool)

    inside_guide = guide_disk & valid_pixels & ~guide_ring_line
    between_guide_and_roi = roi_disk & ~guide_disk & valid_pixels & ~guide_ring_line

    if not np.any(inside_guide):
        raise ValueError("The inside-guide region is empty.")
    if not np.any(between_guide_and_roi):
        raise ValueError("The between-guide-and-ROI region is empty.")

    return inside_guide, between_guide_and_roi


def average_intensity_by_region(
    frames: h5py.Dataset,
    inside_guide: np.ndarray,
    between_guide_and_roi: np.ndarray,
    chunk_frames: int,
) -> tuple[np.ndarray, np.ndarray]:
    frame_count = frames.shape[0]
    inside_mean = np.empty(frame_count, dtype=np.float64)
    between_mean = np.empty(frame_count, dtype=np.float64)

    inside_pixels = int(np.count_nonzero(inside_guide))
    between_pixels = int(np.count_nonzero(between_guide_and_roi))

    for start in range(0, frame_count, chunk_frames):
        stop = min(start + chunk_frames, frame_count)
        chunk = np.asarray(frames[start:stop], dtype=np.float32)
        inside_mean[start:stop] = chunk[:, inside_guide].sum(axis=1, dtype=np.float64) / inside_pixels
        between_mean[start:stop] = (
            chunk[:, between_guide_and_roi].sum(axis=1, dtype=np.float64) / between_pixels
        )
        print(f"Processed frames {start + 1}..{stop} of {frame_count}")

    return inside_mean, between_mean


def estimate_sample_period_s(time_s: np.ndarray) -> float:
    if time_s.size < 2:
        return 1.0
    diffs = np.diff(time_s)
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    if diffs.size == 0:
        return 1.0
    return float(np.median(diffs))


def seconds_to_odd_samples(window_s: float, sample_period_s: float, minimum: int = 3) -> int:
    if window_s <= 0:
        return 0
    samples = max(minimum, int(round(window_s / sample_period_s)))
    if samples % 2 == 0:
        samples += 1
    return samples


def rolling_median(values: np.ndarray, window_samples: int) -> np.ndarray:
    if window_samples <= 1:
        return values.astype(np.float64, copy=True)

    radius = window_samples // 2
    padded = np.pad(values.astype(np.float64), radius, mode="edge")
    output = np.empty_like(values, dtype=np.float64)
    for index in range(values.size):
        output[index] = np.median(padded[index:index + window_samples])
    return output


def interpolate_bad_values(values: np.ndarray, bad_values: np.ndarray) -> np.ndarray:
    cleaned = values.astype(np.float64, copy=True)
    good_values = ~bad_values

    if np.all(good_values):
        return cleaned
    if not np.any(good_values):
        raise ValueError("Outlier filtering marked every sample as an outlier.")

    indices = np.arange(values.size)
    cleaned[bad_values] = np.interp(indices[bad_values], indices[good_values], cleaned[good_values])
    return cleaned


def filter_outliers(
    values: np.ndarray,
    window_samples: int,
    mad_z_threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    if mad_z_threshold <= 0 or window_samples <= 1:
        return values.astype(np.float64, copy=True), np.zeros(values.shape, dtype=bool)

    median = rolling_median(values, window_samples)
    residual = values - median
    mad = rolling_median(np.abs(residual), window_samples)
    robust_sigma = 1.4826 * mad
    fallback_sigma = float(np.std(residual))
    if fallback_sigma <= 0:
        fallback_sigma = 1.0
    robust_sigma = np.where(robust_sigma > 1e-12, robust_sigma, fallback_sigma)

    outliers = np.abs(residual) > (mad_z_threshold * robust_sigma)
    return interpolate_bad_values(values, outliers), outliers


def butterworth_low_pass_filter(
    values: np.ndarray,
    sample_rate_hz: float,
    cutoff_hz: float,
    order: int,
) -> np.ndarray:
    if cutoff_hz <= 0:
        return values.astype(np.float64, copy=True)

    nyquist_hz = sample_rate_hz / 2.0
    if cutoff_hz >= nyquist_hz:
        raise ValueError(
            f"--lowpass-cutoff-hz must be below the Nyquist frequency ({nyquist_hz:.6g} Hz)."
        )
    if order < 1:
        raise ValueError("--lowpass-order must be at least 1.")

    sos = butter(order, cutoff_hz, btype="lowpass", fs=sample_rate_hz, output="sos")
    return sosfiltfilt(sos, values.astype(np.float64))


def save_csv(
    output_csv: Path,
    time_s: np.ndarray,
    inside_mean: np.ndarray,
    between_mean: np.ndarray,
    inside_clean: np.ndarray,
    between_clean: np.ndarray,
    inside_lowpass: np.ndarray,
    between_lowpass: np.ndarray,
    inside_outliers: np.ndarray,
    between_outliers: np.ndarray,
) -> None:
    table = np.column_stack(
        (
            time_s,
            inside_mean,
            between_mean,
            inside_clean,
            between_clean,
            inside_lowpass,
            between_lowpass,
            inside_outliers.astype(np.uint8),
            between_outliers.astype(np.uint8),
        )
    )
    header = (
        "time_s,"
        "inside_guide_mean_intensity,"
        "between_guide_and_roi_mean_intensity,"
        "inside_guide_clean_intensity,"
        "between_guide_and_roi_clean_intensity,"
        "inside_guide_lowpass_intensity,"
        "between_guide_and_roi_lowpass_intensity,"
        "inside_guide_outlier,"
        "between_guide_and_roi_outlier"
    )
    np.savetxt(output_csv, table, delimiter=",", header=header, comments="", fmt="%.8f")


def timestamped_fallback_path(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")


def save_csv_with_fallback(
    output_csv: Path,
    time_s: np.ndarray,
    inside_mean: np.ndarray,
    between_mean: np.ndarray,
    inside_clean: np.ndarray,
    between_clean: np.ndarray,
    inside_lowpass: np.ndarray,
    between_lowpass: np.ndarray,
    inside_outliers: np.ndarray,
    between_outliers: np.ndarray,
) -> Path:
    try:
        save_csv(
            output_csv,
            time_s,
            inside_mean,
            between_mean,
            inside_clean,
            between_clean,
            inside_lowpass,
            between_lowpass,
            inside_outliers,
            between_outliers,
        )
        return output_csv
    except PermissionError:
        fallback_csv = timestamped_fallback_path(output_csv)
        print(f"CSV is locked, saving to alternate file: {fallback_csv}")
        save_csv(
            fallback_csv,
            time_s,
            inside_mean,
            between_mean,
            inside_clean,
            between_clean,
            inside_lowpass,
            between_lowpass,
            inside_outliers,
            between_outliers,
        )
        return fallback_csv


def save_plot(
    output_png: Path,
    time_s: np.ndarray,
    inside_mean: np.ndarray,
    between_mean: np.ndarray,
    inside_clean: np.ndarray,
    between_clean: np.ndarray,
    inside_lowpass: np.ndarray,
    between_lowpass: np.ndarray,
    show: bool,
) -> Path:
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True, constrained_layout=True)

    axes[0].plot(time_s, inside_mean, label="Core raw", linewidth=0.9, alpha=0.35)
    axes[0].plot(time_s, between_mean, label="Downcomer raw", linewidth=0.9, alpha=0.35)
    axes[0].plot(time_s, inside_clean, label="Core cleaned", linewidth=1.4)
    axes[0].plot(time_s, between_clean, label="Downcomer cleaned", linewidth=1.4)
    axes[0].set_title("Average Intensity by Region")
    axes[0].set_ylabel("Average intensity")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    axes[1].plot(time_s, inside_clean, label="Core raw", linewidth=0.9, alpha=0.35)
    axes[1].plot(time_s, between_clean, label="Downcomer raw", linewidth=0.9, alpha=0.35)
    axes[1].plot(time_s, inside_lowpass, label="Core cleaned", linewidth=1.4)
    axes[1].plot(time_s, between_lowpass, label="Downcomer cleaned", linewidth=1.4)
    axes[1].set_title("Butterworth Low-Pass Filtered Intensity")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Average intensity")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    try:
        fig.savefig(output_png, dpi=160)
    except PermissionError:
        fallback_png = timestamped_fallback_path(output_png)
        print(f"Plot image is locked, saving to alternate file: {fallback_png}")
        fig.savefig(fallback_png, dpi=160)
        output_png = fallback_png
    plt.close(fig)
    return output_png


def show_interactive_plot(
    time_s: np.ndarray,
    inside_clean: np.ndarray,
    between_clean: np.ndarray,
    inside_lowpass: np.ndarray,
    between_lowpass: np.ndarray,
) -> None:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
    from matplotlib.figure import Figure
    from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

    app = QApplication.instance() or QApplication([])

    window = QMainWindow()
    window.setWindowTitle("Interactive Region Intensity Plot")

    canvas = FigureCanvas(Figure(figsize=(11, 8)))
    axes = canvas.figure.subplots(2, 1, sharex=True)
    canvas.figure.subplots_adjust(left=0.08, right=0.98, bottom=0.08, top=0.94, hspace=0.28)

    axes[0].plot(time_s, inside_clean, label="Inside guide cleaned", linewidth=1.2)
    axes[0].plot(time_s, between_clean, label="Between guide/ROI cleaned", linewidth=1.2)
    axes[0].set_title("Outlier-Cleaned Average Intensity")
    axes[0].set_ylabel("Average intensity")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    axes[1].plot(time_s, inside_lowpass, label="Inside guide low-pass", linewidth=1.4)
    axes[1].plot(time_s, between_lowpass, label="Between guide/ROI low-pass", linewidth=1.4)
    axes[1].set_title("Butterworth Low-Pass Filtered Intensity")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylabel("Average intensity")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    cursor_lines = [axis.axvline(time_s[0], color="black", linewidth=0.9, alpha=0.55) for axis in axes]
    readout = QLabel()
    readout.setMinimumHeight(28)
    readout.setText("Move the mouse over the plot")

    def update_readout(event) -> None:
        if event.xdata is None:
            return
        index = int(np.argmin(np.abs(time_s - event.xdata)))
        x_value = float(time_s[index])
        for line in cursor_lines:
            line.set_xdata([x_value, x_value])
        readout.setText(
            f"t = {x_value:.4f} s | "
            f"inside guide clean = {inside_clean[index]:.4f} | "
            f"between guide/ROI clean = {between_clean[index]:.4f}"
        )
        canvas.draw_idle()

    canvas.mpl_connect("motion_notify_event", update_readout)

    layout = QVBoxLayout()
    layout.addWidget(NavigationToolbar(canvas, window))
    layout.addWidget(canvas)
    layout.addWidget(readout)

    container = QWidget()
    container.setLayout(layout)
    window.setCentralWidget(container)
    window.resize(1200, 850)
    window.show()
    app.exec()


def main() -> None:
    args = parse_args()
    input_h5 = args.input_h5
    output_png = args.output_png or input_h5.with_name(f"{input_h5.stem}_region_intensity_timeseries.png")
    output_csv = args.output_csv or input_h5.with_name(f"{input_h5.stem}_region_intensity_timeseries.csv")

    if args.chunk_frames < 1:
        raise ValueError("--chunk-frames must be at least 1.")
    if args.outlier_window_s < 0:
        raise ValueError("--outlier-window-s cannot be negative.")
    if args.lowpass_cutoff_hz < 0:
        raise ValueError("--lowpass-cutoff-hz cannot be negative.")
    if args.lowpass_order < 1:
        raise ValueError("--lowpass-order must be at least 1.")
    if not input_h5.exists():
        raise FileNotFoundError(input_h5)

    with h5py.File(input_h5, "r") as h5:
        if "frames" not in h5:
            raise KeyError(f"No /frames dataset found in {input_h5}")

        frames = h5["frames"]
        if len(frames.shape) != 3:
            raise ValueError(f"Expected /frames to be 3D, got shape {frames.shape}")

        frame_count, frame_h, frame_w = frames.shape
        time_s = np.asarray(h5["time_s"][:], dtype=np.float64) if "time_s" in h5 else np.arange(frame_count)
        if time_s.shape[0] != frame_count:
            raise ValueError(f"/time_s has {time_s.shape[0]} entries but /frames has {frame_count} frames.")

        inside_guide, between_guide_and_roi = load_region_masks(h5, (frame_h, frame_w))
        print(f"Inside-guide pixels: {np.count_nonzero(inside_guide)}")
        print(f"Between-guide-and-ROI pixels: {np.count_nonzero(between_guide_and_roi)}")

        inside_mean, between_mean = average_intensity_by_region(
            frames,
            inside_guide,
            between_guide_and_roi,
            args.chunk_frames,
        )

    sample_period_s = estimate_sample_period_s(time_s)
    sample_rate_hz = 1.0 / sample_period_s
    outlier_window_samples = seconds_to_odd_samples(args.outlier_window_s, sample_period_s)

    inside_clean, inside_outliers = filter_outliers(
        inside_mean,
        outlier_window_samples,
        args.outlier_mad_z,
    )
    between_clean, between_outliers = filter_outliers(
        between_mean,
        outlier_window_samples,
        args.outlier_mad_z,
    )
    inside_lowpass = butterworth_low_pass_filter(
        inside_clean,
        sample_rate_hz,
        args.lowpass_cutoff_hz,
        args.lowpass_order,
    )
    between_lowpass = butterworth_low_pass_filter(
        between_clean,
        sample_rate_hz,
        args.lowpass_cutoff_hz,
        args.lowpass_order,
    )

    print(f"Sample period: {sample_period_s:.6f} s")
    print(f"Sample rate: {sample_rate_hz:.6f} Hz")
    print(f"Outlier window: {outlier_window_samples} samples")
    print(f"Butterworth low-pass cutoff: {args.lowpass_cutoff_hz:g} Hz")
    print(f"Butterworth low-pass order: {args.lowpass_order}")
    print(f"Inside-guide outliers replaced: {np.count_nonzero(inside_outliers)}")
    print(f"Between-guide-and-ROI outliers replaced: {np.count_nonzero(between_outliers)}")

    if args.interactive_only:
        show_interactive_plot(
            time_s,
            inside_clean,
            between_clean,
            inside_lowpass,
            between_lowpass,
        )
        return

    output_csv = save_csv_with_fallback(
        output_csv,
        time_s,
        inside_mean,
        between_mean,
        inside_clean,
        between_clean,
        inside_lowpass,
        between_lowpass,
        inside_outliers,
        between_outliers,
    )
    output_png = save_plot(
        output_png,
        time_s,
        inside_mean,
        between_mean,
        inside_clean,
        between_clean,
        inside_lowpass,
        between_lowpass,
        args.show,
    )

    print(f"Saved CSV: {output_csv}")
    print(f"Saved plot: {output_png}")

    if args.show:
        show_interactive_plot(
            time_s,
            inside_clean,
            between_clean,
            inside_lowpass,
            between_lowpass,
        )


if __name__ == "__main__":
    main()
