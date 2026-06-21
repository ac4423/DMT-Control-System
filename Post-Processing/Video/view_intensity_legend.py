from pathlib import Path

import cv2
import h5py
import hdf5plugin  # noqa: F401 - registers compressed HDF5 filters
import numpy as np


IMAGE_PATH = Path(r"E:\RPV Test\camera_20260601_154017_frame_005850.png")
AVERAGE_H5_PATH = Path(r"E:\RPV Test\camera_20260601_154017_frames_5600_to_5900_roi_average.h5")
OVERLAY_IMAGE_PATH = Path(r"E:\RPV Test\RPV Data Display\RPV Image\RPV_Silouette.png")
WINDOW_NAME = "non-local means denoising"
DISPLAY_SCALE = 0.3
PANEL_SPACING = 8
HISTOGRAM_HEIGHT = 160
HISTOGRAM_WIDTH_SCALE = 0.92
DISPLAY_INTENSITY_MIN = 0
DISPLAY_INTENSITY_MAX = 255
NORMALIZED_INTENSITY_MIN = 30
NORMALIZED_INTENSITY_MAX = 90
NLM_H = 20
NLM_TEMPLATE_WINDOW_SIZE = 7
NLM_SEARCH_WINDOW_SIZE = 21
BACKGROUND_DARK_FLOOR = 20.0
ROI_CENTER_X = 505
ROI_CENTER_Y = 580
ROI_RADIUS = 440
ROI_ROTATION_DEG = -2
OVERLAY_ROTATION_DEG = ROI_ROTATION_DEG
GUIDE_CIRCLE_RADIUS = 380
ROI_OUTLINE_COLOR_BGR = (0, 0, 0)
ROI_OUTLINE_THICKNESS = 3
OUTSIDE_ROI_COLOR_BGR = (0, 0, 0)
SHOW_ROI_MASK = True
OVERLAY_X = 120
OVERLAY_Y = 235
OVERLAY_SCALE = 1.4
OVERLAY_ALPHA = 1


def display_intensity_image(
    image: np.ndarray,
    low: float = DISPLAY_INTENSITY_MIN,
    high: float = DISPLAY_INTENSITY_MAX,
) -> np.ndarray:
    low = float(low)
    high = float(high)
    if high <= low:
        high = low + 1.0

    # Window the image to [low, high], then stretch that window to the full
    # 0..255 range used by the colormap.
    clipped = np.clip(image.astype(np.float32), low, high)
    normalized = (clipped - low) / (high - low)
    return np.round(normalized * 255.0).astype(np.uint8)


def make_intensity_legend(
    height: int,
    width: int = 90,
    low: float = 0.0,
    high: float = 1.0,
    label: str = "Norm",
) -> np.ndarray:
    bar_width = 28
    tick_len = 8
    label_x = bar_width + tick_len + 8

    legend = np.full((height, width, 3), 255, dtype=np.uint8)

    gradient = np.linspace(255, 0, height, dtype=np.uint8).reshape(height, 1)
    gradient = np.repeat(gradient, bar_width, axis=1)
    color_bar = cv2.applyColorMap(gradient, cv2.COLORMAP_VIRIDIS)
    legend[:, :bar_width] = color_bar

    value_range = high - low
    if value_range <= 0:
        value_range = 1.0

    for value in np.linspace(low, high, 5):
        normalized = (float(value) - low) / value_range
        y = int(round((1.0 - normalized) * (height - 1)))
        value_text = f"{value:.2f}" if high <= 1.0 else f"{value:.0f}"
        cv2.line(legend, (bar_width, y), (bar_width + tick_len, y), (0, 0, 0), 1)
        cv2.putText(
            legend,
            value_text,
            (label_x, min(height - 4, max(12, y + 5))),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )

    cv2.putText(
        legend,
        label,
        (label_x, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 0),
        1,
        cv2.LINE_AA,
    )
    return legend


def draw_hover_text(display: np.ndarray, text: str) -> None:
    margin = 10
    origin = (margin, 28)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.7
    thickness = 2

    text_size, baseline = cv2.getTextSize(text, font, scale, thickness)
    box_w = text_size[0] + 2 * margin
    box_h = text_size[1] + baseline + 2 * margin

    cv2.rectangle(display, (0, 0), (box_w, box_h), (255, 255, 255), -1)
    cv2.rectangle(display, (0, 0), (box_w, box_h), (0, 0, 0), 1)
    cv2.putText(display, text, origin, font, scale, (0, 0, 0), thickness, cv2.LINE_AA)


