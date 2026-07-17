"""Handheld OCR Translator MVP pipeline: OCR -> clean -> translate -> blur & overlay.

Usage:
    python main.py --image path/to/photo.jpg --target-lang es

Modules are organized as:
    src/ocr/         OCR engines, GT-based evaluation harness, text clean-up
    src/translation/ Google Cloud Translation API wrapper
    src/overlay/     Blur source text + draw translated text on the image
"""

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
for package_dir in ("ocr", "translation", "overlay"):
    sys.path.insert(0, str(SRC_DIR / package_dir))

from ocr import configure_tesseract, ocr_psm11_confidence  # noqa: E402
from text_cleaning import clean_ocr_text, group_tokens_into_lines  # noqa: E402
from google_translate import translate_batch  # noqa: E402
from draw_translation import save_translated_image  # noqa: E402


class SimpleOcrConfig:
    """Minimal duck-typed config for `ocr_psm11_confidence`, which only
    needs these two fields (see src/ocr/ocr.py)."""

    def __init__(self, tesseract_config="--psm 11", confidence_threshold=40.0):
        self.confidence_tesseract_config = tesseract_config
        self.confidence_threshold = confidence_threshold


def parse_args():
    parser = argparse.ArgumentParser(
        description="OCR -> clean -> translate -> blur & overlay pipeline for a single image."
    )
    parser.add_argument("--image", type=Path, required=True, help="Path to the input image.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to save the translated image. Defaults to `<image>_translated<ext>`.",
    )
    parser.add_argument("--target-lang", default="en", help="Target language code, e.g. `en`, `es`, `zh-CN`.")
    parser.add_argument("--source-lang", default=None, help="Source language code. Auto-detected if omitted.")
    parser.add_argument(
        "--tesseract-cmd",
        default=None,
        help="Optional full path to tesseract.exe if it is not on PATH.",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=40.0,
        help="Minimum Tesseract confidence score kept before translation.",
    )
    return parser.parse_args()


def run_pipeline(
    image_path,
    output_path=None,
    target_lang="en",
    source_lang=None,
    tesseract_cmd=None,
    confidence_threshold=40.0,
):
    # 1) OCR: detect text with per-word boxes, keep only confident tokens.
    configure_tesseract(tesseract_cmd)
    ocr_config = SimpleOcrConfig(confidence_threshold=confidence_threshold)
    _, _, token_rows = ocr_psm11_confidence(image_path, ocr_config)

    # 2) Text cleaning: merge tokens into lines, strip OCR noise.
    lines = group_tokens_into_lines(token_rows)
    for line in lines:
        line["text"] = clean_ocr_text(line["text"])
    lines = [line for line in lines if line["text"]]

    if not lines:
        print("No text detected.")
        return None

    # 3) Translation: translate each line via the Google Translate API.
    translations = translate_batch(
        [line["text"] for line in lines],
        target_language=target_lang,
        source_language=source_lang,
    )

    # 4) Blur + overlay: hide the source text and draw the translation on top.
    regions = [
        {"bbox": line["bbox"], "translated_text": translation}
        for line, translation in zip(lines, translations)
    ]
    output_path = output_path or image_path.with_name(f"{image_path.stem}_translated{image_path.suffix}")
    saved_path = save_translated_image(image_path, regions, output_path)

    print(f"Detected {len(lines)} line(s):")
    for line, translation in zip(lines, translations):
        print(f"  - {line['text']!r} -> {translation!r}")
    print(f"Saved translated image to {saved_path}")
    return saved_path


def main():
    args = parse_args()
    run_pipeline(
        image_path=args.image,
        output_path=args.output,
        target_lang=args.target_lang,
        source_lang=args.source_lang,
        tesseract_cmd=args.tesseract_cmd,
        confidence_threshold=args.confidence_threshold,
    )


if __name__ == "__main__":
    main()
