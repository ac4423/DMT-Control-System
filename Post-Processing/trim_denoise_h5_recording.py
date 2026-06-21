from pathlib import Path

import cv2
import h5py
import hdf5plugin  # noqa: F401 - registers HDF5 plugin filters
import numpy as np


INPUT_H5_PATH = Path(r"E:\RPV Test\camera_20260601_154017.h5")
AVERAGE_IMAGE_PATH = Path(r"E:\RPV Test\camera_20260601_154017_frames_5600_to_5900_roi_average.h5")
OUTPUT_H5_PATH = Path(r"E:\RPV Test\camera_20260601_154017_from_3500_avg_5600_to_5900_roi_masked_nlm_bgcomp_zstd9.h5")
OVERLAY_IMAGE_PATH = Path(r"E:\RPV Test\RPV Data Display\RPV Image\RPV_Silouette.png")

# Human-readable frame numbers. With one-based numbering, frame 1 is dataset index 0.
FRAME_NUMBERS_ARE_ONE_BASED = True
START_FRAME = 3500
END_FRAME = None

# Keep these matched to view_intensity_legend.py.
NLM_H = 20
NLM_TEMPLATE_WINDOW_SIZE = 7
NLM_SEARCH_WINDOW_SIZE = 21
BACKGROUND_DARK_FLOOR = 20.0

ROI_CENTER_X = 505
ROI_CENTER_Y = 580
ROI_RADIUS = 440
GUIDE_CIRCLE_RADIUS = 380
GUIDE_CIRCLE_THICKNESS = 3
ROI_ROTATION_DEG = -2
OVERLAY_ROTATION_DEG = ROI_ROTATION_DEG

OVERLAY_X = 120
OVERLAY_Y = 235
OVERLAY_SCALE = 1.4
OVERLAY_ALPHA_THRESHOLD = 1

PROGRESS_EVERY_N_FRAMES = 50


def frame_number_to_index(frame_number: int) -> int:
    return frame_number - 1 if FRAME_NUMBERS_ARE_ONE_BASED else frame_number


def as_grayscale(frame: np.ndarray) -> np.ndarray:
    frame = np.asarray(frame)
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3 and frame.shape[2] == 3:
        return cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    if frame.ndim == 3 and frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_RGBA2GRAY)
    raise ValueError(f"Unsupported frame shape: {frame.shape}")


def make_circle_mask(shape: tuple[int, int], radius: int) -> np.ndarray:
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.circle(mask, (ROI_CENTER_X, ROI_CENTER_Y), radius, 255, -1, cv2.LINE_AA)
    return mask


def make_roi_mask(shape: tuple[int, int]) -> np.ndarray:
    return make_circle_mask(shape, ROI_RADIUS)


def make_guide_ring_mask(shape: tuple[int, int]) -> np.ndarray:
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.circle(
        mask,
        (ROI_CENTER_X, ROI_CENTER_Y),
        GUIDE_CIRCLE_RADIUS,
        255,
        GUIDE_CIRCLE_THICKNESS,
        cv2.LINE_AA,
    )
    return mask


def rotate_overlay_image(overlay: np.ndarray, angle_deg: float) -> np.ndarray:
    if angle_deg == 0:
        return overlay.copy()

    height, width = overlay.shape[:2]
    rotation_matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle_deg, 1.0)
    return cv2.warpAffine(
        overlay,
        rotation_matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )


def load_overlay_image() -> np.ndarray:
    overlay = cv2.imread(str(OVERLAY_IMAGE_PATH), cv2.IMREAD_UNCHANGED)
    if overlay is None:
        raise FileNotFoundError(f"Could not read overlay image: {OVERLAY_IMAGE_PATH}")

    if overlay.ndim == 2:
        overlay = cv2.cvtColor(overlay, cv2.COLOR_GRAY2BGRA)
    elif overlay.shape[2] == 3:
        alpha = np.full(overlay.shape[:2] + (1,), 255, dtype=np.uint8)
        overlay = np.dstack((overlay, alpha))

    return rotate_overlay_image(overlay, OVERLAY_ROTATION_DEG)


