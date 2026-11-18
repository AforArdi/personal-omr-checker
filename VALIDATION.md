# Implementation and Validation Report

## Delivery Status

- **Key Catalog**: **67 / 67 exams (6,700 / 6,700 question entries) are 100% source-verified**.
  - 50 Practice Book exams verified against high-resolution printed source photos (`model-ans-pic-[1..11].jpg`).
  - 17 Retina exams verified against high-resolution source photos (`*-1.jpg` and `*-2.jpg`).
  - Multi-answer entries verified (e.g. `practice-paper-final-02-biology-1st-paper` Q74 = `[B, C]`, `practice-paper-final-02-physics-2nd-paper` Q94 = `[B, D]`, `practice-model-test-26` Q60 = `[A, B]`, Q93 = `[B, D]`).
  - Validation check (`python -m omr_check validate-keys`): **67 exams; 67 verified; 0 incomplete**.
- **Core & Integration Test Suite**: **65 passed, 0 failed, 0 skipped** (`python -u -m pytest -q`, 159.43 seconds, 2026-11-18).
  - `test_scoring.py`: Exact Decimal arithmetic, +1 correct, -0.25 wrong/multiple/invalid, 0 blank, negative scores, multi-choice key matching, explicit label result reporting (`Score:`, `Correct:`, `Wrong answers:`, `Unanswered:`, `Multiple-marked:`, `Invalid-marked:`), formatted question-number lists (`Q2`, `none`), and multi-accepted answer comparisons (`Q2: A → B or C`).
  - `test_catalog.py`: Database schema validation, case/punctuation-insensitive lookup, ambiguous name detection, exact displayed label matching (`Paper Final English [Practice book]`), alias matching, collection disambiguation, and keyword search across IDs, names, collections, and aliases.
  - `test_recognition.py`: SIFT grid alignment, structural alignment, EXIF correction, blank rejection, ink measurement, repeatability, and the 100-question Canva regression fixture (`test_canva_30marked_regression`) verifying 30 single fills (including Q12, Q13, Q14, Q19), 70 blanks, and 0 uncertain/review rows.
  - `test_review.py`: Local key review web interface, authentication token, atomic saves, revision verification.
  - `test_bot_flow.py`: Complete Telegram flow (`upload -> preview -> correction (/fix) -> confirmation -> result`), stale preview protection, uncertain mark blocking, cancellation, concise `/exam` help, displayed label selection, paginated `/exams` search with inline buttons, deterministic short callback selection (`sel:eXX`), invalid caption rejection without silent fallback, and session `exam_id` immutability when a new exam is selected.
- **Python Compilation**: All application and tooling modules compile cleanly with zero errors.

## Alignment & Recognition Benchmark Results

Measured with `python -m tools.benchmark_alignment --phase verified`:

| Layout | Case | Accepted | Method | Circle Coverage | Confident Errors | Uncertain Rows | Notes |
|---|---|---|---|---|---|---|---|
| Retina | original | True | column_frames | 0.9925 | 0 | [87, 91] | Real camera photo |
| Retina | crop-jpeg | True | registration_marks | 0.9675 | 0 | [17] | Synthetic crop & JPEG compression |
| Retina | crop-640 | True | registration_marks | 0.9500 | 0 | [40] | 640px downscale |
| Retina | rotated | True | column_frames | 0.9375 | 0 | [70, 75] | 90° clockwise rotation |
| Retina | perspective | True | registration_marks | 0.9425 | 0 | [] | Perspective transform |
| Retina | incomplete-grid | False | N/A | N/A | 0 | N/A | Safely rejected with clear error |
| Practice Book | original | True | column_frames | 0.9975 | 0 | [] | Real camera photo (Q1-3 marked, 97 blank) |
| Practice Book | crop-jpeg | True | column_frames | 0.9975 | 0 | [] | Synthetic crop & JPEG compression |
| Practice Book | crop-640 | True | column_frames | 1.0000 | 0 | [] | 640px downscale |
| Practice Book | rotated | True | column_frames | 1.0000 | 0 | [] | 90° clockwise rotation |
| Practice Book | perspective | True | column_frames | 1.0000 | 0 | [] | 100% circle coverage |
| Practice Book | incomplete-grid | False | N/A | N/A | 0 | N/A | Safely rejected with clear error |

