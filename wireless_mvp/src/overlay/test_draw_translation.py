"""Standalone smoke test for draw_translation.py (no OCR/translation calls).

Uses hand-picked regions on a real ICDAR2013 test image, with translated
text taken from a prior run of the translation module, to verify the
blur + overlay rendering in isolation.

Usage:
    python test_draw_translation.py
"""

from pathlib import Path

from draw_translation import save_translated_image

IMAGE_PATH = Path(r"D:\Handheld OCR Translator\Icdar2013\Challenge2_Test_Task12_Images\img_1.jpg")
OUTPUT_DIR = Path(__file__).resolve().parent / "test_output"

# Hand-picked regions covering the billboard text in img_1.jpg (960x1280),
# with Chinese translations taken from a prior google_translate.py run.
REGIONS = [
    {"bbox": (40, 20, 920, 380), "translated_text": "疲劳会致命"},
    {"bbox": (20, 560, 940, 820), "translated_text": "短暂休息可以节省"},
    {"bbox": (150, 900, 810, 1150), "translated_text": "你的生活"},
]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{IMAGE_PATH.stem}_translated{IMAGE_PATH.suffix}"

    saved_path = save_translated_image(IMAGE_PATH, REGIONS, output_path)

    print(f"Source image: {IMAGE_PATH}")
    print(f"Regions drawn: {len(REGIONS)}")
    for region in REGIONS:
        print(f"  - {region['bbox']} -> {region['translated_text']!r}")
    print(f"Saved to: {saved_path}")


if __name__ == "__main__":
    main()
