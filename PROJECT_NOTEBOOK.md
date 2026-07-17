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

## 2026-07-16

### Work Done

- Added PaddleOCR as a third OCR engine, using the modern PaddleOCR 3.x module API (`PaddleOCR`, `TextDetection`, `TextRecognition`).
- Added `paddleocr_simple` mode (full PP-OCRv6 detect+recognize pipeline via `PaddleOCR().predict()`), saved to `ocr_results_paddleocr_simple/`.
- Added `paddleocr_detection` mode: runs PaddleOCR's own `TextDetection` detector first, matches detected boxes to GT boxes by IoU (same matcher used for EasyOCR), then recognizes all detected crops in one batched `TextRecognition().predict()` call; saved to `ocr_results_paddleocr_detection/` with `detection_summary` in `summary.json`.
- Refactored `polygon_to_bbox` out of `easyocr_backend.py` into `metrics.py` so the new `paddleocr_backend.py` doesn't need to import (and therefore install) EasyOCR/torch.
- Installed `paddleocr` + `paddlepaddle` into `.venv`; hit a known PaddlePaddle 3.3.1 + oneDNN CPU bug (`ConvertPirAttribute2RuntimeAttribute not support`) and fixed it by pinning `paddlepaddle==3.2.2`.

### Results

- All results on the same first 50 ICDAR2013 test images, CPU only:
- `paddleocr_simple`:
  - CER: `0.2474`
  - WER: `0.4487`
  - Average OCR runtime per image: `54.14s` (see caveat below)
  - Wall-clock test time: `2717.55s`
- `paddleocr_detection` (IoU threshold `0.5`):
  - CER: `0.6979`
  - WER: `0.8886`
  - Average OCR runtime per image: `36.02s` (see caveat below)
  - Wall-clock test time: `1938.27s`
  - Detection precision: `0.4720`, recall: `0.2962`, F1: `0.3640`, mean IoU (matched boxes): `0.6693`
- Method comparison so far (same 50 images):

| Method | CER | WER |
|---|---|---|
| `gt_bbox_crops` (Tesseract, best) | 0.1800 | 0.5103 |
| `paddleocr_simple` | 0.2474 | **0.4487** |
| `easyocr_paragraph` | 0.2845 | 0.6628 |
| `easyocr_detection` | 0.3017 | 0.6833 |
| `easyocr_simple` | 0.3030 | 0.6745 |
| `paddleocr_detection` | 0.6979 | 0.8886 |

