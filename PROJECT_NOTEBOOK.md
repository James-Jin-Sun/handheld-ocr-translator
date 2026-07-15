# Project Notebook

Use this file to track what was done, what results were observed, and what should happen next.

## 2026-06-30

### Work Done

- Built a Tesseract + `pytesseract` OCR evaluator for the first 50 ICDAR2013 test images.
- Added multiple OCR modes: whole image, GT-bbox crops, PSM 11 confidence filtering, and GT-bbox crops with border.
- Refactored the evaluator into separate modules for config, dataset loading, GT parsing, OCR, metrics, and result saving.
- Saved each method's results into separate output folders with JSON/CSV metrics and per-image predictions.
- Added test config and timing metadata to each `summary.json`.

### Results

- Best current method: `gt_bbox_crops` with crop resize and `--psm 8`.
- `gt_bbox_crops` on 50 images:
  - CER: `0.1800`
  - WER: `0.5103`
  - Average OCR runtime per image: `4.09s`
  - Wall-clock test time: `204.79s`
- `gt_bbox_crops_border` on 50 images with white border and `--psm 7`:
  - CER: `0.3446`
  - WER: `0.6188`
  - Average OCR runtime per image: `3.78s`
  - Wall-clock test time: `189.51s`
- `psm11_confidence` on 50 images with confidence threshold `40.0`:
  - CER: `0.8399`
  - WER: `1.6569`
  - Average OCR runtime per image: `0.81s`
  - Wall-clock test time: `40.63s`
- Conclusion: bbox cropping gives the strongest accuracy so far; adding a border and using PSM 11 confidence filtering did not beat the crop-only baseline.

### Notes

- Current best crop settings: `crop_scale = 3.0`, `min_crop_height = 48`, `crop_tesseract_config = --psm 8`.
- Confidence filtering is implemented through `pytesseract.image_to_data(...)`, but the first test was less accurate.
- Bordered crop mode is useful for comparison, but did not improve 50-image accuracy.
- Use `--mode gt_bbox_crops` as the current baseline.

### Next Steps

- Try preprocessing on cropped regions: grayscale, contrast enhancement, thresholding, and denoising.
- Compare more crop OCR settings, especially `--psm 7`, `--psm 8`, and `--psm 13`.
- Add a simple comparison script that reads all `summary.json` files and prints method rankings.
- Consider testing a stronger OCR model if Tesseract remains weak on scene text.

## 2026-07-14

### Work Done

- Added EasyOCR as a second OCR engine alongside Tesseract, reusing the same evaluation pipeline (CER/WER/runtime).
- Added `easyocr_simple` mode (word/line-level `readtext`) and `easyocr_paragraph` mode (`readtext(paragraph=True)`), each saved to its own output folder with `per_region_results.*`.
- Added `easyocr_detection` mode that runs EasyOCR's own text detector (`reader.detect`) first, matches detected boxes to GT boxes by IoU, and reports detection precision/recall/F1/mean IoU in `summary.json` and `per_detection_results.*`.
- Optimized `easyocr_detection` to recognize all detected boxes in one batched `reader.recognize()` call instead of re-running detection+recognition per crop (~5x faster per image).
- Installed `easyocr`, `torch`, `torchvision`, and `opencv-python-headless` into `.venv` (re-installed `pytesseract`, which had gone missing from the venv).

### Results

- All three EasyOCR modes run on the same first 50 ICDAR2013 test images, CPU only (`--easyocr-gpu` not set):
- `easyocr_simple`:
  - CER: `0.3030`
  - WER: `0.6745`
  - Average OCR runtime per image: `15.36s`
  - Wall-clock test time: `779.66s`
- `easyocr_paragraph`:
  - CER: `0.2845`
  - WER: `0.6628`
  - Average OCR runtime per image: `14.23s`
  - Wall-clock test time: `720.15s`
- `easyocr_detection` (IoU threshold `0.5`):
  - CER: `0.3017`
  - WER: `0.6833`
  - Average OCR runtime per image: `16.07s`
  - Wall-clock test time: `811.31s`
  - Detection precision: `0.6748`, recall: `0.4868`, F1: `0.5656`, mean IoU (matched boxes): `0.6481`
- Comparison to the current best Tesseract method (`gt_bbox_crops`, CER `0.1800` / WER `0.5103` / `4.09s` per image): EasyOCR is noticeably less accurate and ~4x slower per image on this dataset (small, low-res, distorted scene-text crops), even though it does its own detection instead of relying on GT boxes.
- EasyOCR's own detector recovers well under half of the GT boxes at IoU ≥ 0.5 (recall `0.49`), which explains a large part of the CER/WER gap versus Tesseract-on-GT-crops.

### Notes

- `gt_bbox_crops` (Tesseract + GT boxes) is still the strongest and fastest method overall.
- EasyOCR's `paragraph=True` mode slightly outperforms plain `readtext`, likely because merging boxes into lines reduces fragmented/duplicate word predictions.
- EasyOCR detection recall is the main bottleneck for `easyocr_detection`; missed boxes contribute directly to WER since that text is never recognized.
- All EasyOCR runs use `easyocr_languages=("en",)` and default CRAFT detector thresholds; no GPU was available in this environment.

### Next Steps

- Try EasyOCR with adjusted `detect()` thresholds (`text_threshold`, `low_text`, `link_threshold`) to see if recall improves.
- Try upscaling/denoising images before EasyOCR detection, similar to what helped the Tesseract crop pipeline.
- Add a comparison script/table across all `summary.json` files (Tesseract + EasyOCR) for a single ranked view.
- Consider testing EasyOCR with GPU (`--easyocr-gpu`) if a CUDA machine becomes available, since CPU runtime is the main practical downside today.

## Daily Entry Template

### YYYY-MM-DD

#### Work Done

- 

#### Results

- 

#### Notes

- 

#### Next Steps

- 
