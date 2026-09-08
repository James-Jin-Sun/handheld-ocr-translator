"""Wrapper around the Google Cloud Translation API - Advanced (v3).

Uses the built-in `general/nmt` model and Application Default Credentials
(ADC) from an OAuth user login (`gcloud auth application-default login`) --
no API key or service-account JSON file needed. Run once per machine:

    gcloud auth application-default login
    gcloud config set project handheld-ocr-translator
"""

from functools import lru_cache

try:
    from google.cloud import translate_v3 as translate
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: install it with `pip install google-cloud-translate`."
    ) from exc


DEFAULT_PROJECT_ID = "handheld-ocr-translator"
DEFAULT_LOCATION = "global"
DEFAULT_TARGET_LANGUAGE = "zh-CN"  # Simplified Chinese


@lru_cache(maxsize=1)
def get_client():
    return translate.TranslationServiceClient()


def _parent(project_id):
    return f"projects/{project_id}/locations/{DEFAULT_LOCATION}"


def _model_path(project_id):
    return f"{_parent(project_id)}/models/general/nmt"


def translate_text(
    text,
    target_language=DEFAULT_TARGET_LANGUAGE,
    source_language=None,
    project_id=DEFAULT_PROJECT_ID,
):
    """Translate a single string with the general/nmt model. Returns "" for empty input."""
    if not text or not text.strip():
        return ""

    client = get_client()
    response = client.translate_text(
        contents=[text],
        target_language_code=target_language,
        source_language_code=source_language,
        parent=_parent(project_id),
        model=_model_path(project_id),
        mime_type="text/plain",
    )
    return response.translations[0].translated_text


def translate_batch(
    texts,
    target_language=DEFAULT_TARGET_LANGUAGE,
    source_language=None,
    project_id=DEFAULT_PROJECT_ID,
):
    """Translate a list of strings in one API call, preserving order and
    passing empty strings through untouched."""
    non_empty_indices = [index for index, text in enumerate(texts) if text and text.strip()]
    translations = [""] * len(texts)

    if not non_empty_indices:
        return translations

    client = get_client()
    response = client.translate_text(
        contents=[texts[index] for index in non_empty_indices],
        target_language_code=target_language,
        source_language_code=source_language,
        parent=_parent(project_id),
        model=_model_path(project_id),
        mime_type="text/plain",
    )
    for index, translation in zip(non_empty_indices, response.translations):
        translations[index] = translation.translated_text

    return translations
