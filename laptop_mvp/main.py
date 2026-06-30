import statistics
import time

from config import (
    MODE_CROPPED,
    MODE_CROPPED_BORDER,
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
from metrics import edit_distance, error_rate
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


def run_ocr_for_image(image_path, records, config):
    if config.mode == MODE_WHOLE_IMAGE:
        prediction, runtime_seconds = ocr_whole_image(
            image_path,
            config.tesseract_config,
        )
        return prediction, runtime_seconds, [], [], MODE_WHOLE_IMAGE

    if config.mode == MODE_PSM11_CONFIDENCE:
        prediction, runtime_seconds, confidence_rows = ocr_psm11_confidence(
            image_path,
            config,
        )
        return prediction, runtime_seconds, [], confidence_rows, MODE_PSM11_CONFIDENCE

    if not records:
        prediction, runtime_seconds = ocr_whole_image(
            image_path,
            config.tesseract_config,
        )
        return prediction, runtime_seconds, [], [], MODE_WHOLE_IMAGE

    if config.mode == MODE_CROPPED_BORDER:
        prediction, runtime_seconds, crop_rows = ocr_gt_crops(
            image_path,
            records,
            config,
            with_border=True,
        )
        return prediction, runtime_seconds, crop_rows, [], MODE_CROPPED_BORDER

    prediction, runtime_seconds, crop_rows = ocr_gt_crops(
        image_path,
        records,
        config,
    )
    return prediction, runtime_seconds, crop_rows, [], MODE_CROPPED


def build_summary(config, rows, totals, test_started_at, wall_clock_seconds):
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
        (
            prediction,
            runtime_seconds,
            image_crop_rows,
            image_confidence_rows,
            method,
        ) = run_ocr_for_image(
            image_path,
            records,
            config,
        )
        prediction_path = save_prediction_text(
            config.output_dir,
            image_path,
            prediction,
        )
        crop_rows.extend(image_crop_rows)
        confidence_rows.extend(image_confidence_rows)

        metrics = image_metrics(ground_truth, prediction)
        totals["char_edits"] += metrics["char_edits"]
        totals["chars"] += len(ground_truth)
        totals["word_edits"] += metrics["word_edits"]
        totals["words"] += len(ground_truth.split())

        rows.append(
            {
                "index": index,
                "image": image_path.name,
                "method": method,
                "gt_file": str(gt_file) if gt_file else "",
                "crop_count": len(records),
                "confidence_token_count": len(image_confidence_rows),
                "kept_confidence_token_count": sum(
                    1 for row in image_confidence_rows if row["kept"]
                ),
                "ground_truth": ground_truth,
                "prediction": prediction,
                "prediction_file": str(prediction_path),
                "cer": metrics["cer"],
                "wer": metrics["wer"],
                "runtime_seconds": runtime_seconds,
            }
        )

        print(
            f"{index:02d}/{len(images)} {image_path.name}: "
            f"CER={metrics['cer']:.4f} WER={metrics['wer']:.4f} "
            f"runtime={runtime_seconds:.3f}s"
        )

    wall_clock_seconds = time.perf_counter() - wall_clock_start
    summary = build_summary(config, rows, totals, test_started_at, wall_clock_seconds)
    save_results(config.output_dir, rows, crop_rows, confidence_rows, summary)
    return summary


def print_summary(summary):
    print("\nAggregate metrics:")
    print(f"CER: {summary['cer']:.4f}")
    print(f"WER: {summary['wer']:.4f}")
    print(f"Runtime per image: {summary['average_runtime_seconds']:.3f}s")
    print(f"Total OCR runtime: {summary['total_ocr_runtime_seconds']:.3f}s")
    print(f"Wall-clock test time: {summary['test_time']['wall_clock_seconds']:.3f}s")


def main():
    config = parse_args()
    summary = evaluate(config)
    print_summary(summary)


if __name__ == "__main__":
    main()
