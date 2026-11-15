# Antigravity continuation: OMR Check

**Latest checkpoint:** 28 core tests pass; 4 catalog tests pass after the last catalog edit; the HTTP integration test is skipped due to sandbox loopback restriction (WinError 10013). Extraction has finished: 6,048/6,700 candidate slots, 652 unresolved, 16 complete candidate keys, and 1 source-verified key. Practice sample is exact; Retina has 14 uncertain rows and no confident mismatch on the supplied visual ground truth. Read VALIDATION.md.

You are continuing an existing implementation in C:\projects\omr-check-work. Inspect the existing files before editing. Finish the system; do not restart it or replace it with an AI chatbot.

## User's accepted requirements

- Python Telegram bot, running locally on Windows first and on a VPS later.
- Detect either supported OMR layout automatically, independently of the supplied exam key. The image's printed title must not choose the exam.
- User supplies an exam name with the image (caption or prior /exam selection). Match capitalization-insensitively. Normalize punctuation and whitespace. Never guess ambiguous names; several names repeat across the two collections.
- Recognize only the 100-question answer grid. Roll/name/registration sections do not affect marking.
- Black pen, fully shaded bubbles only. A tick/cross or multiple filled bubbles is invalid/wrong. Unanswered earns zero.
- Correct +1; wrong/multiple/invalid -0.25 earned marks; blank 0. Equivalently: 100 - 1.25*(wrong+multiple+invalid) - blanks. Do not subtract the lost mark twice. Preserve negative scores.
- A printed key entry such as BC means either B OR C is accepted. Both shaded together on an OMR are still wrong.
- Show an annotated reading preview, allow corrections of misread marks, and require confirmation before grading. Uncertain recognition must block scoring, not be silently treated as blank or wrong.
- Result must include score and question numbers for wrong, blank, multiple, and invalid marks, with selected vs accepted answers.
- Reliability matters more than appearing finished. Never promise zero errors or silently guess missing key entries.

## Existing code

- omr_check/domain.py: mark models, validation, exact Decimal scoring.
- catalog.py: database schema validation, normalization, exact/ambiguous lookup.
- recognition.py: EXIF correction; SIFT grid alignment; coverage checks; deterministic BF matching; bounded local correction for curved Retina pages; template-specific ink measurements; annotations.
- sessions.py: owner-scoped sessions, expiry, correction parsing/history, revision handling.
- bot.py: /start /exams /exam /fix /confirm /cancel /whoami, image-caption selection, preview and final result. No bot token has been supplied.
- review.py: local answer-key review server with source crops, correction, verification, atomic revision-checked saves.
- cli.py and run.ps1: local entry points.
- assets/: normalized blank references and the 400 bubble centers for each layout.
- data/source_layouts.json: manually identified practice-book exam heading spans.
- data/manual_verified_keys.json: first practice-book exam manually transcribed and checked (Paper Final-01 Biology 1st Paper). Preserve checked data.
- data/answer_keys.json: generated catalog, including draft/unresolved entries. Read current coverage from it; do not assume it is complete.
- data/sample_expected.json: manually read ground truth for every row in the two completed sample photos.
- tools/extract_keys.py: conservative OCR extraction with explicit printed-number anchors, cell/column preprocessing, and question sequence checks.
- tools/recover_practice.py: additional grid-based draft recovery pass.
- tools/build_catalog.py: merges original, recovery, and v2 extraction, preserves manually reviewed keys, and generates catalog.
- tools/check_samples.py: prints all deviations from the sample ground truth.
- tests/: scoring, catalog, correction, real-photo and synthetic OMR tests.
- README.md, Dockerfile, requirements.txt, pyproject.toml, .env.example already exist.

## Source folders and inventory

- omr-check-answer-sheet-images/: 48 photos, consisting of 11 practice-book key pages, 34 Retina key photos for 17 exams, 2 blank OMR reference forms, and one black separator photo.
- The practice-book pages contain 50 distinct exams (14 paper finals, 5 subject finals, 31 model tests), with overlapping exams across photographs. They are not 11 exams.
- Total catalog: 67 exams, requiring 6,700 accepted-answer entries.
- omr-exam-paper-example/20261115_191044.jpg: completed Retina sample; visual reading is 72 single fills and 28 blanks. Ground truth lives in data/sample_expected.json.
- omr-exam-paper-example/20261115_191159.jpg: practice-book sample; Q1=A, Q2=A, Q3=C, remaining 97 blank.
- Read EXIF orientation before cropping. Many files store sideways pixels with EXIF orientation 6.
- Filename halves can be reversed and are not necessarily 50/50. Example: model-test-two-1.jpg is questions 47–100, and -2 is 1–46. Always use printed numbers.

## Runtime already prepared

Project-local interpreter: .venv\Scripts\python.exe (Python 3.11). Use it; python/py are not correctly registered on PATH here. The installed source interpreter is C:\Users\User\AppData\Local\Programs\Python\Python311\python.exe.

