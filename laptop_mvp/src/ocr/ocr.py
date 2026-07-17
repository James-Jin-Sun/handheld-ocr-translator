import time

try:
    from PIL import Image, ImageOps
except ImportError as exc:
    raise SystemExit("Missing dependency: install Pillow with `pip install pillow`.") from exc

try:
    import pytesseract
    from pytesseract import Output
except ImportError as exc:
    raise SystemExit("Missing dependency: install pytesseract with `pip install pytesseract`.") from exc

from metrics import normalize_text


def configure_tesseract(tesseract_cmd):
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)


def ocr_whole_image(image_path, tesseract_config):
    start_time = time.perf_counter()
    with Image.open(image_path) as image:
        prediction = pytesseract.image_to_string(image, config=tesseract_config)
    runtime = time.perf_counter() - start_time
    return normalize_text(prediction), runtime


def parse_confidence(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def ocr_psm11_confidence(image_path, config):
    start_time = time.perf_counter()
    token_rows = []
    kept_tokens = []

    with Image.open(image_path) as image:
        data = pytesseract.image_to_data(
            image,
            config=config.confidence_tesseract_config,
            output_type=Output.DICT,
        )

    item_count = len(data.get("text", []))
    for index in range(item_count):
        text = normalize_text(data["text"][index])
        confidence = parse_confidence(data["conf"][index])
        is_kept = bool(text) and confidence >= config.confidence_threshold

        if is_kept:
            kept_tokens.append(text)

        token_rows.append(
            {
                "image": image_path.name,
                "token_index": index + 1,
                "text": text,
                "confidence": confidence,
                "kept": is_kept,
                "left": data["left"][index],
                "top": data["top"][index],
                "width": data["width"][index],
                "height": data["height"][index],
                "level": data["level"][index],
                "page_num": data["page_num"][index],
                "block_num": data["block_num"][index],
                "par_num": data["par_num"][index],
                "line_num": data["line_num"][index],
                "word_num": data["word_num"][index],
            }
        )

    runtime = time.perf_counter() - start_time
    return normalize_text(" ".join(kept_tokens)), runtime, token_rows


def resample_filter():
    if hasattr(Image, "Resampling"):
        return Image.Resampling.LANCZOS
    return Image.LANCZOS


def crop_text_region(image, bbox, padding):
    width, height = image.size
    x1, y1, x2, y2 = bbox
    left = max(0, min(x1, x2) - padding)
    top = max(0, min(y1, y2) - padding)
    right = min(width, max(x1, x2) + padding)
    bottom = min(height, max(y1, y2) + padding)

    if right <= left or bottom <= top:
        return None

    return image.crop((left, top, right, bottom))


def resize_crop(crop, scale, min_height):
    if crop.height <= 0:
        return crop

    resize_factor = max(scale, min_height / crop.height)
    if resize_factor <= 1:
        return crop

    new_size = (
        max(1, int(round(crop.width * resize_factor))),
        max(1, int(round(crop.height * resize_factor))),
    )
    return crop.resize(new_size, resample_filter())


def add_crop_border(crop, border_pixels, border_color):
    if border_pixels <= 0:
        return crop
    return ImageOps.expand(crop, border=border_pixels, fill=border_color)


def ocr_gt_crops(image_path, records, config, with_border=False):
    start_time = time.perf_counter()
    predictions = []
    crop_rows = []
    crop_dir = config.output_dir / "crops" / image_path.stem
    crop_dir.mkdir(parents=True, exist_ok=True)
    tesseract_config = (
        config.crop_border_tesseract_config
        if with_border
        else config.crop_tesseract_config
    )

    with Image.open(image_path) as image:
        image = image.convert("RGB")

        for crop_index, record in enumerate(records, start=1):
            crop = crop_text_region(image, record["bbox"], config.crop_padding)
            if crop is None:
                prediction = ""
                crop_path = ""
            else:
                crop = resize_crop(crop, config.crop_scale, config.min_crop_height)
                if with_border:
                    crop = add_crop_border(
                        crop,
                        config.crop_border_pixels,
                        config.crop_border_color,
                    )
                crop_path = crop_dir / f"{crop_index:03d}.png"
                crop.save(crop_path)
                prediction = pytesseract.image_to_string(
                    crop,
                    config=tesseract_config,
                )

            prediction = normalize_text(prediction)
            predictions.append(prediction)
            crop_rows.append(
                {
                    "image": image_path.name,
                    "crop_index": crop_index,
                    "bbox": list(record["bbox"]),
                    "ground_truth": record["text"],
                    "prediction": prediction,
                    "crop_file": str(crop_path),
                    "with_border": with_border,
                    "border_pixels": config.crop_border_pixels if with_border else 0,
                    "tesseract_config": tesseract_config,
                }
            )

    runtime = time.perf_counter() - start_time
    return normalize_text(" ".join(predictions)), runtime, crop_rows