### Canva Solid Fills Regression Fixture (`answer-omr-1 (1).png`)
- **Dimensions**: 1081 × 927 PNG.
- **Marks**: 30 Canva solid circular marks (Q1–Q30), 70 blanks (Q31–Q100).
- **Ground Truth**:
  - Q1–Q5: A, A, C, D, A
  - Q6–Q10: B, B, D, A, A
  - Q11–Q15: B, A, D, D, C
  - Q16–Q20: D, C, C, A, A
  - Q21–Q25: B, D, B, C, A
  - Q26–Q30: C, B, C, B, A
  - Q31–Q100: Blank
- **Initial Issue**: Q12, Q13, Q14, and Q19 were falsely flagged as `REVIEW` (uncertain).
- **Root Cause**: In `omr_check/alignment.py`, `locate_rows` for `practice-book` applied a hardcoded active threshold `profile > 0.36`. In this fixture, Option A on Row 25 had a solid black fill covering printed red form ink, lowering the red print peak profile on Row 25 to 0.352. Because 0.352 < 0.36, Row 25 was omitted from candidate peaks. `locate_rows` requires `count - 1 in present` (Row 24), causing Column 0 row localization to fail and falling back to SIFT global homography. The SIFT homography had 5–15px vertical sag on Column 0 rows 11–20 and sampled at static template coordinates, causing sampling disks to miss half the bubble on Q12, Q13, Q14, Q19 (measured strength ~0.50–0.74, landing in faint threshold -> REVIEW).
- **Fix**: Replaced hardcoded `0.36` with adaptive percentile contrast detection:
  `low, high = np.percentile(profile[35:895], [15, 85])` with `if high - low < 0.15: return None` and `active = profile > min(0.28, (low + high) * 0.40)`.
- **Outcome**: All 4 columns locate all 25 rows (`validated_rows_per_column: [25, 25, 25, 25]`, circle coverage 1.0). Dynamic sampling centers center exactly on every bubble.
  - Q12: single fill A (strength 1.000, 0 faint)
  - Q13: single fill D (strength 0.999, 0 faint)
  - Q14: single fill D (strength 1.000, 0 faint)
  - Q19: single fill A (strength 0.999, 0 faint)
  - Total: **30 correct single fills, 70 blanks, 0 uncertain rows**.

## Exam Search and Selection Improvements

1. **Exact Displayed Label Indexing**: `Catalog` indexes `f"{exam.name} [{exam.collection}]"`, `f"{exam.id}: {exam.name} [{exam.collection}]"`, `exam.id`, `exam.name`, and all collection-qualified aliases. Copying the exact displayed label from `/exams` into `/exam` or an image caption resolves the exact target exam unambiguously.
2. **Ambiguity Protection**: When an exam name exists in multiple collections (e.g. `Model Test-01`), the resolver prompts the user with inline selection buttons for each collection-specific exam.
3. **Keyword Search**: `/exams` supports keyword queries (e.g. `/exams english practice`) across exam IDs, names, collections, and aliases.
4. **Pagination**: `/exams` results are paginated (5 exams/page) with inline `[Select: ...]` buttons and `« Prev`, `page/total`, `Next »` navigation controls.
5. **Concise `/exam` Help**: Typing `/exam` without arguments outputs clear usage help and examples.
6. **Unified Resolver with Caption Strictness**: Image captions use the same resolver. If a user provides an invalid or ambiguous caption, the bot rejects it with suggestions; it never silently falls back to a previously selected exam.
7. **Session Immutability**: Selecting or searching an exam with `/exam` or `/exams` never alters or discards the `exam_id` of an active in-review reading session.
8. **Callback Safety**: Selection callbacks use deterministic short tokens (`sel:eXX`) bounded to ~7 bytes, and pagination callbacks (`page:X:hash`) are bounded to ~16 bytes, well below Telegram's 64-byte payload limit.

