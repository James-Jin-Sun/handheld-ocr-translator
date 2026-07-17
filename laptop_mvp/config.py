import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


MODE_CROPPED = "gt_bbox_crops"
MODE_CROPPED_BORDER = "gt_bbox_crops_border"
MODE_WHOLE_IMAGE = "whole_image"
MODE_PSM11_CONFIDENCE = "psm11_confidence"
MODE_EASYOCR_SIMPLE = "easyocr_simple"
MODE_EASYOCR_PARAGRAPH = "easyocr_paragraph"
MODE_EASYOCR_DETECTION = "easyocr_detection"
MODE_PADDLEOCR_SIMPLE = "paddleocr_simple"
MODE_PADDLEOCR_DETECTION = "paddleocr_detection"


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
    crop_border_tesseract_config: str
    confidence_tesseract_config: str
    confidence_threshold: float
    crop_padding: int
    crop_scale: float
    min_crop_height: int
    crop_border_pixels: int
    crop_border_color: str
    easyocr_languages: tuple
    easyocr_gpu: bool
    paddleocr_lang: str
    paddleocr_gpu: bool
    detection_iou_threshold: float
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
        "cropped_border_output_dir": script_dir / "ocr_results_cropped_border",
        "whole_image_output_dir": script_dir / "ocr_results_whole_image",
        "psm11_confidence_output_dir": script_dir / "ocr_results_psm11_confidence",
        "easyocr_simple_output_dir": script_dir / "ocr_results_easyocr_simple",
        "easyocr_paragraph_output_dir": script_dir / "ocr_results_easyocr_paragraph",
        "easyocr_detection_output_dir": script_dir / "ocr_results_easyocr_detection",
        "paddleocr_simple_output_dir": script_dir / "ocr_results_paddleocr_simple",
        "paddleocr_detection_output_dir": script_dir / "ocr_results_paddleocr_detection",
    }


def parse_args():
    defaults = resolve_default_paths()

    parser = argparse.ArgumentParser(
        description="Evaluate Tesseract OCR on ICDAR2013 test images."
    )
    parser.add_argument(
        "--mode",
        choices=[
            MODE_CROPPED,
            MODE_CROPPED_BORDER,
            MODE_WHOLE_IMAGE,
            MODE_PSM11_CONFIDENCE,
            MODE_EASYOCR_SIMPLE,
            MODE_EASYOCR_PARAGRAPH,
            MODE_EASYOCR_DETECTION,
            MODE_PADDLEOCR_SIMPLE,
            MODE_PADDLEOCR_DETECTION,
        ],
        default=MODE_CROPPED,
        help=(
            "Run GT-bbox cropped OCR, cropped OCR with border, whole-image OCR, "
            "PSM 11 confidence-filtered OCR, EasyOCR simple mode, EasyOCR "
            "paragraph mode, EasyOCR detection-first mode, PaddleOCR simple "
            "mode, or PaddleOCR detection-first mode."
        ),
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
    parser.add_argument(
        "--crop-border-tesseract-config",
        default="--psm 8",
        help="Config used for cropped text regions after adding a border.",
    )
    parser.add_argument(
        "--crop-border-pixels",
        type=int,
        default=20,
        help="White border size, in pixels, added around resized crops.",
    )
    parser.add_argument(
        "--crop-border-color",
        default="white",
        help="Border color added around resized crops.",
    )
    parser.add_argument(
        "--confidence-tesseract-config",
        default="--psm 11",
        help="Config used for confidence-filtered OCR.",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=60.0,
        help="Minimum Tesseract confidence score kept in confidence-filtered OCR.",
    )
    parser.add_argument(
        "--easyocr-langs",
        default="en",
        help="Comma-separated EasyOCR language codes, e.g. `en` or `en,fr`.",
    )
    parser.add_argument(
        "--easyocr-gpu",
        action="store_true",
        help="Use GPU for EasyOCR if a CUDA-enabled torch build is available.",
    )
    parser.add_argument(
        "--detection-iou-threshold",
        type=float,
        default=0.5,
        help="Minimum IoU for a detected box (EasyOCR or PaddleOCR) to count as a GT match.",
    )
    parser.add_argument(
        "--paddleocr-lang",
        default="en",
        help="PaddleOCR language code, e.g. `en` or `ch`.",
    )
    parser.add_argument(
        "--paddleocr-gpu",
        action="store_true",
        help="Use GPU for PaddleOCR if a CUDA-enabled paddlepaddle build is available.",
    )

    args = parser.parse_args()
    mode = MODE_WHOLE_IMAGE if args.whole_image else args.mode
    if args.output_dir is not None:
        output_dir = args.output_dir
    elif mode == MODE_WHOLE_IMAGE:
        output_dir = defaults["whole_image_output_dir"]
    elif mode == MODE_PSM11_CONFIDENCE:
        output_dir = defaults["psm11_confidence_output_dir"]
    elif mode == MODE_CROPPED_BORDER:
        output_dir = defaults["cropped_border_output_dir"]
    elif mode == MODE_EASYOCR_SIMPLE:
        output_dir = defaults["easyocr_simple_output_dir"]
    elif mode == MODE_EASYOCR_PARAGRAPH:
        output_dir = defaults["easyocr_paragraph_output_dir"]
    elif mode == MODE_EASYOCR_DETECTION:
        output_dir = defaults["easyocr_detection_output_dir"]
    elif mode == MODE_PADDLEOCR_SIMPLE:
        output_dir = defaults["paddleocr_simple_output_dir"]
    elif mode == MODE_PADDLEOCR_DETECTION:
        output_dir = defaults["paddleocr_detection_output_dir"]
    else:
        output_dir = defaults["cropped_output_dir"]

    easyocr_languages = tuple(
        lang.strip() for lang in args.easyocr_langs.split(",") if lang.strip()
    ) or ("en",)

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
        crop_border_tesseract_config=args.crop_border_tesseract_config,
        confidence_tesseract_config=args.confidence_tesseract_config,
        confidence_threshold=args.confidence_threshold,
        crop_padding=args.crop_padding,
        crop_scale=args.crop_scale,
        min_crop_height=args.min_crop_height,
        crop_border_pixels=args.crop_border_pixels,
        crop_border_color=args.crop_border_color,
        easyocr_languages=easyocr_languages,
        easyocr_gpu=args.easyocr_gpu,
        paddleocr_lang=args.paddleocr_lang,
        paddleocr_gpu=args.paddleocr_gpu,
        detection_iou_threshold=args.detection_iou_threshold,
        run_started_at=current_timestamp(),
    )
