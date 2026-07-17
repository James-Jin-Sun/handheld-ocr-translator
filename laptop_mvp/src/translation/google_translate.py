"""Thin wrapper around the Google Cloud Translation API.

Requires the `google-cloud-translate` package and a service-account key:

    pip install google-cloud-translate

By default, the key is looked up at `laptop_mvp/keys/google-translate-key.json`
(see `default_credentials_path`). You can override this by setting the
`GOOGLE_APPLICATION_CREDENTIALS` environment variable to a different path.

Never commit the key file to GitHub -- `laptop_mvp/keys/` is git-ignored.
"""

import os
from functools import lru_cache
from pathlib import Path

try:
    from google.cloud import translate_v2 as translate
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install it with `pip install google-cloud-translate`."
    ) from exc


def default_credentials_path():
    """Default service-account key location: laptop_mvp/keys/google-translate-key.json."""
    return Path(__file__).resolve().parents[2] / "keys" / "google-translate-key.json"


def _ensure_credentials_env():
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return

    key_path = default_credentials_path()
    if key_path.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(key_path)


@lru_cache(maxsize=1)
def get_client():
    _ensure_credentials_env()
    return translate.Client()


def translate_text(text, target_language="en", source_language=None):
    """Translate a single string. Returns "" for empty/whitespace-only input."""
    if not text or not text.strip():
        return ""

    client = get_client()
    result = client.translate(
        text,
        target_language=target_language,
        source_language=source_language,
    )
    return result["translatedText"]


def translate_batch(texts, target_language="en", source_language=None):
    """Translate a list of strings in one API call, preserving order and
    passing empty strings through untouched."""
    non_empty_indices = [index for index, text in enumerate(texts) if text and text.strip()]
    translations = [""] * len(texts)

    if not non_empty_indices:
        return translations

    client = get_client()
    results = client.translate(
        [texts[index] for index in non_empty_indices],
        target_language=target_language,
        source_language=source_language,
    )
    for index, result in zip(non_empty_indices, results):
        translations[index] = result["translatedText"]

    return translations
