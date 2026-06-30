import csv
import json


def save_prediction_text(output_dir, image_path, prediction):
    prediction_dir = output_dir / "predictions"
    prediction_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = prediction_dir / f"{image_path.stem}.txt"
    prediction_path.write_text(prediction + "\n", encoding="utf-8")
    return prediction_path


def save_results(output_dir, rows, crop_rows, summary):
    summary_path = output_dir / "summary.json"
    details_json_path = output_dir / "per_image_results.json"
    details_csv_path = output_dir / "per_image_results.csv"
    crop_json_path = output_dir / "per_crop_results.json"
    crop_csv_path = output_dir / "per_crop_results.csv"

    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    details_json_path.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with details_csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    if crop_rows:
        crop_json_path.write_text(
            json.dumps(crop_rows, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        with crop_csv_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=crop_rows[0].keys())
            writer.writeheader()
            writer.writerows(crop_rows)

    print("\nSaved results:")
    print(f"- {summary_path}")
    print(f"- {details_json_path}")
    print(f"- {details_csv_path}")
    print(f"- {output_dir / 'predictions'}")
    if crop_rows:
        print(f"- {crop_json_path}")
        print(f"- {crop_csv_path}")
        print(f"- {output_dir / 'crops'}")
