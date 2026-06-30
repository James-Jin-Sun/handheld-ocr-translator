def normalize_text(text):
    return " ".join(text.replace("\r", "\n").split())


def edit_distance(reference, hypothesis):
    rows = len(reference) + 1
    cols = len(hypothesis) + 1
    previous = list(range(cols))

    for row in range(1, rows):
        current = [row] + [0] * (cols - 1)
        ref_item = reference[row - 1]
        for col in range(1, cols):
            hyp_item = hypothesis[col - 1]
            substitution_cost = 0 if ref_item == hyp_item else 1
            current[col] = min(
                previous[col] + 1,
                current[col - 1] + 1,
                previous[col - 1] + substitution_cost,
            )
        previous = current

    return previous[-1]


def error_rate(reference_items, hypothesis_items):
    if not reference_items:
        return 0.0 if not hypothesis_items else 1.0
    return edit_distance(reference_items, hypothesis_items) / len(reference_items)
