import statistics
import time

from config import (
    MODE_CROPPED,
    MODE_CROPPED_BORDER,
    MODE_EASYOCR_DETECTION,
    MODE_EASYOCR_PARAGRAPH,
    MODE_EASYOCR_SIMPLE,
    MODE_PADDLEOCR_DETECTION,
    MODE_PADDLEOCR_SIMPLE,
    MODE_PSM11_CONFIDENCE,
    MODE_WHOLE_IMAGE,
    current_timestamp,
    parse_args,
)
from dataset import find_images
from ground_truth import (
    get_ground_truth,
    get_gt_records,
    joined_record_text,
    load_json_annotations,
    load_json_ground_truth,
)
from metrics import detection_prf, edit_distance, error_rate
from ocr import (
    configure_tesseract,
    ocr_gt_crops,
    ocr_psm11_confidence,
    ocr_whole_image,
)
from results import save_prediction_text, save_results


def image_metrics(ground_truth, prediction):
    char_edits = edit_distance(ground_truth, prediction)
    word_edits = edit_distance(ground_truth.split(), prediction.split())
    return {
        "char_edits": char_edits,
        "word_edits": word_edits,
        "cer": error_rate(ground_truth, prediction),
        "wer": error_rate(ground_truth.split(), prediction.split()),
    }


def resolve_image_ground_truth(image_path, records, json_ground_truth, gt_dir):
    ground_truth = joined_record_text(records)
    if ground_truth:
        return ground_truth
    return get_ground_truth(image_path, json_ground_truth, gt_dir)


def empty_ocr_result(prediction, runtime_seconds, method):
    return {
        "prediction": prediction,
        "runtime_seconds": runtime_seconds,
        "method": method,
        "crop_rows": [],
        "confidence_rows": [],
        "region_rows": [],
        "detection_metrics": None,
    }


def run_ocr_for_image(image_path, records, config):
    if config.mode == MODE_WHOLE_IMAGE:
        prediction, runtime_seconds = ocr_whole_image(
            image_path,
            config.tesseract_config,
        )
        return empty_ocr_result(prediction, runtime_seconds, MODE_WHOLE_IMAGE)

    if config.mode == MODE_PSM11_CONFIDENCE:
        prediction, runtime_seconds, confidence_rows = ocr_psm11_confidence(
            image_path,
            config,
        )
        result = empty_ocr_result(prediction, runtime_seconds, MODE_PSM11_CONFIDENCE)
        result["confidence_rows"] = confidence_rows
        return result

    if config.mode == MODE_EASYOCR_SIMPLE:
        from easyocr_backend import ocr_easyocr_simple

        prediction, runtime_seconds, region_rows = ocr_easyocr_simple(
            image_path,
            config,
        )
        result = empty_ocr_result(prediction, runtime_seconds, MODE_EASYOCR_SIMPLE)
        result["region_rows"] = region_rows
        return result

    if config.mode == MODE_EASYOCR_PARAGRAPH:
        from easyocr_backend import ocr_easyocr_paragraph

        prediction, runtime_seconds, region_rows = ocr_easyocr_paragraph(
            image_path,
            config,
        )
        result = empty_ocr_result(prediction, runtime_seconds, MODE_EASYOCR_PARAGRAPH)
        result["region_rows"] = region_rows
        return result

    if config.mode == MODE_EASYOCR_DETECTION:
        from easyocr_backend import ocr_easyocr_detection

        prediction, runtime_seconds, crop_rows, detection_metrics = (
            ocr_easyocr_detection(image_path, records, config)
        )
        result = empty_ocr_result(prediction, runtime_seconds, MODE_EASYOCR_DETECTION)
        result["crop_rows"] = crop_rows
        result["detection_metrics"] = detection_metrics
        return result

    if config.mode == MODE_PADDLEOCR_SIMPLE:
        from paddleocr_backend import ocr_paddleocr_simple

        prediction, runtime_seconds, region_rows = ocr_paddleocr_simple(
            image_path,
            config,
        )
        result = empty_ocr_result(prediction, runtime_seconds, MODE_PADDLEOCR_SIMPLE)
        result["region_rows"] = region_rows
        return result

    if config.mode == MODE_PADDLEOCR_DETECTION:
        from paddleocr_backend import ocr_paddleocr_detection

        prediction, runtime_seconds, crop_rows, detection_metrics = (
            ocr_paddleocr_detection(image_path, records, config)
        )
        result = empty_ocr_result(prediction, runtime_seconds, MODE_PADDLEOCR_DETECTION)
        result["crop_rows"] = crop_rows
        result["detection_metrics"] = detection_metrics
        return result

    if not records:
        prediction, runtime_seconds = ocr_whole_image(
            image_path,
            config.tesseract_config,
        )
        return empty_ocr_result(prediction, runtime_seconds, MODE_WHOLE_IMAGE)

    if config.mode == MODE_CROPPED_BORDER:
        prediction, runtime_seconds, crop_rows = ocr_gt_crops(
            image_path,
            records,
            config,
            with_border=True,
        )
        result = empty_ocr_result(prediction, runtime_seconds, MODE_CROPPED_BORDER)
        result["crop_rows"] = crop_rows
        return result

    prediction, runtime_seconds, crop_rows = ocr_gt_crops(
        image_path,
        records,
        config,
    )
    result = empty_ocr_result(prediction, runtime_seconds, MODE_CROPPED)
    result["crop_rows"] = crop_rows
    return result


