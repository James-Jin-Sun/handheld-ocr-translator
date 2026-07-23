import time
from functools import lru_cache

try:
    import numpy as np
except ImportError as exc:
    raise SystemExit("Missing dependency: install numpy with `pip install numpy`.") from exc

try:
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Missing dependency: install Pillow with `pip install pillow`.") from exc

try:
    import paddle
    from paddleocr import PaddleOCR, TextDetection, TextRecognition
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install paddleocr and paddlepaddle with "
        "`pip install paddleocr paddlepaddle`."
    ) from exc

from metrics import detection_prf, match_boxes_by_iou, normalize_text, polygon_to_bbox
from ocr import crop_text_region


@lru_cache(maxsize=1)
def _cuda_available():
    """Whether this paddlepaddle build has a working CUDA device.

    Some Jetson paddlepaddle-gpu builds crash (native SIGSEGV, no Python
    traceback) when forced onto their CPU inference path, so GPU should be
    used automatically whenever it's available rather than only when a
    caller happens to pass `--paddleocr-gpu`.
    """
    try:
        return bool(paddle.device.is_compiled_with_cuda()) and paddle.device.cuda.device_count() > 0
    except Exception:
        return False


def _device_for(config):
    if config.paddleocr_gpu:
        return "gpu"
    return "gpu" if _cuda_available() else "cpu"


@lru_cache(maxsize=4)
def get_paddle_pipeline(lang, device):
    return PaddleOCR(
        lang=lang,
        device=device,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


@lru_cache(maxsize=2)
def get_text_detector(device):
    return TextDetection(device=device)


@lru_cache(maxsize=2)
def get_text_recognizer(device):
    return TextRecognition(device=device)


def pipeline_for(config):
    return get_paddle_pipeline(config.paddleocr_lang, _device_for(config))


def detector_for(config):
    return get_text_detector(_device_for(config))


def recognizer_for(config):
    return get_text_recognizer(_device_for(config))


def extract_result_payload(res):
    """PaddleOCR/PaddleX result objects expose a `.json` dict that is either
    the flat result dict, or wrapped as {"res": {...}}. Handle both."""
    data = getattr(res, "json", res)
    if isinstance(data, dict) and isinstance(data.get("res"), dict):
        return data["res"]
    return data


def ocr_paddleocr_simple(image_path, config):
    pipeline = pipeline_for(config)
    start_time = time.perf_counter()
    results = list(pipeline.predict(str(image_path)))
    runtime = time.perf_counter() - start_time

    region_rows = []
    texts = []
    for res in results:
        data = extract_result_payload(res)
        rec_texts = data.get("rec_texts", []) or []
        rec_scores = data.get("rec_scores", []) or []
        rec_polys = data.get("rec_polys", []) or []

        for region_index, (text, score, poly) in enumerate(
            zip(rec_texts, rec_scores, rec_polys), start=1
        ):
            clean_text = normalize_text(str(text))
            texts.append(clean_text)
            region_rows.append(
                {
                    "image": image_path.name,
                    "region_index": region_index,
                    "bbox": list(polygon_to_bbox(poly)),
                    "text": clean_text,
                    "confidence": float(score),
                }
            )

    prediction = normalize_text(" ".join(texts))
    return prediction, runtime, region_rows


def ocr_paddleocr_detection(image_path, records, config):
    """Run PaddleOCR's own text detector first, score it against the GT
    boxes, then recognize text for each detected box (batched) for a
    comparable OCR result."""
    detector = detector_for(config)
    start_time = time.perf_counter()

    detection_results = list(detector.predict(str(image_path), batch_size=1))
    predicted_boxes = []
    for res in detection_results:
        data = extract_result_payload(res)
        for poly in data.get("dt_polys", []) or []:
            predicted_boxes.append(polygon_to_bbox(poly))

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

    crop_dir = config.output_dir / "detections" / image_path.stem
    crop_dir.mkdir(parents=True, exist_ok=True)

    crop_arrays = []
    crop_paths = []
    with Image.open(image_path) as pil_image:
        pil_image = pil_image.convert("RGB")

        for crop_index, box in enumerate(predicted_boxes, start=1):
            crop = crop_text_region(pil_image, box, config.crop_padding)
            if crop is None:
                crop_arrays.append(None)
                crop_paths.append("")
                continue

            crop_path = crop_dir / f"{crop_index:03d}.png"
            crop.save(crop_path)
            crop_arrays.append(np.array(crop))
            crop_paths.append(str(crop_path))

    # Recognize all detected boxes in one batched pass instead of re-running
    # detection+recognition per crop (much faster than a per-crop pipeline call).
    recognizer = recognizer_for(config)
    valid_arrays = [crop for crop in crop_arrays if crop is not None]
    recognized_texts = [""] * len(crop_arrays)
    recognized_scores = [0.0] * len(crop_arrays)

    if valid_arrays:
        recognition_results = list(
            recognizer.predict(input=valid_arrays, batch_size=len(valid_arrays))
        )
        valid_index = 0
        for slot_index, crop in enumerate(crop_arrays):
            if crop is None:
                continue
            data = extract_result_payload(recognition_results[valid_index])
            recognized_texts[slot_index] = normalize_text(str(data.get("rec_text", "")))
            recognized_scores[slot_index] = float(data.get("rec_score", 0.0) or 0.0)
            valid_index += 1

    predictions = []
    crop_rows = []
    for crop_index, box in enumerate(predicted_boxes, start=1):
        slot_index = crop_index - 1
        text = recognized_texts[slot_index]
        predictions.append(text)
        crop_rows.append(
            {
                "image": image_path.name,
                "crop_index": crop_index,
                "bbox": list(box),
                "prediction": text,
                "confidence": recognized_scores[slot_index],
                "crop_file": crop_paths[slot_index],
            }
        )

    runtime = time.perf_counter() - start_time
    prediction = normalize_text(" ".join(predictions))
    return prediction, runtime, crop_rows, detection_metrics
