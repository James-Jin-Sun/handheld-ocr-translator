"""Blur detected source-text regions and draw translated text on top."""

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError as exc:
    raise SystemExit("Missing dependency: install Pillow with `pip install pillow`.") from exc


DEFAULT_BLUR_RADIUS = 8
DEFAULT_TEXT_COLOR = (255, 255, 255)
DEFAULT_BACKDROP_COLOR = (0, 0, 0, 160)


def blur_region(image, bbox, radius=DEFAULT_BLUR_RADIUS):
    """Blur the given (x1, y1, x2, y2) region of `image` in place and return it."""
    x1, y1, x2, y2 = (int(value) for value in bbox)
    region = image.crop((x1, y1, x2, y2))
    region = region.filter(ImageFilter.GaussianBlur(radius))
    image.paste(region, (x1, y1))
    return image


# Microsoft YaHei / SimHei render both Latin and CJK glyphs (needed for
# Chinese translations); Arial is a Latin-only fallback.
_FONT_CANDIDATES = ("msyh.ttc", "simhei.ttf", "arial.ttf")


def _load_font(size):
    for font_name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_text_over_region(
    image,
    bbox,
    text,
    text_color=DEFAULT_TEXT_COLOR,
    backdrop_color=DEFAULT_BACKDROP_COLOR,
):
    """Draw a semi-opaque backdrop plus `text`, shrunk to fit and centered on `bbox`."""
    if not text:
        return image

    x1, y1, x2, y2 = (int(value) for value in bbox)
    width, height = max(1, x2 - x1), max(1, y2 - y1)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((x1, y1, x2, y2), fill=backdrop_color)

    font_size = max(10, int(height * 0.7))
    font = _load_font(font_size)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    while text_width > width and font_size > 8:
        font_size -= 2
        font = _load_font(font_size)
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

    text_x = x1 + max(0, (width - text_width) // 2)
    text_y = y1 + max(0, (height - text_height) // 2)
    draw.text((text_x, text_y), text, font=font, fill=text_color)

    image = image.convert("RGBA")
    image.alpha_composite(overlay)
    return image.convert("RGB")


def split_text_across_lines(text, weights):
    """Split `text` into `len(weights)` segments whose lengths are roughly
    proportional to `weights` (e.g. the original lines' text lengths), so a
    block-level translation can be laid back out over the original lines.

    When the text contains spaces (word-based target languages) the cut
    points snap to the nearest space; otherwise (e.g. Chinese) they fall at
    character boundaries.
    """
    if not weights:
        return []
    if len(weights) == 1:
        return [text]

    total_weight = sum(weights)
    if total_weight <= 0:
        weights = [1] * len(weights)
        total_weight = len(weights)

    text_length = len(text)
    cut_points = []
    cumulative = 0
    for weight in weights[:-1]:
        cumulative += weight
        cut_points.append(round(text_length * cumulative / total_weight))

    if " " in text:
        snapped = []
        for cut in cut_points:
            space_before = text.rfind(" ", 0, cut + 1)
            space_after = text.find(" ", cut)
            candidates = [pos for pos in (space_before, space_after) if pos != -1]
            if candidates:
                cut = min(candidates, key=lambda pos: abs(pos - cut))
            snapped.append(cut)
        cut_points = snapped

    segments = []
    previous = 0
    for cut in cut_points:
        cut = max(previous, min(cut, text_length))
        segments.append(text[previous:cut].strip())
        previous = cut
    segments.append(text[previous:].strip())
    return segments


def _overlap_extent(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    overlap_x = min(ax2, bx2) - max(ax1, bx1)
    overlap_y = min(ay2, by2) - max(ay1, by1)
    return overlap_x, overlap_y


def _separate_pair(box_a, box_b, min_size=4):
    """If `box_a` and `box_b` overlap, shrink both along whichever axis has
    the smaller overlap so they touch but no longer overlap, splitting the
    shared boundary down the middle."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    overlap_x, overlap_y = _overlap_extent(box_a, box_b)

    if overlap_x <= 0 or overlap_y <= 0:
        return box_a, box_b

    if overlap_x <= overlap_y:
        if (ax1 + ax2) <= (bx1 + bx2):
            midpoint = (ax2 + bx1) / 2
            ax2 = max(ax1 + min_size, midpoint)
            bx1 = min(bx2 - min_size, midpoint)
        else:
            midpoint = (bx2 + ax1) / 2
            bx2 = max(bx1 + min_size, midpoint)
            ax1 = min(ax2 - min_size, midpoint)
    else:
        if (ay1 + ay2) <= (by1 + by2):
            midpoint = (ay2 + by1) / 2
            ay2 = max(ay1 + min_size, midpoint)
            by1 = min(by2 - min_size, midpoint)
        else:
            midpoint = (by2 + ay1) / 2
            by2 = max(by1 + min_size, midpoint)
            ay1 = min(ay2 - min_size, midpoint)

    return (ax1, ay1, ax2, ay2), (bx1, by1, bx2, by2)


def resolve_overlapping_boxes(regions, max_iterations=5):
    """Nudge overlapping backdrop boxes apart so rendered regions don't
    collide (e.g. adjacent OCR line boxes that overlap by a few pixels).

    Runs a few passes over every pair since separating one pair can (rarely)
    introduce a new overlap with a third box in dense layouts.

    `regions` is a list of dicts with a "bbox" key: (x1, y1, x2, y2).
    Returns a new list of dicts (inputs are not mutated) with adjusted boxes.
    """
    boxes = [list(region["bbox"]) for region in regions]

    for _ in range(max_iterations):
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                overlap_x, overlap_y = _overlap_extent(boxes[i], boxes[j])
                if overlap_x > 0 and overlap_y > 0:
                    boxes[i], boxes[j] = _separate_pair(boxes[i], boxes[j])
                    changed = True
        if not changed:
            break

    return [{**region, "bbox": tuple(boxes[index])} for index, region in enumerate(regions)]


def blur_and_overlay(image, regions, blur_radius=DEFAULT_BLUR_RADIUS):
    """Blur each region's source text and draw its translated text on top.

    `regions` is a list of dicts: {"bbox": (x1, y1, x2, y2), "translated_text": str}.
    Overlapping boxes are nudged apart first so backdrops/text don't collide.
    """
    image = image.convert("RGB")
    regions = resolve_overlapping_boxes(regions)
    for region in regions:
        image = blur_region(image, region["bbox"], blur_radius)
        image = draw_text_over_region(image, region["bbox"], region.get("translated_text", ""))
    return image


def save_translated_image(image_path, regions, output_path, blur_radius=DEFAULT_BLUR_RADIUS):
    with Image.open(image_path) as image:
        result = blur_and_overlay(image, regions, blur_radius)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path)
    return output_path