def denoise_image(image: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoising(
        image,
        None,
        h=NLM_H,
        templateWindowSize=NLM_TEMPLATE_WINDOW_SIZE,
        searchWindowSize=NLM_SEARCH_WINDOW_SIZE,
    )


def load_average_image(expected_shape: tuple[int, int]) -> np.ndarray:
    if not AVERAGE_H5_PATH.exists():
        raise FileNotFoundError(f"Could not find average image H5: {AVERAGE_H5_PATH}")

    with h5py.File(AVERAGE_H5_PATH, "r") as h5:
        if "average" not in h5:
            raise KeyError(f"No /average dataset found in {AVERAGE_H5_PATH}")
        average = np.asarray(h5["average"][:], dtype=np.float32)

    if average.shape != expected_shape:
        raise ValueError(
            f"Average image shape {average.shape} does not match source image shape {expected_shape}."
        )

    return average


def weighted_background_subtract(
    image: np.ndarray,
    average: np.ndarray,
    mask: np.ndarray,
    dark_floor: float = BACKGROUND_DARK_FLOOR,
) -> np.ndarray:
    corrected = np.zeros(image.shape, dtype=np.float32)
    valid_pixels = mask > 0

    image_float = image.astype(np.float32)
    average_float = average.astype(np.float32)
    correction_strength = np.clip((image_float - dark_floor) / (255.0 - dark_floor), 0.0, 1.0)
    background_above_floor = np.maximum(average_float - dark_floor, 0.0)

    corrected[valid_pixels] = image_float[valid_pixels] - (
        correction_strength[valid_pixels] * background_above_floor[valid_pixels]
    )
    corrected[valid_pixels] = np.clip(corrected[valid_pixels], 0.0, 255.0)
    return corrected


def masked_min_max(image: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    values = image[mask > 0]
    if values.size == 0:
        return 0.0, 0.0
    return float(values.min()), float(values.max())


def display_panel_image(
    image: np.ndarray,
    low: float = DISPLAY_INTENSITY_MIN,
    high: float = DISPLAY_INTENSITY_MAX,
) -> np.ndarray:
    return display_intensity_image(image, low, high)


def make_roi_mask(shape: tuple[int, int], scale: float = 1.0) -> np.ndarray:
    height, width = shape
    center = (
        int(round(ROI_CENTER_X * scale)),
        int(round(ROI_CENTER_Y * scale)),
    )
    radius = int(round(ROI_RADIUS * scale))

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

    return rotate_overlay_image(overlay, OVERLAY_ROTATION_DEG)


def make_overlay_mask(shape: tuple[int, int], overlay: np.ndarray | None) -> np.ndarray:
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)
    if overlay is None:
        return mask

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
    mask[clip_y0:clip_y1, clip_x0:clip_x1] = (alpha_crop > 0).astype(np.uint8) * 255
    return mask


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


def add_panel_label(image: np.ndarray, label: str) -> np.ndarray:
    labelled = image.copy()
    margin = 8
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1
    text_size, baseline = cv2.getTextSize(label, font, scale, thickness)
    box_w = text_size[0] + 2 * margin
    box_h = text_size[1] + baseline + 2 * margin

    cv2.rectangle(labelled, (0, 0), (box_w, box_h), (255, 255, 255), -1)
    cv2.rectangle(labelled, (0, 0), (box_w, box_h), (0, 0, 0), 1)
    cv2.putText(labelled, label, (margin, box_h - margin - baseline), font, scale, (0, 0, 0), thickness, cv2.LINE_AA)
    return labelled


def make_histogram_panel(
    image: np.ndarray,
    mask: np.ndarray,
    width: int,
    height: int,
    label: str,
    low: float,
    high: float,
) -> np.ndarray:
    pixels = image[mask > 0]
    if high <= low:
        high = low + 1.0
    normalized_pixels = np.clip((pixels.astype(np.float32) - low) / (high - low), 0.0, 1.0)
    histogram_pixels = np.round(normalized_pixels * 255.0).astype(np.uint8)
    p5 = float(np.percentile(normalized_pixels, 5)) if normalized_pixels.size else 0.0
    p95 = float(np.percentile(normalized_pixels, 95)) if normalized_pixels.size else 0.0
    hist = np.bincount(histogram_pixels, minlength=256).astype(np.float64)
    if hist.max() > 0:
        hist = hist / hist.max()

    panel = np.full((height, width, 3), 255, dtype=np.uint8)
    plot_margin_left = 34
    plot_margin_right = 8
    plot_margin_top = 24
    plot_margin_bottom = 24
    plot_x0 = plot_margin_left
    plot_y0 = plot_margin_top
    plot_x1 = width - plot_margin_right
    plot_y1 = height - plot_margin_bottom
    plot_w = max(1, plot_x1 - plot_x0)
    plot_h = max(1, plot_y1 - plot_y0)

    cv2.rectangle(panel, (plot_x0, plot_y0), (plot_x1, plot_y1), (0, 0, 0), 1)

    for value in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = plot_y1 - int(round(value * (plot_h - 1)))
        cv2.line(panel, (plot_x0, y), (plot_x1, y), (225, 225, 225), 1)
        cv2.line(panel, (plot_x0 - 5, y), (plot_x0, y), (0, 0, 0), 1)
        cv2.putText(
            panel,
            f"{value:.2g}",
            (4, min(height - 4, y + 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.3,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )

    for intensity, value in enumerate(hist):
        x = plot_x0 + int(round((intensity / 255) * (plot_w - 1)))
        bar_h = int(round(value * (plot_h - 1)))
        cv2.line(panel, (x, plot_y1), (x, plot_y1 - bar_h), (45, 45, 45), 1)

    p5_x = plot_x0 + int(round(p5 * (plot_w - 1)))
    p5_color = (255, 180, 80)
    cv2.line(panel, (p5_x, plot_y0), (p5_x, plot_y1), p5_color, 2)
    cv2.putText(
        panel,
        f"P5 {p5:.2f}",
        (max(plot_x0, min(plot_x1 - 46, p5_x + 4)), plot_y0 + plot_h // 3),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.34,
        p5_color,
        1,
        cv2.LINE_AA,
    )

    p95_x = plot_x0 + int(round(p95 * (plot_w - 1)))
    cv2.line(panel, (p95_x, plot_y0), (p95_x, plot_y1), (0, 0, 220), 2)
    cv2.putText(
        panel,
        f"P95 {p95:.2f}",
        (max(plot_x0, min(plot_x1 - 54, p95_x + 4)), plot_y0 + (2 * plot_h) // 3),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.34,
        (0, 0, 220),
        1,
        cv2.LINE_AA,
    )

    for normalized in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = plot_x0 + int(round(normalized * (plot_w - 1)))
        cv2.line(panel, (x, plot_y1), (x, plot_y1 + 5), (0, 0, 0), 1)
        cv2.putText(
            panel,
            f"{normalized:.2g}",
            (max(0, x - 10), min(height - 4, plot_y1 + 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )

    title_font = cv2.FONT_HERSHEY_SIMPLEX
    title_scale = 0.45
    title_thickness = 1
    title_size, _ = cv2.getTextSize(label, title_font, title_scale, title_thickness)
    title_x = max(0, (width - title_size[0]) // 2)
    cv2.putText(panel, label, (title_x, 16), title_font, title_scale, (0, 0, 0), title_thickness, cv2.LINE_AA)
    cv2.putText(panel, "", (8, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 0, 0), 1, cv2.LINE_AA)
    return panel


def main() -> None:
    image = cv2.imread(str(IMAGE_PATH), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {IMAGE_PATH}")

    denoised = denoise_image(image)
    source_roi_mask = make_roi_mask(image.shape, scale=1.0)
    overlay_image = load_overlay_image()
    overlay_mask = make_overlay_mask(image.shape, overlay_image)
    source_valid_mask = np.where((source_roi_mask > 0) & (overlay_mask == 0), 255, 0).astype(np.uint8)
    average = load_average_image(image.shape)
    corrected = weighted_background_subtract(denoised, average, source_valid_mask)
    corrected_min, corrected_max = masked_min_max(corrected, source_valid_mask)
    print(
        f"Weighted background-subtracted ROI range: {corrected_min:.3f}..{corrected_max:.3f} "
        f"(dark floor {BACKGROUND_DARK_FLOOR:.1f})"
    )

    display_h = max(1, int(round(image.shape[0] * DISPLAY_SCALE)))
    display_w = max(1, int(round(image.shape[1] * DISPLAY_SCALE)))
    display_roi_mask = make_roi_mask((display_h, display_w), scale=DISPLAY_SCALE)
    display_roi_center = (
        int(round(ROI_CENTER_X * DISPLAY_SCALE)),
        int(round(ROI_CENTER_Y * DISPLAY_SCALE)),
    )
    display_roi_radius = int(round(ROI_RADIUS * DISPLAY_SCALE))
    display_guide_circle_radius = int(round(GUIDE_CIRCLE_RADIUS * DISPLAY_SCALE))

    panels = [
        ("Raw", image, DISPLAY_INTENSITY_MIN, DISPLAY_INTENSITY_MAX, 0, 0),
        ("NLM", denoised, DISPLAY_INTENSITY_MIN, DISPLAY_INTENSITY_MAX, display_w + PANEL_SPACING, 0),
        (
            "Baseline Correction",
            corrected,
            DISPLAY_INTENSITY_MIN,
            DISPLAY_INTENSITY_MAX,
            2 * (display_w + PANEL_SPACING),
            0,
        ),
        (
            "Renormalized",
            corrected,
            NORMALIZED_INTENSITY_MIN,
            NORMALIZED_INTENSITY_MAX,
            3 * (display_w + PANEL_SPACING),
            0,
        ),
    ]

    grid_h = display_h + PANEL_SPACING + HISTOGRAM_HEIGHT
    grid_w = 4 * display_w + 3 * PANEL_SPACING
    grid = np.full((grid_h, grid_w, 3), 255, dtype=np.uint8)

    for label, panel_image, display_low, display_high, x0, y0 in panels:
        panel_display = cv2.resize(
            display_panel_image(panel_image, display_low, display_high),
            (display_w, display_h),
            interpolation=cv2.INTER_AREA,
        )
        panel_color = cv2.applyColorMap(panel_display, cv2.COLORMAP_VIRIDIS)
        if SHOW_ROI_MASK:
            panel_color[display_roi_mask == 0] = OUTSIDE_ROI_COLOR_BGR
        cv2.circle(
            panel_color,
            display_roi_center,
            display_roi_radius,
            ROI_OUTLINE_COLOR_BGR,
            ROI_OUTLINE_THICKNESS,
            cv2.LINE_AA,
        )
        cv2.circle(
            panel_color,
            display_roi_center,
            display_guide_circle_radius,
            ROI_OUTLINE_COLOR_BGR,
            ROI_OUTLINE_THICKNESS,
            cv2.LINE_AA,
        )
        panel_color = apply_overlay(panel_color, overlay_image, DISPLAY_SCALE)
        panel_color = add_panel_label(panel_color, label)
        grid[y0:y0 + display_h, x0:x0 + display_w] = panel_color

        hist_y = display_h + PANEL_SPACING
        hist_w = max(1, int(round(display_w * HISTOGRAM_WIDTH_SCALE)))
        hist_x = x0 + (display_w - hist_w) // 2
        hist_panel = make_histogram_panel(
            panel_image,
            source_valid_mask,
            hist_w,
            HISTOGRAM_HEIGHT,
            f"{label} histogram",
            display_low,
            display_high,
        )
        grid[hist_y:hist_y + HISTOGRAM_HEIGHT, hist_x:hist_x + hist_w] = hist_panel

    legend = make_intensity_legend(grid_h)
    base_display = np.hstack((grid, legend))

    state = {
        "display": base_display.copy(),
        "last_text": "",
    }

    def redraw(text: str = "") -> None:
        display = base_display.copy()
        if text:
            draw_hover_text(display, text)
        state["display"] = display
        state["last_text"] = text
        cv2.imshow(WINDOW_NAME, display)

    def on_mouse(event: int, x: int, y: int, flags: int, userdata) -> None:
        if event != cv2.EVENT_MOUSEMOVE:
            return

        text = ""
        for label, panel_image, _display_low, _display_high, x0, y0 in panels:
            if x0 <= x < x0 + display_w and y0 <= y < y0 + display_h:
                panel_x = x - x0
                panel_y = y - y0
                src_x = min(panel_image.shape[1] - 1, int(panel_x / DISPLAY_SCALE))
                src_y = min(panel_image.shape[0] - 1, int(panel_y / DISPLAY_SCALE))
                if source_valid_mask[src_y, src_x]:
                    intensity = float(panel_image[src_y, src_x])
                    if np.issubdtype(panel_image.dtype, np.floating):
                        text = f"{label} ({src_x}, {src_y}, {intensity:.4f})"
                    else:
                        text = f"{label} ({src_x}, {src_y}, {int(intensity)})"
                break

        if text != state["last_text"]:
            redraw(text)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW_NAME, on_mouse)
    redraw()
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