## Clear Result Reporting

Results format output using unambiguous, non-overlapping categories:
```
Score: 28.75 / 100
Correct: 29
Wrong answers: 1
Unanswered: 70
Multiple-marked: 0
Invalid-marked: 0

Wrong question numbers: Q2
Unanswered question numbers: Q31, Q32, ...
Multiple-marked question numbers: none
Invalid-marked question numbers: none

Your answer → accepted answer:
Q2: A → B
```
- Counts and lists are strictly mutually exclusive across correct, wrong, unanswered, multiple, and invalid.
- Alternative accepted answers in answer keys are explicitly presented (e.g. `B or C`).
- Scoring adheres strictly to: +1 correct, -0.25 wrong, -0.25 multiple, -0.25 invalid, 0 unanswered.
- Grading cannot proceed if any row has unresolved REVIEW status.

## Reflective black-pen photograph regression (2026-11-18)

- Required fixture: `tests/fixtures/practice_pen_glare.jpg`; all 100 choices were
  manually transcribed independently of any exam key in
  `tests/fixtures/practice_pen_glare_expected.json` (90 filled, 10 blank).
- The previous pipeline aligned the full grid with 100% circle support but returned
  19 REVIEW rows and incorrectly called the filled Q58 and Q83 blank. Their
  global-red ink strengths were only 0.095 and 0.129. This was a photometric
  failure on glossy ink, rather than missing rows.
- Measurement now estimates nearby paper from an outer annulus and requires both
  mean-channel and red-channel contrast. A small median filter suppresses isolated
  reflections. Reference-print subtraction and the 0.72 dense-fill threshold are
  preserved. Only strong local evidence supplements the original measurement;
  the original partial-mark signal cannot be erased by this step.
- The original photo, JPEG quality 75 at width 720, and 90-degree rotation each
  read all 100 choices exactly: 90 singles, 10 blanks, zero REVIEW and zero errors.
- The full suite passed all 65 tests. The independent alignment benchmark
  (`python -m tools.benchmark_alignment --phase pen-local-review`) accepted all
  10 complete-grid cases with zero confident errors and rejected both incomplete
  grids. Practice had zero REVIEW rows in every case. Retina retained its existing
  review rows except the rotated case, where Q70 was correctly recovered.
- `tests/test_ink_measurement.py` checks empty cells, ticks, crosses, half fills,
  sparse dark-red printing, and double fills on both templates. These examples
  are regression coverage, not a guarantee for every possible handwritten shape.
- Scoring was independently checked: 19 scoring tests passed. The total remains
  `correct - 0.25 * (wrong + multiple + invalid)`, equivalent to
  `100 - 1.25 * (wrong + multiple + invalid) - blank`; the lost correct-answer
  point must not be subtracted again when summing from zero.

## Remaining Limitations & Operational Notes

1. **Lightly Shaded Bubbles**: Faint pencil or partial shading under low contrast continues to trigger the UNCERTAIN review state. This safeguard prevents automatic scoring errors and requires user resolution via `/fix`.
2. **Distinction Between Real Photos and Synthetic Transforms**: The test suite validates real camera photographs (`20261115_191044.jpg`, `20261115_191159.jpg`), synthetic crops, rotations, downscaling, and solid-circle graphics (`answer-omr-1 (1).png`). Real smartphone captures can exhibit varying lighting, shadows, and perspective skew that synthetic tests do not fully simulate.
3. **Black Pen Requirement**: Students must fill bubbles solidly with black ink. Incomplete grids and non-OMR images are rejected.
4. **Local Data Only**: All changes are tested locally. No git push, deployment, or Railway configuration changes have been executed.
