import time
from functools import lru_cache

try:
    import numpy as np
except ImportError as exc:
    raise SystemExit("Missing dependency: install numpy with `pip install numpy`.") from exc

try:
    import cv2
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install opencv with `pip install opencv-python-headless`."
    ) from exc

try:
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Missing dependency: install Pillow with `pip install pillow`.") from exc

try:
    import easyocr
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install easyocr with `pip install easyocr`."
    ) from exc

from metrics import detection_prf, match_boxes_by_iou, normalize_text
from ocr import crop_text_region


@lru_cache(maxsize=4)
def get_reader(languages, gpu):
    return easyocr.Reader(list(languages), gpu=gpu, verbose=False)


def reader_for(config):
    return get_reader(tuple(config.easyocr_languages), config.easyocr_gpu)


def load_image_array(image_path):
    with Image.open(image_path) as image:
        return np.array(image.convert("RGB"))


def polygon_to_bbox(polygon):
    x_values = [point[0] for point in polygon]
    y_values = [point[1] for point in polygon]
    return (
        int(min(x_values)),
        int(min(y_values)),
        int(max(x_values)),
        int(max(y_values)),
    )


_NUMERIC_TYPES = (int, float, np.integer, np.floating)


def _is_numeric(value):
    return isinstance(value, _NUMERIC_TYPES)


def _is_sequence(value):
    return isinstance(value, (list, tuple, np.ndarray))


def _is_horizontal_box(candidate):
    return (
        _is_sequence(candidate)
        and len(candidate) == 4
        and all(_is_numeric(value) for value in candidate)
    )


def _is_polygon_box(candidate):
    return (
        _is_sequence(candidate)
        and len(candidate) >= 3
        and all(
            _is_sequence(point) and len(point) == 2 and all(_is_numeric(v) for v in point)
            for point in candidate
        )
    )


def _flatten_boxes(group, is_box_fn):
    """EasyOCR's detect() sometimes wraps boxes in an extra per-image list
    layer depending on version/batch mode. Recurse until real boxes are found."""
    if group is None or not _is_sequence(group) or len(group) == 0:
        return []
    if is_box_fn(group):
        return [group]

    flattened = []
    for item in group:
        flattened.extend(_flatten_boxes(item, is_box_fn))
    return flattened


def flatten_easyocr_boxes(horizontal_list, free_list):
    boxes = []
    for box in _flatten_boxes(horizontal_list, _is_horizontal_box):
        x_min, x_max, y_min, y_max = box
        boxes.append((int(x_min), int(y_min), int(x_max), int(y_max)))

    for polygon in _flatten_boxes(free_list, _is_polygon_box):
        boxes.append(polygon_to_bbox(polygon))

    return boxes


def ocr_easyocr_simple(image_path, config):
    reader = reader_for(config)
    start_time = time.perf_counter()
    image_array = load_image_array(image_path)
    results = reader.readtext(image_array, detail=1, paragraph=False)
    runtime = time.perf_counter() - start_time

    region_rows = []
    texts = []
    for region_index, (box, text, confidence) in enumerate(results, start=1):
        clean_text = normalize_text(text)
        texts.append(clean_text)
        region_rows.append(
            {
                "image": image_path.name,
                "region_index": region_index,
                "bbox": polygon_to_bbox(box),
                "text": clean_text,
                "confidence": float(confidence),
            }
        )

    prediction = normalize_text(" ".join(texts))
    return prediction, runtime, region_rows


def ocr_easyocr_paragraph(image_path, config):
    reader = reader_for(config)
    start_time = time.perf_counter()
    image_array = load_image_array(image_path)
    results = reader.readtext(image_array, detail=1, paragraph=True)
    runtime = time.perf_counter() - start_time

    region_rows = []
    texts = []
    for region_index, item in enumerate(results, start=1):
        box, text = item[0], item[1]
        clean_text = normalize_text(text)
        texts.append(clean_text)
        region_rows.append(
            {
                "image": image_path.name,
                "region_index": region_index,
                "bbox": polygon_to_bbox(box),
                "text": clean_text,
                "confidence": "",
            }
        )

    prediction = normalize_text(" ".join(texts))
    return prediction, runtime, region_rows


def ocr_easyocr_detection(image_path, records, config):
    """Run EasyOCR's text detector first, score it against the GT boxes,
    then recognize text for each detected box (batched) for a comparable
    OCR result."""
    reader = reader_for(config)
    start_time = time.perf_counter()
    image_array = load_image_array(image_path)

    horizontal_list, free_list = reader.detect(image_array)
    # detect() wraps results in one list per input image; we only pass one image.
    horizontal_boxes = horizontal_list[0] if horizontal_list else []
    free_boxes = free_list[0] if free_list else []
    predicted_boxes = flatten_easyocr_boxes(horizontal_list, free_list)

    gt_boxes = [record["bbox"] for record in records]
    match_result = match_boxes_by_iou(
        gt_boxes,
        predicted_boxes,
        config.detection_iou_threshold,
    )
    precision, recall, f1 = detection_prf(
        match_result["true_positive"],
        match_result["false_positive"],
        match_result["false_negative"],
    )

    detection_metrics = {
        "image": image_path.name,
        "gt_box_count": len(gt_boxes),
        "predicted_box_count": len(predicted_boxes),
        "true_positive": match_result["true_positive"],
        "false_positive": match_result["false_positive"],
        "false_negative": match_result["false_negative"],
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mean_iou": match_result["mean_iou"],
        "iou_threshold": config.detection_iou_threshold,
    }

    # Recognize all detected boxes in one batched pass instead of re-running
    # detection+recognition per crop (much faster than per-crop readtext()).
    gray_image = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
    recognized = reader.recognize(
        gray_image,
        horizontal_list=horizontal_boxes,
        free_list=free_boxes,
    )

    predictions = []
    crop_rows = []
    crop_dir = config.output_dir / "detections" / image_path.stem
    crop_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as pil_image:
        pil_image = pil_image.convert("RGB")

        for crop_index, (box, text, confidence) in enumerate(recognized, start=1):
            bbox = polygon_to_bbox(box)
            clean_text = normalize_text(text)
            predictions.append(clean_text)

            crop = crop_text_region(pil_image, bbox, config.crop_padding)
            crop_path = ""
            if crop is not None:
                crop_path = crop_dir / f"{crop_index:03d}.png"
                crop.save(crop_path)

            crop_rows.append(
                {
                    "image": image_path.name,
                    "crop_index": crop_index,
                    "bbox": list(bbox),
                    "prediction": clean_text,
                    "confidence": float(confidence),
                    "crop_file": str(crop_path),
                }
            )

    runtime = time.perf_counter() - start_time
    prediction = normalize_text(" ".join(predictions))
    return prediction, runtime, crop_rows, detection_metrics
