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


def safe_divide(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def polygon_to_bbox(polygon):
    """Convert a 4+ point polygon (e.g. [[x, y], ...]) to an (x1, y1, x2, y2) box."""
    x_values = [point[0] for point in polygon]
    y_values = [point[1] for point in polygon]
    return (
        int(min(x_values)),
        int(min(y_values)),
        int(max(x_values)),
        int(max(y_values)),
    )


def compute_iou(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union_area = area_a + area_b - inter_area

    return (inter_area / union_area) if union_area > 0 else 0.0


def match_boxes_by_iou(gt_boxes, pred_boxes, iou_threshold):
    """Greedy one-to-one matching between GT and predicted boxes by IoU."""
    candidate_pairs = []
    for gt_index, gt_box in enumerate(gt_boxes):
        for pred_index, pred_box in enumerate(pred_boxes):
            iou = compute_iou(gt_box, pred_box)
            if iou >= iou_threshold:
                candidate_pairs.append((iou, gt_index, pred_index))

    candidate_pairs.sort(key=lambda item: item[0], reverse=True)

    matched_gt = set()
    matched_pred = set()
    matches = []
    for iou, gt_index, pred_index in candidate_pairs:
        if gt_index in matched_gt or pred_index in matched_pred:
            continue
        matched_gt.add(gt_index)
        matched_pred.add(pred_index)
        matches.append((gt_index, pred_index, iou))

    true_positive = len(matches)
    false_negative = len(gt_boxes) - true_positive
    false_positive = len(pred_boxes) - true_positive
    mean_iou = (
        sum(match[2] for match in matches) / true_positive if true_positive else 0.0
    )

    return {
        "matches": matches,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "mean_iou": mean_iou,
    }


def detection_prf(true_positive, false_positive, false_negative):
    precision = safe_divide(true_positive, true_positive + false_positive)
    recall = safe_divide(true_positive, true_positive + false_negative)
    f1 = safe_divide(2 * precision * recall, precision + recall)
    return precision, recall, f1