def build_detection_summary(config, detection_rows):
    if not detection_rows:
        return None

    total_tp = sum(row["true_positive"] for row in detection_rows)
    total_fp = sum(row["false_positive"] for row in detection_rows)
    total_fn = sum(row["false_negative"] for row in detection_rows)
    precision, recall, f1 = detection_prf(total_tp, total_fp, total_fn)

    iou_values = [row["mean_iou"] for row in detection_rows if row["true_positive"] > 0]
    mean_iou = statistics.mean(iou_values) if iou_values else 0.0

    return {
        "iou_threshold": config.detection_iou_threshold,
        "true_positive": total_tp,
        "false_positive": total_fp,
        "false_negative": total_fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mean_iou": mean_iou,
    }


def build_summary(
    config,
    rows,
    totals,
    detection_rows,
    test_started_at,
    wall_clock_seconds,
):
    finished_at = current_timestamp()
    total_ocr_runtime = sum(row["runtime_seconds"] for row in rows)
    summary = {
        "images_processed": len(rows),
        "mode": config.mode,
        "cer": (totals["char_edits"] / totals["chars"]) if totals["chars"] else 0.0,
        "wer": (totals["word_edits"] / totals["words"]) if totals["words"] else 0.0,
        "average_runtime_seconds": statistics.mean(
            row["runtime_seconds"] for row in rows
        ),
        "total_ocr_runtime_seconds": total_ocr_runtime,
        "test_time": {
            "started_at": test_started_at,
            "finished_at": finished_at,
            "wall_clock_seconds": wall_clock_seconds,
        },
        "test_config": config.summary_config(),
    }

    detection_summary = build_detection_summary(config, detection_rows)
    if detection_summary:
        summary["detection_summary"] = detection_summary

    # Keep common paths at the top level for quick scanning and older notebooks.
    summary.update(
        {
            "image_dir": str(config.image_dir),
            "json_gt": str(config.json_gt),
            "gt_dir": str(config.gt_dir),
            "output_dir": str(config.output_dir),
        }
    )
    return summary


