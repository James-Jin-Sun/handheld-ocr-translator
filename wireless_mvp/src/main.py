"""Handheld OCR Translator MVP pipeline: OCR -> clean -> translate -> blur & overlay.

Usage:
    python main.py --image path/to/photo.jpg --target-lang zh-CN

Modules are organized as:
    src/ocr/         OCR engines (incl. Google Cloud Vision), GT-based evaluation harness, text clean-up
    src/translation/ Google Cloud Translation API wrapper
    src/overlay/     Blur source text + draw translated text on the image

The OCR step uses Google Cloud Vision's document text detection, which
returns per-paragraph bounding boxes and text -- no extra line grouping is
needed (unlike Tesseract's word-level output).
"""

import argparse
import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
for package_dir in ("ocr", "translation", "overlay"):
    sys.path.insert(0, str(SRC_DIR / package_dir))

from google_vision_backend import ocr_google_vision_simple  # noqa: E402
from text_cleaning import clean_ocr_text, group_lines_into_blocks  # noqa: E402
from google_translate import DEFAULT_PROJECT_ID, DEFAULT_TARGET_LANGUAGE, translate_batch  # noqa: E402
from draw_translation import save_translated_image, split_text_across_lines  # noqa: E402

DEFAULT_OUTPUT_ROOT = SRC_DIR / "pipeline_results"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Google Cloud Vision -> clean -> translate -> blur & overlay pipeline for a single image."
    )
    parser.add_argument("--image", type=Path, required=True, help="Path to the input image.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Folder to save results in. Defaults to `src/pipeline_results/<image_stem>/`.",
    )
    parser.add_argument(
        "--target-lang",
        default=DEFAULT_TARGET_LANGUAGE,
        help="Target language code, e.g. `zh-CN` (simplified Chinese, default), `en`, `es`.",
    )
    parser.add_argument("--source-lang", default=None, help="Source language code. Auto-detected if omitted.")
    parser.add_argument(
        "--project-id",
        default=DEFAULT_PROJECT_ID,
        help="Google Cloud project ID used for Translation API calls.",
    )
    parser.add_argument(
        "--ocr-language-hints",
        nargs="*",
        default=None,
        help="Optional Vision API language hint codes, e.g. `en` or `zh`.",
    )
    return parser.parse_args()


def run_pipeline(
    image_path,
    output_dir=None,
    target_lang=DEFAULT_TARGET_LANGUAGE,
    source_lang=None,
    project_id=DEFAULT_PROJECT_ID,
    ocr_language_hints=None,
):
    output_dir = output_dir or (DEFAULT_OUTPUT_ROOT / image_path.stem)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) OCR: Google Cloud Vision's document text detection, one region per paragraph.
    _, ocr_runtime, region_rows = ocr_google_vision_simple(image_path, language_hints=ocr_language_hints)

    # 2) Text cleaning: strip OCR noise, drop lines that clean to nothing,
    #    then merge stacked lines into sentence blocks so the translator sees
    #    complete sentences instead of isolated line fragments.
    lines_detected = []
    for row in region_rows:
        text = clean_ocr_text(row["text"])
        if text:
            lines_detected.append({"bbox": row["bbox"], "text": text, "confidence": row["confidence"]})

    print(f"OCR (Google Vision) took {ocr_runtime:.2f}s.")

    if not lines_detected:
        print("No text detected.")
        return None, ocr_runtime

    blocks = group_lines_into_blocks(lines_detected)

    # 3) Translation: translate each whole sentence block via the Google Translate API.
    translations = translate_batch(
        [block["text"] for block in blocks],
        target_language=target_lang,
        source_language=source_lang,
        project_id=project_id,
    )

    # 4) Blur + overlay: split each block's translation back across the
    #    block's original lines (proportionally to each line's text length)
    #    and draw every segment on its own line bbox for a natural layout.
    overlay_regions = []
    block_line_segments = []
    for block, translation in zip(blocks, translations):
        segments = split_text_across_lines(
            translation,
            [len(line["text"]) for line in block["lines"]],
        )
        block_line_segments.append(segments)
        for line, segment in zip(block["lines"], segments):
            if segment:
                overlay_regions.append({"bbox": line["bbox"], "translated_text": segment})

    output_image_path = output_dir / f"{image_path.stem}_translated{image_path.suffix}"
    saved_path = save_translated_image(image_path, overlay_regions, output_image_path)

    manifest = {
        "image": str(image_path),
        "ocr_engine": "google_vision",
        "target_language": target_lang,
        "source_language": source_lang,
        "ocr_runtime_seconds": ocr_runtime,
        "blocks": [
            {
                "bbox": list(block["bbox"]),
                "text": block["text"],
                "translated_text": translation,
                "lines": [
                    {
                        "bbox": list(line["bbox"]),
                        "text": line["text"],
                        "confidence": line["confidence"],
                        "translated_segment": segment,
                    }
                    for line, segment in zip(block["lines"], segments)
                ],
            }
            for block, translation, segments in zip(blocks, translations, block_line_segments)
        ],
    }
    manifest_path = output_dir / f"{image_path.stem}_regions.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Detected {len(lines_detected)} line(s) grouped into {len(blocks)} block(s):")
    for block, translation in zip(blocks, translations):
        print(f"  - {block['text']!r} -> {translation!r}")
    print(f"Saved translated image to {saved_path}")
    print(f"Saved region manifest to {manifest_path}")
    return saved_path, ocr_runtime


def main():
    args = parse_args()
    run_pipeline(
        image_path=args.image,
        output_dir=args.output_dir,
        target_lang=args.target_lang,
        source_lang=args.source_lang,
        project_id=args.project_id,
        ocr_language_hints=args.ocr_language_hints,
    )


if __name__ == "__main__":
    main()
