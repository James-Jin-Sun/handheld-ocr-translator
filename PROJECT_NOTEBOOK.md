# Project Notebook

Use this file to track what was done, what results were observed, and what should happen next.

## 2026-06-30

### Work Done

- Created the initial OCR evaluation pipeline for the ICDAR2013 first 50 test images.
- Added Tesseract + `pytesseract` OCR support.
- Installed Python dependencies in the project virtual environment:
  - `pillow`
  - `pytesseract`
- Installed the Tesseract OCR executable:
  - `C:\Program Files\Tesseract-OCR\tesseract.exe`
- Added whole-image OCR evaluation.
- Added GT-bbox cropped OCR evaluation to mimic text detection before OCR:
  - Uses bbox data from `Icdar2013\Challenge2_Test_Task1_GT (1)`.
  - Crops each text region.
  - Upscales crops before OCR.
  - Runs Tesseract on each crop.
  - Combines crop OCR results into an image-level prediction.
- Refactored `laptop_mvp/main.py` into smaller modules:
  - `config.py`
  - `dataset.py`
  - `ground_truth.py`
  - `metrics.py`
  - `ocr.py`
  - `results.py`
- Added mode-specific result folders:
  - `laptop_mvp/ocr_results_whole_image`
  - `laptop_mvp/ocr_results_cropped`
- Updated summaries to include:
  - Test mode
  - Test config
  - Start and finish timestamps
  - Wall-clock test time
  - OCR runtime

### Results

- Whole-image OCR performed poorly because Tesseract tried to read the entire natural scene image at once.
- GT-bbox cropped OCR improved results significantly by isolating text regions before OCR.
- For the first 50 cropped OCR run, observed summary:
  - CER: about `0.1800`
  - WER: about `0.5103`
  - Average OCR runtime per image: about `4.15s`
  - Total OCR runtime: about `207.38s`
- One-image whole-image smoke test:
  - CER: `0.5000`
  - WER: `0.8889`
  - Runtime: about `0.85s`
- One-image cropped smoke test:
  - CER: `0.2800`
  - WER: `0.5556`
  - Runtime: about `6.74s`

### Notes

- Current cropped OCR upscales each crop using:
  - `crop_scale = 3.0`
  - `min_crop_height = 48`
- Current code does not use confidence filtering.
- Confidence filtering would require switching from `pytesseract.image_to_string(...)` to `pytesseract.image_to_data(...)`.
- `--mode whole_image` can be used to rerun the original whole-image test.
- `--mode gt_bbox_crops` can be used to rerun cropped OCR.

### Next Steps

- Add confidence filtering with `pytesseract.image_to_data(...)`.
- Experiment with crop preprocessing:
  - grayscale
  - thresholding
  - contrast enhancement
  - denoising
- Compare Tesseract page segmentation modes:
  - `--psm 6`
  - `--psm 7`
  - `--psm 8`
  - `--psm 13`
- Add a table or script to compare whole-image vs cropped OCR metrics across the same image set.
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
