import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


MODE_CROPPED = "gt_bbox_crops"
MODE_WHOLE_IMAGE = "whole_image"


@dataclass
class EvaluationConfig:
    image_dir: Path
    json_gt: Path
    gt_dir: Path
    output_dir: Path
    limit: int
    mode: str
    tesseract_cmd: Optional[str]
    tesseract_config: str
    crop_tesseract_config: str
    crop_padding: int
    crop_scale: float
    min_crop_height: int
    run_started_at: str

    def summary_config(self):
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Path):
                data[key] = str(value)
        return data


def current_timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_default_paths():
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    workspace_root = repo_root.parent

    dataset_root_candidates = [
        repo_root / "Icdar2013",
        workspace_root / "Icdar2013",
    ]
    dataset_root = next(
        (candidate for candidate in dataset_root_candidates if candidate.exists()),
        workspace_root / "Icdar2013",
    )
    gt_dir_candidates = [
        dataset_root / "Challenge2_Test_Task1_GT (1)",
        dataset_root / "Challenge2_Test_Task12_GT",
        dataset_root / "Challenge2_Test_Task1_GT",
    ]
    gt_dir = next(
        (candidate for candidate in gt_dir_candidates if candidate.exists()),
        dataset_root / "Challenge2_Test_Task1_GT (1)",
    )

    return {
        "image_dir": dataset_root / "Challenge2_Test_Task12_Images",
        "json_gt": dataset_root / "test_gt.json",
        "gt_dir": gt_dir,
        "cropped_output_dir": script_dir / "ocr_results_cropped",
        "whole_image_output_dir": script_dir / "ocr_results_whole_image",
    }


def parse_args():
    defaults = resolve_default_paths()

    parser = argparse.ArgumentParser(
        description="Evaluate Tesseract OCR on ICDAR2013 test images."
    )
    parser.add_argument(
        "--mode",
        choices=[MODE_CROPPED, MODE_WHOLE_IMAGE],
        default=MODE_CROPPED,
        help="Run GT-bbox cropped OCR or whole-image OCR.",
    )
    parser.add_argument(
        "--whole-image",
        action="store_true",
        help="Shortcut for `--mode whole_image`.",
    )
    parser.add_argument("--image-dir", type=Path, default=defaults["image_dir"])
    parser.add_argument("--json-gt", type=Path, default=defaults["json_gt"])
    parser.add_argument("--gt-dir", type=Path, default=defaults["gt_dir"])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to a mode-specific result folder.",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--crop-padding", type=int, default=4)
    parser.add_argument("--crop-scale", type=float, default=3.0)
    parser.add_argument("--min-crop-height", type=int, default=48)
    parser.add_argument(
        "--tesseract-cmd",
        default=None,
        help="Optional full path to tesseract.exe if it is not on PATH.",
    )
    parser.add_argument(
        "--tesseract-config",
        default="--psm 6",
        help="Config used for whole-image OCR.",
    )
    parser.add_argument(
        "--crop-tesseract-config",
        default="--psm 8",
        help="Config used for each cropped text region.",
    )

    args = parser.parse_args()
    mode = MODE_WHOLE_IMAGE if args.whole_image else args.mode
    if args.output_dir is not None:
        output_dir = args.output_dir
    elif mode == MODE_WHOLE_IMAGE:
        output_dir = defaults["whole_image_output_dir"]
    else:
        output_dir = defaults["cropped_output_dir"]

    return EvaluationConfig(
        image_dir=args.image_dir,
        json_gt=args.json_gt,
        gt_dir=args.gt_dir,
        output_dir=output_dir,
        limit=args.limit,
        mode=mode,
        tesseract_cmd=args.tesseract_cmd,
        tesseract_config=args.tesseract_config,
        crop_tesseract_config=args.crop_tesseract_config,
        crop_padding=args.crop_padding,
        crop_scale=args.crop_scale,
        min_crop_height=args.min_crop_height,
        run_started_at=current_timestamp(),
    )
