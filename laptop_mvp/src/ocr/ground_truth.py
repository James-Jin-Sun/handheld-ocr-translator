import csv
import json

from metrics import normalize_text


def load_json_ground_truth(json_path):
    if not json_path.exists():
        return {}

    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    annotations = data.get("annots", data)
    ground_truth = {}
    for image_name, annotation in annotations.items():
        if isinstance(annotation, dict):
            words = annotation.get("text", [])
            if isinstance(words, list):
                text = " ".join(str(word) for word in words)
            else:
                text = str(words)
        elif isinstance(annotation, list):
            text = " ".join(str(word) for word in annotation)
        else:
            text = str(annotation)

        ground_truth[image_name.lower()] = normalize_text(text)

    return ground_truth


def load_json_annotations(json_path):
    if not json_path.exists():
        return {}

    with json_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    annotations = data.get("annots", data)
    parsed = {}
    for image_name, annotation in annotations.items():
        if not isinstance(annotation, dict):
            continue

        texts = annotation.get("text", [])
        boxes = annotation.get("bbox", [])
        records = []
        for bbox, text in zip(boxes, texts):
            x_values = [point[0] for point in bbox]
            y_values = [point[1] for point in bbox]
            records.append(
                {
                    "bbox": (
                        int(min(x_values)),
                        int(min(y_values)),
                        int(max(x_values)),
                        int(max(y_values)),
                    ),
                    "text": normalize_text(str(text)),
                }
            )

        parsed[image_name.lower()] = records

    return parsed


def candidate_gt_files(image_path, gt_dir):
    stem = image_path.stem
    numeric_suffix = stem.split("_")[-1]
    names = [
        f"{stem}.txt",
        f"gt_{stem}.txt",
        f"gt_{numeric_suffix}.txt",
        f"{numeric_suffix}.txt",
    ]
    return [gt_dir / name for name in names]


def find_gt_file(image_path, gt_dir):
    if gt_dir is None:
        return None

    for candidate in candidate_gt_files(image_path, gt_dir):
        if candidate.exists():
            return candidate

    return None


def parse_gt_text_file(gt_path):
    records = []
    for line in gt_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue

        fields = next(csv.reader([line], skipinitialspace=True))
        if len(fields) < 5:
            continue

        x1, y1, x2, y2 = (int(float(value)) for value in fields[:4])
        records.append(
            {
                "bbox": (x1, y1, x2, y2),
                "text": normalize_text(",".join(fields[4:])),
            }
        )

    return records


def get_gt_records(image_path, gt_dir, json_annotations):
    gt_file = find_gt_file(image_path, gt_dir)
    if gt_file is not None:
        return parse_gt_text_file(gt_file), gt_file

    return json_annotations.get(image_path.name.lower(), []), None


def read_text_ground_truth(image_path, gt_dir):
    gt_file = find_gt_file(image_path, gt_dir)
    if gt_file is None:
        return None

    records = parse_gt_text_file(gt_file)
    if records:
        return joined_record_text(records)

    return normalize_text(gt_file.read_text(encoding="utf-8", errors="ignore"))


def joined_record_text(records):
    return normalize_text(" ".join(record["text"] for record in records))


def get_ground_truth(image_path, json_ground_truth, gt_dir):
    json_text = json_ground_truth.get(image_path.name.lower())
    if json_text is not None:
        return json_text

    text_file_gt = read_text_ground_truth(image_path, gt_dir)
    if text_file_gt is not None:
        return text_file_gt

    return ""
