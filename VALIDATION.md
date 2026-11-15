# Implementation and Validation Report

## Delivery Status

- **Key Catalog**: **67 / 67 exams (6,700 / 6,700 question entries) are 100% source-verified**.
  - 50 Practice Book exams verified against high-resolution printed source photos (`model-ans-pic-[1..11].jpg`).
  - 17 Retina exams verified against high-resolution source photos (`*-1.jpg` and `*-2.jpg`).
  - Multi-answer entries verified (e.g. `practice-paper-final-02-biology-1st-paper` Q74 = `[B, C]`, `practice-paper-final-02-physics-2nd-paper` Q94 = `[B, D]`, `practice-model-test-26` Q60 = `[A, B]`, Q93 = `[B, D]`).
  - Validation check (`python -m omr_check validate-keys`): **67 exams; 67 verified; 0 incomplete**.
- **Core & Integration Test Suite**: **33 passed** (`python -m pytest -q`).
  - `test_scoring.py`: Exact Decimal arithmetic, +1 correct, -0.25 wrong/multiple/invalid, 0 blank, negative scores, multi-choice key matching.
  - `test_catalog.py`: Database schema validation, case/punctuation-insensitive lookup, ambiguous name detection.
  - `test_recognition.py`: SIFT grid alignment, EXIF correction, blank rejection, ink measurement, repeatability.
  - `test_review.py`: Local key review web interface, authentication token, atomic saves, revision verification.
  - `test_bot_flow.py`: Complete Telegram flow (`upload -> preview -> correction (/fix) -> confirmation -> result`), stale preview protection, uncertain mark blocking, cancellation, and ambiguous exam selection.
- **Python Compilation**: All application and tooling modules compile cleanly with zero errors.

## Real Photo Recognition

Ground truth for all 100 rows of both benchmark photos is stored in `data/sample_expected.json`.

| Sample | Outcome |
|---|---|
| Practice Book photo (`20261115_191159.jpg`) | **0 mismatches**: Exactly Q1=A, Q2=A, Q3=C, and 97 blank answers; 100% agreement with visual reading. |
| Retina photo (`20261115_191044.jpg`) | Layout recognized. 86 rows match visual reading directly; **14 lightly shaded rows safely flagged as UNCERTAIN for user review**. Zero incorrect confident reads. |

The 14 Retina review rows are: 38, 42, 60, 62, 63, 64, 65, 66, 68, 69, 70, 91, 95, and 96.
In accordance with system safeguards, these uncertain rows **block grading** until the user reviews and confirms them via `/fix` (e.g., `/fix 38=A 42=D ...`).

## Verified Telegram Bot Flow

The asynchronous Telegram bot flow (`omr_check/bot.py`) was validated via integration tests:
1. **Upload**: User sends OMR sheet image with exam caption (or chooses exam first with `/exam`). Image EXIF is corrected, layout detected (Practice Book vs Retina), answer grid aligned with SIFT, and answers measured.
2. **Preview**: User receives annotated reading image (`detected-answers.jpg`) showing detected bubbles (green=single, blue=blank, red=multiple/invalid, orange=review) along with a text breakdown and inline action buttons.
3. **Correction (`/fix`)**: User can correct any mark (e.g., `/fix 12=A 27=blank 40=invalid 51=A+B`). This updates the reading session, increments the session revision token, re-annotates the preview, and records an audit log.
4. **Stale Confirmation Guard**: Confirming an outdated preview (e.g., clicking confirm on revision 0 after revision 1 was generated) is safely rejected.
5. **Confirmation & Result**: Confirming a reading without unresolved/uncertain marks computes the exact score according to the agreed rules and outputs the detailed score summary with wrong, unanswered, multiple, and invalid questions.

## Remaining Limitations & Operational Notes

1. **Lightly Shaded Bubbles**: Curved, folded, or very faintly pencil/pen shaded bubbles on Retina sheets trigger the uncertain state. This is an intentional safety feature to prevent misgrading. Users must resolve them using `/fix`.
2. **Black Pen Requirement**: Sheets must be shaded using black pen with fully filled bubbles. Ticks, crosses, or multiple fills are penalized (-0.25) as invalid/multiple marks.
3. **Bot Token & Telegram Privacy**: Live Telegram bot execution requires setting `TELEGRAM_BOT_TOKEN` in `.env`. The bot interacts only in private chats (not public groups) to protect student privacy.
4. **Image Limits**: The bot accepts JPEG/PNG files up to 19 MB. For best alignment, the four outer corner black registration marks and the answer grid should be fully visible without heavy shadows.
