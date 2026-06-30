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
