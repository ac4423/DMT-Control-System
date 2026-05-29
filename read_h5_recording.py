import argparse
import os
from pathlib import Path

import h5py
import hdf5plugin  # noqa: F401 - registers Blosc/LZF-style HDF5 filters
import numpy as np


def _format_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def _print_attrs(h5: h5py.File) -> None:
    if not h5.attrs:
        print("Attributes: none")
        return
    print("Attributes:")
    for key, value in h5.attrs.items():
        print(f"  {key}: {value}")


def _print_datasets(h5: h5py.File) -> None:
    print("Datasets:")
    for name, ds in h5.items():
        if not isinstance(ds, h5py.Dataset):
            continue
        compression = ds.compression or "plugin/filter"
        print(
            f"  /{name}: shape={ds.shape}, dtype={ds.dtype}, "
            f"chunks={ds.chunks}, compression={compression}"
        )


def _estimate_fps(h5: h5py.File) -> None:
    frame_count = h5["frames"].shape[0] if "frames" in h5 else 0
    print(f"Frames: {frame_count}")
    if frame_count < 2:
        return

    time_name = "time_s" if "time_s" in h5 else "timestamps"
    times = np.asarray(h5[time_name][:], dtype=float)
    times = times[np.isfinite(times)]
    if times.size < 2:
        return

    duration = float(times[-1] - times[0])
    if duration <= 0:
        return
    fps = (times.size - 1) / duration
    print(f"Duration: {duration:.3f} s")
    print(f"Estimated FPS: {fps:.2f}")


def _print_frame_stats(h5: h5py.File, frame_index: int) -> None:
    frames = h5["frames"]
    if frames.shape[0] == 0:
        return
    index = max(0, min(int(frame_index), frames.shape[0] - 1))
    frame = np.asarray(frames[index])
    print(f"Frame {index} stats:")
    print(f"  shape: {frame.shape}")
    print(f"  min/max: {frame.min()} / {frame.max()}")
    print(f"  mean/std: {frame.mean():.2f} / {frame.std():.2f}")

    if "time_s" in h5:
        print(f"  time_s: {float(h5['time_s'][index]):.6f}")
    if "timestamps" in h5:
        print(f"  timestamp: {float(h5['timestamps'][index]):.6f}")
    if "heights_mm" in h5:
        print(f"  height_mm: {float(h5['heights_mm'][index]):.3f}")


def _export_frames(h5: h5py.File, output_dir: Path, indexes: list[int]) -> None:
    try:
        import cv2
    except ImportError:
        print("OpenCV is not installed, so frame export is unavailable.")
        return

    frames = h5["frames"]
    if frames.shape[0] == 0:
        print("No frames to export.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    for raw_index in indexes:
        index = max(0, min(int(raw_index), frames.shape[0] - 1))
        frame = np.asarray(frames[index])
        out_path = output_dir / f"frame_{index:06d}.png"
        ok = cv2.imwrite(str(out_path), frame)
        print(f"Exported {out_path}" if ok else f"Failed to export {out_path}")


def inspect_recording(path: Path, frame_index: int, export_dir: Path | None, export_indexes: list[int]) -> None:
    if not path.exists():
        raise FileNotFoundError(path)

    print(f"File: {path}")
    print(f"Size: {_format_bytes(path.stat().st_size)}")
    with h5py.File(path, "r") as h5:
        _print_attrs(h5)
        _print_datasets(h5)
        if "frames" not in h5:
            print("No /frames dataset found.")
            return
        _estimate_fps(h5)
        _print_frame_stats(h5, frame_index)
        if export_dir is not None:
            _export_frames(h5, export_dir, export_indexes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a camera HDF5 recording.")
    parser.add_argument("path", help="Path to camera_*.h5")
    parser.add_argument("--frame", type=int, default=0, help="Frame index for detailed stats")
    parser.add_argument("--export-dir", help="Optional folder to export PNG frames into")
    parser.add_argument(
        "--export-frames",
        type=int,
        nargs="*",
        default=[0],
        help="Frame indexes to export when --export-dir is set",
    )
    args = parser.parse_args()

    inspect_recording(
        Path(args.path),
        frame_index=args.frame,
        export_dir=Path(args.export_dir) if args.export_dir else None,
        export_indexes=args.export_frames,
    )


if __name__ == "__main__":
    main()
