import re

from metrics import normalize_text

# Keep common punctuation used in real sentences; drop stray symbol noise
# that OCR engines occasionally emit around text regions.
_NOISE_CHARS_PATTERN = re.compile(r"[^\w\s.,!?'\"\-:;()%/]", re.UNICODE)
_REPEATED_PUNCTUATION_PATTERN = re.compile(r"([.,!?])\1{2,}")


def clean_ocr_text(text):
    """Light clean-up for raw OCR output before translation.

    Strips stray symbol noise, collapses runs of the same punctuation mark,
    and normalizes whitespace.
    """
    if not text:
        return ""

    text = _NOISE_CHARS_PATTERN.sub(" ", text)
    text = _REPEATED_PUNCTUATION_PATTERN.sub(r"\1", text)
    return normalize_text(text)


def group_tokens_into_lines(token_rows):
    """Group Tesseract word-level token rows (as produced by
    `ocr_psm11_confidence`) into line-level regions.

    Returns a list of dicts, in reading order, each with:
    - "text": the words on that line joined with spaces
    - "bbox": the (x1, y1, x2, y2) box covering the whole line
    """
    lines = {}
    order = []

    for row in token_rows:
        if not row.get("kept") or not row.get("text"):
            continue

        key = (row["page_num"], row["block_num"], row["par_num"], row["line_num"])
        left = row["left"]
        top = row["top"]
        right = left + row["width"]
        bottom = top + row["height"]

        if key not in lines:
            lines[key] = {"words": [], "left": left, "top": top, "right": right, "bottom": bottom}
            order.append(key)

        line = lines[key]
        line["words"].append(row["text"])
        line["left"] = min(line["left"], left)
        line["top"] = min(line["top"], top)
        line["right"] = max(line["right"], right)
        line["bottom"] = max(line["bottom"], bottom)

    return [
        {
            "text": " ".join(lines[key]["words"]),
            "bbox": (
                lines[key]["left"],
                lines[key]["top"],
                lines[key]["right"],
                lines[key]["bottom"],
            ),
        }
        for key in order
    ]