def evaluate(config):
    configure_tesseract(config.tesseract_cmd)

    if not config.image_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {config.image_dir}")

    gt_dir = config.gt_dir if config.gt_dir.exists() else None
    json_ground_truth = load_json_ground_truth(config.json_gt)
    json_annotations = load_json_annotations(config.json_gt)
    images = find_images(config.image_dir, config.limit)

    if not images:
        raise FileNotFoundError(f"No images found in: {config.image_dir}")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    crop_rows = []
    confidence_rows = []
    region_rows = []
    detection_rows = []
    totals = {"char_edits": 0, "chars": 0, "word_edits": 0, "words": 0}
    test_started_at = config.run_started_at
    wall_clock_start = time.perf_counter()

    for index, image_path in enumerate(images, start=1):
        records, gt_file = get_gt_records(image_path, gt_dir, json_annotations)
        ground_truth = resolve_image_ground_truth(
            image_path,
            records,
            json_ground_truth,
            gt_dir,
        )
        ocr_result = run_ocr_for_image(image_path, records, config)
        prediction = ocr_result["prediction"]
        runtime_seconds = ocr_result["runtime_seconds"]
        method = ocr_result["method"]
        image_confidence_rows = ocr_result["confidence_rows"]
        image_region_rows = ocr_result["region_rows"]
        detection_metrics = ocr_result["detection_metrics"]

        prediction_path = save_prediction_text(
            config.output_dir,
            image_path,
            prediction,
        )
        crop_rows.extend(ocr_result["crop_rows"])
        confidence_rows.extend(image_confidence_rows)
        region_rows.extend(image_region_rows)
        if detection_metrics:
            detection_rows.append(detection_metrics)

        metrics = image_metrics(ground_truth, prediction)
        totals["char_edits"] += metrics["char_edits"]
        totals["chars"] += len(ground_truth)
        totals["word_edits"] += metrics["word_edits"]
        totals["words"] += len(ground_truth.split())

        row = {
            "index": index,
            "image": image_path.name,
            "method": method,
            "gt_file": str(gt_file) if gt_file else "",
            "crop_count": len(records),
            "confidence_token_count": len(image_confidence_rows),
            "kept_confidence_token_count": sum(
                1 for token_row in image_confidence_rows if token_row["kept"]
            ),
            "region_count": len(image_region_rows),
            "ground_truth": ground_truth,
            "prediction": prediction,
            "prediction_file": str(prediction_path),
            "cer": metrics["cer"],
            "wer": metrics["wer"],
            "runtime_seconds": runtime_seconds,
        }
        if detection_metrics:
            row["detection_precision"] = detection_metrics["precision"]
            row["detection_recall"] = detection_metrics["recall"]
            row["detection_f1"] = detection_metrics["f1"]
            row["detection_mean_iou"] = detection_metrics["mean_iou"]
        rows.append(row)

        detection_summary_line = ""
        if detection_metrics:
            detection_summary_line = (
                f" detect_P={detection_metrics['precision']:.2f} "
                f"detect_R={detection_metrics['recall']:.2f}"
            )
        print(
            f"{index:02d}/{len(images)} {image_path.name}: "
            f"CER={metrics['cer']:.4f} WER={metrics['wer']:.4f} "
            f"runtime={runtime_seconds:.3f}s{detection_summary_line}"
        )

    wall_clock_seconds = time.perf_counter() - wall_clock_start
    summary = build_summary(
        config,
        rows,
        totals,
        detection_rows,
        test_started_at,
        wall_clock_seconds,
    )
    save_results(
        config.output_dir,
        rows,
        crop_rows,
        confidence_rows,
        summary,
        region_rows=region_rows,
        detection_rows=detection_rows,
    )
    return summary


def print_summary(summary):
    print("\nAggregate metrics:")
    print(f"CER: {summary['cer']:.4f}")
    print(f"WER: {summary['wer']:.4f}")
    print(f"Runtime per image: {summary['average_runtime_seconds']:.3f}s")
    print(f"Total OCR runtime: {summary['total_ocr_runtime_seconds']:.3f}s")
    print(f"Wall-clock test time: {summary['test_time']['wall_clock_seconds']:.3f}s")

    detection_summary = summary.get("detection_summary")
    if detection_summary:
        print("\nDetection metrics (vs. GT bounding boxes):")
        print(f"IoU threshold: {detection_summary['iou_threshold']}")
        print(f"Precision: {detection_summary['precision']:.4f}")
        print(f"Recall: {detection_summary['recall']:.4f}")
        print(f"F1: {detection_summary['f1']:.4f}")
        print(f"Mean IoU (matched boxes): {detection_summary['mean_iou']:.4f}")


def main():
    config = parse_args()
    summary = evaluate(config)
    print_summary(summary)


if __name__ == "__main__":
    main()
