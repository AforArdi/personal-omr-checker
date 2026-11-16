# OMR Check

A Python Telegram bot with two independently detected OMR layouts, source-linked answer keys, a reading-confirmation step, and deterministic scoring.

## Current delivery status

All **67 exam keys (6,700 questions total)** are 100% source-verified from high-resolution printed source photos. The full test suite (45 tests) passes cleanly, including end-to-end Telegram bot flow verification (`upload -> preview -> correction -> confirmation -> result`), paginated exam search, deterministic inline callback selection, and verified recognition across both layouts (`practice-book` and `retina`) and the new Canva solid-fill fixture (30 marked single fills, 70 blanks, 0 uncertain). See `VALIDATION.md` for detailed test metrics, sample recognition outcomes, and remaining limitations. A bot token is not supplied or embedded in this project.

## Run on this Windows laptop

A project-local environment has been created at `.venv`. No global Python packages were changed.

1. Copy `.env.example` to `.env` and put your BotFather token in `TELEGRAM_BOT_TOKEN`.
2. Optionally set `ALLOWED_USER_IDS` to your Telegram user ID. The bot's `/whoami` command returns it. Without this setting the bot accepts any private-chat user.
3. Run `.\run.ps1 bot` from PowerShell. Keep the process and laptop running.
4. Send the bot an original JPEG/PNG **as a file**, with the exact exam name in its caption. Names ignore capitalization and punctuation. Either OMR layout can be used with any exam key.
5. Review the cropped, annotated answer grid and the detected answer list. Use `/fix 12=A 27=blank 40=invalid 51=A+B` to correct a misreading. Confirm the latest preview to grade it.

If PowerShell blocks the script, run `.\.venv\Scripts\python.exe -m omr_check bot` directly. Do not change your machine-wide execution policy.

To recreate the environment on another computer with Python 3.11 or later:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For source-key OCR tools and tests, additionally install `pytesseract pytest`. Source extraction also needs the Tesseract executable; it is already present on this laptop. OMR recognition and normal bot operation do not use Tesseract.

## Commands

```powershell
.\run.ps1 exams
.\run.ps1 validate-keys
.\run.ps1 inspect omr-exam-paper-example\20261115_191159.jpg --output var/practice
.\run.ps1 review-keys
.\.venv\Scripts\python.exe -m pytest -q
```

The key-review screen runs at http://127.0.0.1:8765 and stays on this computer. Select an exam, inspect the source crops and original pages, fill unresolved answers, correct any OCR errors, and verify all 100 answers. Enter `BC` when either B or C is accepted. A reviewer name and source-page confirmations are required to verify a key. Saving a draft disables final grading again. Each save checks its revision and keeps the previous database as `data/answer_keys.before-review.json`.

The original folders `omr-check-answer-sheet-images` and `omr-exam-paper-example` belong beside this README. They are already present in this workspace. They are not duplicated in the code download. Runtime recognition uses the normalized reference assets in `assets`; source-key review uses your original source photos.

## Scoring

- Correct single shaded bubble: +1.
- Wrong single, multiple filled bubbles, or an invalid tick/cross: -0.25 earned marks, equivalent to losing 1.25 from a perfect score.
- Unanswered: 0 earned marks, equivalent to losing 1 from a perfect score.
- Final score = correct - 0.25 × (wrong + multiple + invalid). Negative scores are preserved.
- If a key accepts B or C, either individual bubble is correct. Filling both remains wrong.
- Uncertain recognition is a separate state and blocks grading until resolved. A bad photo is not automatically counted as wrong.

Results use explicit labels with separated question lists and answer comparisons:
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

## Exam search and selection

`data/answer_keys.json` has a schema version, scoring metadata, and 67 exam records: 50 practice-book exams and 17 Retina exams. Every initial record reserves question numbers 1–100. An unresolved answer is `null`, never a guessed letter. Accepted answers are arrays, for example `"74": ["B", "C"]`.

- `/exams [words]` performs keyword search across exam IDs, displayed names, collections, and aliases (e.g. `/exams english practice`). Results are paginated with inline `[Select: ...]` buttons and page navigation.
- `/exam` without arguments shows concise usage help.
- `/exam NAME` accepts exact displayed labels (e.g. `Paper Final English [Practice book]`), exact IDs, names, or aliases.
- When an exam name exists across multiple collections, the bot prompts with collection-specific inline buttons; it never silently guesses.
- Image captions and `/exam` use the exact same resolver. An invalid or ambiguous caption never silently falls back to a previously selected exam.
- Selecting a new exam updates the default for subsequent uploads without mutating the `exam_id` of an active in-review reading. All callback payloads are strictly bounded under Telegram's 64-byte limit.

## Architecture

- `domain.py`: validated marks, accepted answers, exact Decimal scoring; no Telegram or image-processing dependencies.
- `catalog.py`: key validation and case-insensitive name resolution; ambiguity stays explicit.
- `recognition.py`: EXIF orientation, SIFT alignment across the answer grid, template coverage checks, black-ink measurement, and review annotations.
- `sessions.py`: owner-scoped, expiring sessions; correction history; stale confirmation protection.
- `bot.py`: Telegram commands, uploads, preview, corrections, and confirmation.
- `review.py`: local source verification with revision-checked atomic saves.
- `tools/`: reproducible template calibration, conservative draft OCR, catalog assembly, and sample checks.

The reader uses answer-grid features to align the sheet. Names, roll numbers, serial numbers, surrounding questions, and the title printed on the uploaded OMR do not select the grading key. The user's supplied exam name does.

## VPS

The same source code runs with the supplied Dockerfile:

```sh
docker build -t omr-check .
docker run --rm --env-file .env -v omr-data:/app/var omr-check
```

Verify and finalize the key database before building the deployment image. Rebuild the image after changing keys, or mount your own database path. Long polling needs outbound HTTPS and does not need a public inbound port. Run only one polling instance for each bot token. The container runs as a non-root user; mounted directories must be writable by that user. This container configuration has not been deployed to a VPS in this session.

## Limits and retention

A small set of real photos cannot establish production accuracy across different phones, shadows, folds, lighting, or dense tick/cross marks. Partial and nonstandard marks are sent for review. Synthetic marks are useful regression tests, not evidence of universal accuracy. Keep the complete grid visible and flatten the page.

Images and review records live under `var/sessions`. The configured default session lifetime is 30 minutes. Expired data is removed on subsequent activity or startup; no background deletion service is implied. Successful confirmation and cancellation delete that active session. Restarting the bot requires uploading the photo again. Bot tokens and local data are excluded from version control and the code download.