Tesseract exists at C:\Program Files\Tesseract-OCR\tesseract.exe. Its Python wrapper and the project dependencies are installed in .venv. OCR scripts set OMP_THREAD_LIMIT=1 to avoid excess CPU use. OpenCV imports/process startup can be slow on this laptop.

.runtime/ contains disposable downloaded wheels, abandoned embedded-Python setup, and inspection images. Do not package it, .venv, .env, or var/session photos.

## Exact next steps

1. Read VALIDATION.md for the latest test and extraction results. Run the tests if new changes or unresolved failures justify it. The latest core suite passed 28 tests after the stabilization below. The local HTTP integration test is separate and currently skipped because of environment restrictions. The current stabilization switched approximate FLANN matching to exact BF matching, seeds OpenCV's RNG per read, restores practice-book threshold 155 and radius factor .78, uses Retina threshold 210 and radius factor .60, and limits local curvature correction to Retina. Check the newest test log before changing anything.
2. Finish recognition validation against ALL 100 rows of both real samples. Distinguish confident wrong readings from safely flagged uncertain rows. Practice-book should identify exactly A,A,C plus 97 blanks. Retina currently needs conservative review for some lightly shaded rows; never lower thresholds just to make tests pass. Test ticks/crosses, double fills, rotation, perspective, blur/cropping and repeated reads where these tests add meaningful coverage. If an uncertainty cannot be resolved safely, keep confirmation/review or require a retake.
3. Finish the answer database. Current OCR is incomplete and unverified except the manual key. First extraction caches are in var/key-extraction; extra reads in var/key-recovered; improved separate-column reads in var/key-extraction-v2. The improved method recovered 570/600 candidates on model-ans-pic-1 and 435 reads on pic-3 (which includes overlap/partial columns), much better than the initial method. A crop outside the image used to crash v2; bounds checks now skip empty crops. Resume with the command below; completed files are skipped. Do not run another writer to the same output folder concurrently.
4. Run build_catalog after extraction/recovery. Every missing answer remains null; every conflicting/low-confidence draft needs source comparison. Do not flip status to verified to bypass the guard. Compare printed question numbers and answer glyphs against the original image; ignore explanations. Fill and verify every exam's 100 answers, preserving source references. You can use the local review screen or edit the JSON carefully. Preserve manual verified keys across regeneration.
5. Inspect duplicate exam-name behavior, stale confirmation protection, settings validation, review saves, and output formatting. Fix real defects, not speculative feature expansion.
6. To test Telegram live, the user must put a BotFather token in .env locally. Never request that they paste it into chat or commit it. Without credentials, perform local service/CLI tests and state live Telegram was not tested.
7. Update README/VALIDATION with exact final counts, tests, limitations and launch commands. Package only source, assets, keys, tests and documentation. Do not publish, deploy, commit, or push without the user's explicit request.

## Useful commands (PowerShell, from project root)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m tools.check_samples
$env:OMP_THREAD_LIMIT='1'
.\.venv\Scripts\python.exe -u -m tools.extract_keys
.\.venv\Scripts\python.exe -u -m tools.recover_practice
.\.venv\Scripts\python.exe -m tools.build_catalog
.\.venv\Scripts\python.exe -m omr_check validate-keys
.\run.ps1 review-keys
.\run.ps1 inspect omr-exam-paper-example\20261115_191159.jpg --output var/practice
.\run.ps1 bot
```

## Known implementation concerns to check

- OCR sequence extrapolation can produce out-of-frame glyph crops. Empty crops are now guarded; inspect any inferred rows rather than treating a sequence fit as proof.
- Source layouts are hand-mapped spans. Check exam assignment at page edges, overlap, and the unequal column widths in pic-2. Do not merge adjacent exams' answers.
- Conflicting OCR records currently retain the higher-confidence candidate and record an issue. That candidate is not necessarily the true answer.
- Some keys, notably Retina Paper Final English, were empty in the first pass because faded column borders prevented cell detection. The latest extractor can infer an adjacent answer-column border from the detected number column, but this still needs source validation.
- Recognition was previously non-repeatable with approximate FLANN indexes. Exact BF matching plus fixed RANSAC seed is the latest fix; verify repeated identical reads.
- Broad core/baseline ink compensation created false review flags on blank practice rows and was reverted. Do not reintroduce it without measured evidence.
- Partial/tick/cross recognition currently routes ambiguous shapes to review; it does not claim universal automatic shape classification.
- bot.py upload failure cleanup has been fixed: a new valid upload invalidates the previous session, and failures remove the new in-memory session and its directory. Verify this through the live Telegram flow when a token is available.
- Local key review was syntax-checked; its HTTP save/revision integration test could not run because loopback sockets are forbidden in this execution sandbox (WinError 10013). Run tests/test_review.py outside that restriction. It binds 127.0.0.1, checks Host and a request token, and serializes saves.

Finish with an honest status: verified keys / 67, resolved entries / 6700, recognition results on both samples, test outcome, whether live Telegram ran, and exactly what remains. Do not describe this as ready for reliable marking while keys or recognition are unresolved.
