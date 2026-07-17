"""Standalone smoke test for google_translate.py (no OCR/overlay involved).

Usage:
    python test_translation.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from google_translate import (
    DEFAULT_LOCATION,
    DEFAULT_PROJECT_ID,
    DEFAULT_TARGET_LANGUAGE,
    translate_text,
)

SAMPLE_TEXT = "Tiredness kills A short break could save your life"
OUTPUT_DIR = Path(__file__).resolve().parent / "test_output"


def main():
    translated_text = translate_text(SAMPLE_TEXT, target_language=DEFAULT_TARGET_LANGUAGE)

    result = {
        "input_text": SAMPLE_TEXT,
        "translated_text": translated_text,
        "target_language": DEFAULT_TARGET_LANGUAGE,
        "project_id": DEFAULT_PROJECT_ID,
        "location": DEFAULT_LOCATION,
        "model": "general/nmt",
        "tested_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "translation_result.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Input:      {SAMPLE_TEXT}")
    print(f"Translated: {translated_text}")
    print(f"Saved to:   {output_path}")


if __name__ == "__main__":
    main()