- `paddleocr_simple` has the best WER of any method tried so far (even beating Tesseract's `gt_bbox_crops`), and is clearly the strongest of the three "detect on raw image, no GT boxes" methods (EasyOCR + PaddleOCR).

### Notes

- **Runtime caveat**: both 50-image PaddleOCR runs hit heavy system memory/swap pressure partway through (per-image runtime varied wildly, from ~5s up to 600+s on the same run); the reported average runtimes are not a fair speed comparison and should be re-measured on a less loaded machine before drawing conclusions about PaddleOCR speed.
- PaddleOCR's standalone `TextDetection` module recall (`0.30`) is notably lower than EasyOCR's own detector recall (`0.49`) on this dataset, causing `paddleocr_detection`'s CER/WER to be much worse than `paddleocr_simple`'s full pipeline — the standalone detector's default thresholds appear to miss more small/word-level GT boxes than the full pipeline's detector settings.
- `paddleocr_simple`'s full pipeline (detection + recognition together, PP-OCRv6 medium models) is the most accurate learned-OCR method tested so far.
- All PaddleOCR runs use `paddleocr_lang="en"`, PP-OCRv6 medium det/rec models (auto-downloaded to `~/.paddlex/official_models/`), CPU only, `paddlepaddle==3.2.2` (pinned due to the oneDNN bug above).

### Next Steps

- Re-run PaddleOCR timing on an unloaded machine to get trustworthy per-image runtime numbers.
- Tune `TextDetection` parameters (`thresh`, `box_thresh`, `unclip_ratio`) to try to close the recall gap vs. EasyOCR's detector.
- Add a single comparison script/table that reads all `summary.json` files (Tesseract + EasyOCR + PaddleOCR) and prints a ranked view.
- Consider GPU for both EasyOCR and PaddleOCR if a CUDA machine becomes available, since CPU runtime/memory cost is the main practical downside for both so far.

## 2026-07-17

### Work Done

- Restructured `laptop_mvp/` into an MVP-shaped layout: `src/ocr/` (all existing Tesseract/EasyOCR/PaddleOCR eval code, renamed entry point `main.py` -> `evaluate.py` to avoid clashing with the new app entry point), `src/translation/`, `src/overlay/`, and top-level `src/main.py`.
- Added `src/translation/google_translate.py`: a Google Cloud Translation API - **Advanced (v3)** wrapper (`translate_text`, `translate_batch`) using the built-in `general/nmt` model.
- Added `src/overlay/draw_translation.py`: blurs each detected text region and draws the translated text on top, with auto-shrinking font to fit the box.
- Added `src/ocr/text_cleaning.py` (strip OCR symbol noise, collapse repeated punctuation) and a `group_tokens_into_lines` helper that turns Tesseract's per-word confidence-filtered tokens into line-level regions for translation/overlay.
- Wired it all together in `src/main.py`: OCR (PSM 11 + confidence filter) -> clean -> translate (batched) -> blur & overlay -> save, as a single-image CLI (`python main.py --image ... --target-lang ...`).
- Switched translation auth from a service-account key file to **OAuth Application Default Credentials** (`gcloud auth application-default login`, project `handheld-ocr-translator`) — removed `laptop_mvp/keys/` entirely since v3 Advanced + ADC needs no key file.
- Set default target language to simplified Chinese (`zh-CN`) in both `google_translate.py` and `src/main.py`.
- Added standalone tests: `src/translation/test_translation.py` (translates a sample sentence, saves JSON to `src/translation/test_output/`) and `src/overlay/test_draw_translation.py` (blurs+overlays hand-picked regions on `img_1.jpg`, saves to `src/overlay/test_output/`).
- Fixed CJK font rendering in `draw_translation.py` — Arial has no Chinese glyphs, so `_load_font` now tries `msyh.ttc` / `simhei.ttf` before falling back to Arial.
- Connected all three modules in `src/main.py`: swapped the OCR step from Tesseract PSM 11 to **PaddleOCR simple mode** (`ocr_paddleocr_simple`), which already returns per-line bboxes+text, so the Tesseract-specific word->line grouping step is no longer needed there. Pipeline is now PaddleOCR -> clean -> translate (batched) -> blur & overlay -> save, with results written to `src/pipeline_results/<image_stem>/` (translated image + a `<stem>_regions.json` manifest of detected text, confidence, and translation per region).
- Fixed the word-by-word/line-by-line translation issue: added `group_lines_into_blocks` to `text_cleaning.py`, which merges vertically stacked, horizontally overlapping OCR lines into sentence blocks (vertical gap < 0.7x line height, x-overlap >= 30% of the narrower box) before translation. `main.py` now translates whole sentence blocks and overlays each block's union bbox; the manifest keeps both the merged blocks and their source lines.
- Improved the overlay layout: added `split_text_across_lines` to `draw_translation.py`, which splits each block's translated sentence back across the block's original lines, proportionally to each line's source text length (cut points snap to spaces for word-based target languages, character boundaries for CJK). Each segment is drawn on its own line bbox instead of one auto-shrunk line across the block's union box; the manifest now records a `translated_segment` per line.

### Results

- Restructure verified: re-ran `evaluate.py --mode gt_bbox_crops --limit 50` after the move, CER `0.1800` / WER `0.5103` (matches the pre-move baseline).
- Translation module test: `"Tiredness kills A short break could save your life"` -> `"疲劳会致命。短暂休息或许能救你一命。"` (model `general/nmt`, target `zh-CN`), saved to `src/translation/test_output/translation_result.json`.
- Overlay module test: 3 hand-picked regions on `img_1.jpg` blurred and overlaid with Chinese text, saved to `src/overlay/test_output/img_1_translated.jpg` — text renders correctly after the CJK font fix.
- Full connected pipeline on `img_1.jpg` (`python main.py --image img_1.jpg`): PaddleOCR detected 5 clean lines — `Tiredness`, `kills`, `A short break`, `could save`, `your life` (all confidence > 0.88, most > 0.99) — each translated and overlaid correctly. Saved to `src/pipeline_results/img_1/`.
- After sentence-block grouping, the same 5 lines merge into 2 blocks and translate with full context: `Tiredness kills` -> `疲劳会致命`, `A short break could save your life` -> `短暂的休息或许能救你一命` (previously `could save` alone came back as "can save (money)" and `your life` as "your (daily) life").
- With per-line layout, the block translations flow back over the original 5 line positions: `疲劳会` / `致命` on the top billboard and `短暂的休息` / `或许能救` / `你一命` on the lower one, matching the source layout much more naturally than one stretched line per block.

### Notes

- Per-line translation loses context vs. translating a full sentence at once — e.g. "A short break could save" translated alone came back closer to "...could save (money)" rather than "...could save (your life)". Fixed the same day via sentence-block grouping (see Work Done above).
- Kept the internal import style consistent with the rest of the project (flat `from module import x`, no package `__init__.py`s); `src/main.py` adds each `src/*` subfolder to `sys.path` itself rather than using relative package imports.

### Next Steps

- Try the pipeline on more/other images (multi-column layouts, side-by-side signs) to stress-test the block-grouping heuristics (`max_gap_factor`, `min_horizontal_overlap`).
- The proportional split is length-based, not meaning-based — segments like `或许能救` / `你一命` can break mid-phrase. If this matters, a smarter split (e.g. on Chinese punctuation/word boundaries via jieba) could improve it.

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