def make_overlay_mask(shape: tuple[int, int], overlay: np.ndarray) -> np.ndarray:
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)
    alpha = overlay[:, :, 3]

    overlay_w = max(1, int(round(alpha.shape[1] * OVERLAY_SCALE)))
    overlay_h = max(1, int(round(alpha.shape[0] * OVERLAY_SCALE)))
    alpha = cv2.resize(alpha, (overlay_w, overlay_h), interpolation=cv2.INTER_AREA)

    x0 = int(round(OVERLAY_X))
    y0 = int(round(OVERLAY_Y))
    x1 = x0 + overlay_w
    y1 = y0 + overlay_h

    clip_x0 = max(0, x0)
    clip_y0 = max(0, y0)
    clip_x1 = min(width, x1)
    clip_y1 = min(height, y1)

    if clip_x0 >= clip_x1 or clip_y0 >= clip_y1:
        return mask

    overlay_x0 = clip_x0 - x0
    overlay_y0 = clip_y0 - y0
    overlay_x1 = overlay_x0 + (clip_x1 - clip_x0)
    overlay_y1 = overlay_y0 + (clip_y1 - clip_y0)

    alpha_crop = alpha[overlay_y0:overlay_y1, overlay_x0:overlay_x1]
    mask[clip_y0:clip_y1, clip_x0:clip_x1] = (alpha_crop >= OVERLAY_ALPHA_THRESHOLD).astype(np.uint8) * 255
    return mask


