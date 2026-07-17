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


def blur_and_overlay(image, regions, blur_radius=DEFAULT_BLUR_RADIUS):
    """Blur each region's source text and draw its translated text on top.

    `regions` is a list of dicts: {"bbox": (x1, y1, x2, y2), "translated_text": str}.
    """
    image = image.convert("RGB")
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
