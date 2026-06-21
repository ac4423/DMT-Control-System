from pathlib import Path

import cv2
import h5py
import hdf5plugin  # noqa: F401 - registers compressed HDF5 filters
import numpy as np


INPUT_H5_PATH = Path(r"E:\RPV Test\camera_20260601_154017.h5")

# Human-readable frame numbers. Frame 1500 maps to dataset index 1499.
START_FRAME = 5600
END_FRAME = 5900
FRAME_NUMBERS_ARE_ONE_BASED = True

FRAME_RANGE_LABEL = f"frames_{START_FRAME}_to_{END_FRAME if END_FRAME is not None else 'final'}"
OUTPUT_PNG_PATH = INPUT_H5_PATH.with_name(f"{INPUT_H5_PATH.stem}_{FRAME_RANGE_LABEL}_roi_average.png")
OUTPUT_H5_PATH = INPUT_H5_PATH.with_name(f"{INPUT_H5_PATH.stem}_{FRAME_RANGE_LABEL}_roi_average.h5")

# Matched to view_intensity_legend.py.
ROI_CENTER_X = 505
ROI_CENTER_Y = 580
ROI_RADIUS = 440

CHUNK_FRAMES = 128


def frame_number_to_index(frame_number: int) -> int:
    return frame_number - 1 if FRAME_NUMBERS_ARE_ONE_BASED else frame_number


def make_roi_mask(shape: tuple[int, int]) -> np.ndarray:
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.circle(mask, (ROI_CENTER_X, ROI_CENTER_Y), ROI_RADIUS, 255, -1, cv2.LINE_AA)
    return mask


def as_grayscale(frame: np.ndarray) -> np.ndarray:
    frame = np.asarray(frame)
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3 and frame.shape[2] == 3:
        return cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    if frame.ndim == 3 and frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_RGBA2GRAY)
    raise ValueError(f"Unsupported frame shape: {frame.shape}")


def write_average_h5(
    output_path: Path,
    average: np.ndarray,
    roi_mask: np.ndarray,
    source_path: Path,
    start_index: int,
    end_index: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_path, "w") as h5:
        h5.create_dataset("average", data=average.astype(np.float32), dtype=np.float32, compression="gzip", compression_opts=9)
        h5.create_dataset("roi_mask", data=roi_mask, dtype=np.uint8, compression="gzip", compression_opts=9)
        h5.attrs["source_file"] = str(source_path)
        h5.attrs["source_start_frame"] = START_FRAME
        h5.attrs["source_end_frame"] = END_FRAME if END_FRAME is not None else "final"
        h5.attrs["source_start_index"] = start_index
        h5.attrs["source_end_index"] = end_index
        h5.attrs["frame_numbers_are_one_based"] = FRAME_NUMBERS_ARE_ONE_BASED
        h5.attrs["roi_center_x"] = ROI_CENTER_X
        h5.attrs["roi_center_y"] = ROI_CENTER_Y
        h5.attrs["roi_radius"] = ROI_RADIUS
        h5.attrs["processing"] = "temporal average from START_FRAME to END_FRAME; pixels outside ROI set to zero"


def save_png(image: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image_u8 = np.clip(np.rint(image), 0, 255).astype(np.uint8)
    if not cv2.imwrite(str(output_path), image_u8):
        raise RuntimeError(f"Failed to save image to {output_path}")


def temporal_average_roi() -> None:
    if not INPUT_H5_PATH.exists():
        raise FileNotFoundError(INPUT_H5_PATH)

    start_index = frame_number_to_index(START_FRAME)
    if start_index < 0:
        raise ValueError(f"Invalid start frame: {START_FRAME}")

    with h5py.File(INPUT_H5_PATH, "r") as h5:
        if "frames" not in h5:
            raise KeyError("Input HDF5 file has no /frames dataset.")

        frames = h5["frames"]
        frame_count = frames.shape[0]
        end_index = frame_count - 1 if END_FRAME is None else frame_number_to_index(END_FRAME)
        if end_index < start_index:
            raise ValueError(f"Invalid frame range: {START_FRAME}..{END_FRAME}")
        if start_index >= frame_count:
            raise IndexError(
                f"Start frame {START_FRAME} maps to index {start_index}, "
                f"but the file only has indexes 0..{frame_count - 1}."
            )
        if end_index >= frame_count:
            raise IndexError(
                f"End frame {END_FRAME} maps to index {end_index}, "
                f"but the file only has indexes 0..{frame_count - 1}."
            )

        first_frame = as_grayscale(frames[start_index])
        frame_h, frame_w = first_frame.shape
        roi_mask = make_roi_mask((frame_h, frame_w))
        roi_pixels = roi_mask > 0

        accumulator = np.zeros((frame_h, frame_w), dtype=np.float64)
        frames_used = 0
        total_frames_to_average = end_index - start_index + 1

        for chunk_start in range(start_index, end_index + 1, CHUNK_FRAMES):
            chunk_end = min(end_index + 1, chunk_start + CHUNK_FRAMES)
            chunk = frames[chunk_start:chunk_end]

            if chunk.ndim == 3:
                accumulator[roi_pixels] += chunk[:, roi_pixels].sum(axis=0, dtype=np.float64)
                frames_used += chunk.shape[0]
            else:
                for frame in chunk:
                    gray = as_grayscale(frame)
                    accumulator[roi_pixels] += gray[roi_pixels].astype(np.float64)
                    frames_used += 1

            print(f"Averaged {frames_used}/{total_frames_to_average} frames")

    average = np.zeros_like(accumulator, dtype=np.float32)
    average[roi_pixels] = (accumulator[roi_pixels] / frames_used).astype(np.float32)

    save_png(average, OUTPUT_PNG_PATH)
    write_average_h5(OUTPUT_H5_PATH, average, roi_mask, INPUT_H5_PATH, start_index, end_index)

    print(f"Saved ROI temporal average PNG to: {OUTPUT_PNG_PATH}")
    print(f"Saved float32 average and ROI mask H5 to: {OUTPUT_H5_PATH}")


if __name__ == "__main__":
    temporal_average_roi()
