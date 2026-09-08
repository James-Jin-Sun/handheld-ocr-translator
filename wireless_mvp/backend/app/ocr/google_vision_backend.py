"""Wrapper around the Google Cloud Vision API for OCR.

Uses Application Default Credentials (ADC), same as `google_translate.py` --
no API key or service-account JSON file needed. Enable the Vision API once on
the same GCP project used for translation:

    gcloud services enable vision.googleapis.com --project=handheld-ocr-translator
    gcloud auth application-default login
"""

import time
from functools import lru_cache
from pathlib import Path

try:
    from google.cloud import vision
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install it with `pip install google-cloud-vision`."
    ) from exc

from metrics import normalize_text


@lru_cache(maxsize=1)
def get_client():
    return vision.ImageAnnotatorClient()


def _paragraph_region(paragraph, image_name, region_index):
    """Vision API has no native "line" concept -- a paragraph (one or more
    stacked lines of body text) is the closest match to PaddleOCR's
    per-line regions, so each paragraph becomes one region here."""
    words = []
    confidences = []
    x_values = []
    y_values = []
    for word in paragraph.words:
        words.append("".join(symbol.text for symbol in word.symbols))
        confidences.append(word.confidence)
        for vertex in word.bounding_box.vertices:
            x_values.append(vertex.x)
            y_values.append(vertex.y)

    text = normalize_text(" ".join(words))
    if not text:
        return None

    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return {
        "image": image_name,
        "region_index": region_index,
        "bbox": [min(x_values), min(y_values), max(x_values), max(y_values)],
        "text": text,
        "confidence": float(confidence),
    }


def ocr_google_vision_simple(image_path, language_hints=None):
    """Run Google Cloud Vision's document text detection, returning one
    region per detected paragraph (bbox, text, confidence). Mirrors
    `ocr_paddleocr_simple`'s `(prediction, runtime, region_rows)` return
    shape so it's a drop-in replacement in the pipeline."""
    client = get_client()
    content = Path(image_path).read_bytes()
    image = vision.Image(content=content)
    image_context = vision.ImageContext(language_hints=language_hints) if language_hints else None

    start_time = time.perf_counter()
    response = client.document_text_detection(image=image, image_context=image_context)
    runtime = time.perf_counter() - start_time

    if response.error.message:
        raise RuntimeError(f"Google Vision API error: {response.error.message}")

    region_rows = []
    texts = []
    region_index = 0
    for page in response.full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                region_index += 1
                region = _paragraph_region(paragraph, image_path.name, region_index)
                if region is None:
                    continue
                texts.append(region["text"])
                region_rows.append(region)

    prediction = normalize_text(" ".join(texts))
    return prediction, runtime, region_rows
