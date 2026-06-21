from pathlib import Path

import h5py
import hdf5plugin  # noqa: F401 - registers compressed HDF5 filters
import numpy as np


H5_PATH = Path(r"E:\RPV Test\camera_20260601_154017.h5")
FRAME_NUMBER = 3500  # Human-readable frame number, so this reads dataset index 4305.
OUTPUT_PATH = H5_PATH.with_name(f"{H5_PATH.stem}_frame_{FRAME_NUMBER:06d}.png")


def save_png(frame: np.ndarray, output_path: Path) -> None:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required to save the PNG. Install it with: pip install opencv-python") from exc

    frame = np.asarray(frame)

    if frame.ndim == 3 and frame.shape[2] == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), frame):
        raise RuntimeError(f"Failed to save image to {output_path}")


def main() -> None:
    if not H5_PATH.exists():
        raise FileNotFoundError(H5_PATH)

    frame_index = FRAME_NUMBER - 1

    with h5py.File(H5_PATH, "r") as h5:
        if "frames" not in h5:
            raise KeyError("No /frames dataset found in the HDF5 file.")

        frames = h5["frames"]
        frame_count = frames.shape[0]

        if frame_index < 0 or frame_index >= frame_count:
            raise IndexError(
                f"Frame number {FRAME_NUMBER} is outside the file's range of 1..{frame_count}."
            )

        frame = frames[frame_index]
        save_png(frame, OUTPUT_PATH)

    print(f"Saved frame {FRAME_NUMBER} to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