def make_keep_mask(shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    roi_mask = make_roi_mask(shape)
    guide_ring_mask = make_guide_ring_mask(shape)
    overlay_mask = make_overlay_mask(shape, load_overlay_image())
    keep_mask = np.where((roi_mask > 0) & (overlay_mask == 0), 255, 0).astype(np.uint8)
    return keep_mask, roi_mask, guide_ring_mask, overlay_mask


def load_average_image(expected_shape: tuple[int, int]) -> np.ndarray:
    if not AVERAGE_IMAGE_PATH.exists():
        raise FileNotFoundError(f"Could not find average image: {AVERAGE_IMAGE_PATH}")

    if AVERAGE_IMAGE_PATH.suffix.lower() in {".h5", ".hdf5"}:
        with h5py.File(AVERAGE_IMAGE_PATH, "r") as h5:
            if "average" not in h5:
                raise KeyError(f"No /average dataset found in {AVERAGE_IMAGE_PATH}")
            average = np.asarray(h5["average"][:], dtype=np.float32)
    else:
        average = cv2.imread(str(AVERAGE_IMAGE_PATH), cv2.IMREAD_GRAYSCALE)
        if average is None:
            raise RuntimeError(f"Could not read average image: {AVERAGE_IMAGE_PATH}")
        average = average.astype(np.float32)

    if average.shape != expected_shape:
        raise ValueError(
            f"Average image shape {average.shape} does not match frame shape {expected_shape}."
        )

    return average


def apply_keep_mask(frame: np.ndarray, keep_mask: np.ndarray) -> np.ndarray:
    output = np.asarray(frame).copy()
    output[keep_mask == 0] = 0
    return output


def mask_bounds(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    if ys.size == 0 or xs.size == 0:
        raise ValueError("The keep mask is empty.")

    y0 = int(ys.min())
    y1 = int(ys.max()) + 1
    x0 = int(xs.min())
    x1 = int(xs.max()) + 1
    return y0, y1, x0, x1


def denoise_image(image: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoising(
        image,
        None,
        h=NLM_H,
        templateWindowSize=NLM_TEMPLATE_WINDOW_SIZE,
        searchWindowSize=NLM_SEARCH_WINDOW_SIZE,
    )


def weighted_background_subtract(
    image: np.ndarray,
    average: np.ndarray,
    keep_mask: np.ndarray,
    dark_floor: float = BACKGROUND_DARK_FLOOR,
) -> np.ndarray:
    corrected = np.zeros(image.shape, dtype=np.float32)
    valid_pixels = keep_mask > 0

    image_float = image.astype(np.float32)
    average_float = average.astype(np.float32)
    correction_strength = np.clip((image_float - dark_floor) / (255.0 - dark_floor), 0.0, 1.0)
    background_above_floor = np.maximum(average_float - dark_floor, 0.0)

    corrected[valid_pixels] = image_float[valid_pixels] - (
        correction_strength[valid_pixels] * background_above_floor[valid_pixels]
    )
    corrected[valid_pixels] = np.clip(corrected[valid_pixels], 0.0, 255.0)
    return corrected


def process_frame(
    frame: np.ndarray,
    keep_mask: np.ndarray,
    average: np.ndarray,
    keep_bounds: tuple[int, int, int, int],
) -> np.ndarray:
    frame = as_grayscale(frame)
    if frame.dtype != np.uint8:
        frame = np.clip(frame, 0, 255).astype(np.uint8)

    y0, y1, x0, x1 = keep_bounds
    frame_crop = frame[y0:y1, x0:x1]
    mask_crop = keep_mask[y0:y1, x0:x1]
    average_crop = average[y0:y1, x0:x1]

    masked = apply_keep_mask(frame_crop, mask_crop)
    denoised = denoise_image(masked)
    denoised = apply_keep_mask(denoised, mask_crop)
    corrected = weighted_background_subtract(denoised, average_crop, mask_crop)

    output = np.zeros(frame.shape, dtype=np.uint8)
    output[y0:y1, x0:x1] = np.clip(np.rint(corrected), 0, 255).astype(np.uint8)
    return output


def frame_compression_kwargs() -> tuple[dict, str]:
    try:
        return (
            hdf5plugin.Blosc(
                cname="zstd",
                clevel=9,
                shuffle=hdf5plugin.Blosc.BITSHUFFLE,
            ),
            "blosc-zstd-clevel9-bitshuffle",
        )
    except Exception:
        return ({"compression": "gzip", "compression_opts": 9}, "gzip-9")


def copy_root_attrs(src: h5py.File, dst: h5py.File, start_index: int, end_index: int, compression_name: str) -> None:
    for key, value in src.attrs.items():
        dst.attrs[key] = value

    dst.attrs["source_file"] = str(INPUT_H5_PATH)
    dst.attrs["source_start_frame"] = START_FRAME
    dst.attrs["source_end_frame"] = END_FRAME if END_FRAME is not None else "final"
    dst.attrs["source_start_index"] = start_index
    dst.attrs["source_end_index"] = end_index
    dst.attrs["frame_numbers_are_one_based"] = FRAME_NUMBERS_ARE_ONE_BASED
    dst.attrs["processing"] = (
        "trimmed, circular ROI masked, rotated overlay silhouette excluded, "
        "OpenCV fastNlMeansDenoising, weighted average-background subtraction, remasked"
    )
    dst.attrs["average_background_file"] = str(AVERAGE_IMAGE_PATH)
    dst.attrs["background_dark_floor"] = BACKGROUND_DARK_FLOOR
    dst.attrs["nlm_h"] = NLM_H
    dst.attrs["nlm_template_window_size"] = NLM_TEMPLATE_WINDOW_SIZE
    dst.attrs["nlm_search_window_size"] = NLM_SEARCH_WINDOW_SIZE
    dst.attrs["roi_center_x"] = ROI_CENTER_X
    dst.attrs["roi_center_y"] = ROI_CENTER_Y
    dst.attrs["roi_radius"] = ROI_RADIUS
    dst.attrs["guide_circle_radius"] = GUIDE_CIRCLE_RADIUS
    dst.attrs["guide_circle_thickness"] = GUIDE_CIRCLE_THICKNESS
    dst.attrs["roi_rotation_deg"] = ROI_ROTATION_DEG
    dst.attrs["overlay_rotation_deg"] = OVERLAY_ROTATION_DEG
    dst.attrs["overlay_image_path"] = str(OVERLAY_IMAGE_PATH)
    dst.attrs["overlay_x"] = OVERLAY_X
    dst.attrs["overlay_y"] = OVERLAY_Y
    dst.attrs["overlay_scale"] = OVERLAY_SCALE
    dst.attrs["overlay_alpha_threshold"] = OVERLAY_ALPHA_THRESHOLD
    dst.attrs["frame_compression"] = compression_name


def copy_dataset_attrs(src_ds: h5py.Dataset, dst_ds: h5py.Dataset) -> None:
    for key, value in src_ds.attrs.items():
        dst_ds.attrs[key] = value


def copy_vector_dataset(src: h5py.File, dst: h5py.File, name: str, src_slice: slice) -> None:
    if name not in src:
        return

    data = src[name][src_slice]
    dst_ds = dst.create_dataset(name, data=data, dtype=src[name].dtype)
    copy_dataset_attrs(src[name], dst_ds)


def copy_rebased_time_s(src: h5py.File, dst: h5py.File, src_slice: slice) -> None:
    if "time_s" not in src:
        return

    time_s = np.asarray(src["time_s"][src_slice], dtype=np.float64)
    finite = np.isfinite(time_s)
    if finite.any():
        time_s[finite] = time_s[finite] - time_s[finite][0]

    dst_ds = dst.create_dataset("time_s", data=time_s, dtype=np.float64)
    copy_dataset_attrs(src["time_s"], dst_ds)
    dst_ds.attrs["rebased_to_zero_at_source_frame"] = START_FRAME


def trim_and_process_h5() -> None:
    if not INPUT_H5_PATH.exists():
        raise FileNotFoundError(INPUT_H5_PATH)

    start_index = frame_number_to_index(START_FRAME)
    if start_index < 0:
        raise ValueError(f"Invalid frame range: {START_FRAME}..{END_FRAME}")

    with h5py.File(INPUT_H5_PATH, "r") as src:
        if "frames" not in src:
            raise KeyError("Input HDF5 file has no /frames dataset.")

        frames = src["frames"]
        total_frames = frames.shape[0]
        end_index = total_frames - 1 if END_FRAME is None else frame_number_to_index(END_FRAME)
        if end_index < start_index:
            raise ValueError(f"Invalid frame range: {START_FRAME}..{END_FRAME}")
        if end_index >= total_frames:
            raise IndexError(
                f"End frame {END_FRAME} maps to index {end_index}, "
                f"but the file only has indexes 0..{total_frames - 1}."
            )

        first_frame = as_grayscale(frames[start_index])
        frame_h, frame_w = first_frame.shape
        frame_count = end_index - start_index + 1
        source_slice = slice(start_index, end_index + 1)
        keep_mask, roi_mask, guide_ring_mask, overlay_mask = make_keep_mask((frame_h, frame_w))
        keep_bounds = mask_bounds(keep_mask)
        average = load_average_image((frame_h, frame_w))

        OUTPUT_H5_PATH.parent.mkdir(parents=True, exist_ok=True)
        compression, compression_name = frame_compression_kwargs()

        with h5py.File(OUTPUT_H5_PATH, "w") as dst:
            copy_root_attrs(src, dst, start_index, end_index, compression_name)

            dst_frames = dst.create_dataset(
                "frames",
                shape=(frame_count, frame_h, frame_w),
                maxshape=(frame_count, frame_h, frame_w),
                dtype=np.uint8,
                chunks=(1, frame_h, frame_w),
                **compression,
            )
            copy_dataset_attrs(frames, dst_frames)

            dst.create_dataset("keep_mask", data=keep_mask, dtype=np.uint8, compression="gzip", compression_opts=9)
            dst.create_dataset("roi_mask", data=roi_mask, dtype=np.uint8, compression="gzip", compression_opts=9)
            dst.create_dataset("guide_ring_mask", data=guide_ring_mask, dtype=np.uint8, compression="gzip", compression_opts=9)
            dst.create_dataset("overlay_mask", data=overlay_mask, dtype=np.uint8, compression="gzip", compression_opts=9)
            copy_vector_dataset(src, dst, "timestamps", source_slice)
            copy_vector_dataset(src, dst, "heights_mm", source_slice)
            copy_rebased_time_s(src, dst, source_slice)

            print(
                f"Writing {frame_count} processed frames from source indexes "
                f"{start_index}..{end_index} using {compression_name}",
                flush=True,
            )
            print(
                "Pipeline: full ROI -> rotated overlay exclusion -> mask -> NLM -> "
                f"weighted background subtraction with dark floor {BACKGROUND_DARK_FLOOR:.1f}",
                flush=True,
            )
            print(
                f"Processing bounding box y={keep_bounds[0]}:{keep_bounds[1]}, "
                f"x={keep_bounds[2]}:{keep_bounds[3]}",
                flush=True,
            )

            for out_index, src_index in enumerate(range(start_index, end_index + 1)):
                dst_frames[out_index] = process_frame(frames[src_index], keep_mask, average, keep_bounds)

                if (out_index + 1) % PROGRESS_EVERY_N_FRAMES == 0 or out_index + 1 == frame_count:
                    print(f"  {out_index + 1}/{frame_count} frames", flush=True)

            dst.flush()

    print(f"Saved processed recording to: {OUTPUT_H5_PATH}")


if __name__ == "__main__":
    trim_and_process_h5()
