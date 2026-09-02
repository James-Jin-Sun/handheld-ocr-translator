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


def _horizontal_overlap_ratio(box_a, box_b):
    """Overlap of the two x-ranges, as a fraction of the narrower box's width."""
    overlap = min(box_a[2], box_b[2]) - max(box_a[0], box_b[0])
    narrower_width = min(box_a[2] - box_a[0], box_b[2] - box_b[0])
    return (overlap / narrower_width) if narrower_width > 0 else 0.0


def group_lines_into_blocks(
    lines,
    max_gap_factor=0.7,
    min_horizontal_overlap=0.3,
    min_height_similarity=0.5,
):
    """Merge line-level OCR regions into sentence/paragraph blocks so the
    translator sees complete sentences instead of isolated line fragments.

    Two consecutive lines (in top-to-bottom order) join the same block when:
    - the vertical gap between them is small relative to their line height,
    - their x-ranges overlap (i.e. they visually stack like lines of the
      same sentence/paragraph), and
    - their line heights are similar (`min(h1, h2) / max(h1, h2)` is at
      least `min_height_similarity`) -- this keeps e.g. a large standalone
      number/heading from being merged with unrelated small captions just
      because they happen to sit close together.

    `lines` is a list of dicts with at least "text" and "bbox" (x1, y1, x2, y2).
    Returns a list of dicts, each with:
    - "text": all line texts joined with spaces, in reading order
    - "bbox": the union box covering the whole block
    - "lines": the original line dicts that were merged
    """
    if not lines:
        return []

    ordered = sorted(lines, key=lambda line: (line["bbox"][1], line["bbox"][0]))

    blocks = []
    for line in ordered:
        x1, y1, x2, y2 = line["bbox"]
        line_height = max(1, y2 - y1)

        target_block = None
        for block in blocks:
            bx1, by1, bx2, by2 = block["bbox"]
            last_height = max(1, block["last_line_height"])
            vertical_gap = y1 - by2
            max_gap = max_gap_factor * min(line_height, last_height)
            height_similarity = min(line_height, last_height) / max(line_height, last_height)

            if (
                vertical_gap <= max_gap
                and height_similarity >= min_height_similarity
                and _horizontal_overlap_ratio(line["bbox"], block["bbox"]) >= min_horizontal_overlap
            ):
                target_block = block
                break

        if target_block is None:
            blocks.append(
                {
                    "lines": [line],
                    "bbox": [x1, y1, x2, y2],
                    "last_line_height": line_height,
                }
            )
        else:
            target_block["lines"].append(line)
            bx1, by1, bx2, by2 = target_block["bbox"]
            target_block["bbox"] = [min(bx1, x1), min(by1, y1), max(bx2, x2), max(by2, y2)]
            target_block["last_line_height"] = line_height

    return [
        {
            "text": " ".join(line["text"] for line in block["lines"]),
            "bbox": tuple(block["bbox"]),
            "lines": block["lines"],
        }
        for block in blocks
    ]


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
