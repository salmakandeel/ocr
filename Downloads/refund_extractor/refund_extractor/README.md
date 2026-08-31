# استردادات — Refund Data Extractor

Extracts refund-payment data from your `استردادات` folder (one subfolder
per student, each containing a bank confirmation letter image + the
university refund-request form image) into Excel files ready for the
bank, batched 25 rows at a time.

## How it works — 2 stages

**Stage 1 — extract:** reads every image with OCR (Tesseract) and builds
one *draft* workbook.
- From the **bank letter** (machine-printed, so OCR is reliable): account
  holder name, account number (or IBAN if no plain account number is
  printed), bank abbreviation, account type.
- From the **university form**: the student name and amount are
  **handwritten**, and Tesseract cannot reliably read handwriting — it
  will get some of these wrong. So instead of trusting it blindly, the
  draft workbook has a second **"Review" sheet** that shows a small
  cropped image of exactly where each handwritten value came from, next
  to OCR's best guess. Glance at the snippet, and fix the "Data" sheet's
  Transaction Amount / Remittance Information cells if OCR got it wrong.
  Cells with no digits detected at all are highlighted yellow so you
  don't miss them.

**Stage 2 — batch:** once you're happy with the corrected Data sheet,
this splits it into files of 25 rows each, named after the sum of that
file's Transaction Amount column — exactly as you asked.

## Setup (one-time)

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-ara
pip install -r requirements.txt --break-system-packages   # or use a venv
```

## Usage

```bash
# Stage 1: point it at your استردادات folder
python3 extract_data.py "/path/to/استردادات" draft_output.xlsx

# -> open draft_output.xlsx, check the "Review" sheet, fix any
#    highlighted / wrong cells in the "Data" sheet, save it.

# Stage 2: split the corrected file into batches of 25
python3 build_batches.py draft_output.xlsx batches_folder --batch-size 25
```

Each subfolder under `استردادات` = one case, and must contain exactly
2 images (any common format: png/jpg/jpeg/bmp/tif/webp, any filenames —
they're told apart automatically by their content, not their name).

## Fixed values used for every row

These were set per your instructions — edit the constants at the top of
`extract_data.py` if they ever change:

| Field | Value |
|---|---|
| Debtor Name | جامعة المنوفيه الاهليه |
| Debtor Account Number | 20314180200 |
| Debtor Account Type | CACC |
| Transaction Purpose | cash |
| Creditor National ID | (always left blank) |

## Extending bank recognition

`bank_map.json` maps a bank's Swift/BIC prefix (and, as a fallback, Arabic
or English name keywords) to the English abbreviation written into the
"Creditor Bank" column. It already covers the major Egyptian banks. If a
row comes back with an empty Creditor Bank, open the bank letter, find
its actual Swift Code or bank name, and add an entry to this file — no
code changes needed.

## Files

| File | Purpose |
|---|---|
| `extract_data.py` | Stage 1 — walks the folder, runs OCR, writes the draft workbook |
| `build_batches.py` | Stage 2 — splits the corrected draft into 25-row batches |
| `ocr_utils.py` | Shared OCR helpers (orientation-fixing, preprocessing) |
| `extract_bank_letter.py` | Field extraction from the bank letter image |
| `extract_university_form.py` | Field extraction (+ crop) from the university form image |
| `bank_map.json` | Swift-code / bank-name → English abbreviation lookup (editable) |

## Known limitations (please read)

- **Handwriting is never auto-trusted.** Transaction Amount and
  Remittance Information (student name) always need a human glance at
  the Review sheet — this is a deliberate choice, not a bug, because a
  wrong guess here means money going to the wrong place with no warning.
- The two crop regions for the university form (student name box, amount
  box) are hard-coded as percentages of the page in
  `extract_university_form.py` → `CROP_BOXES`, based on your sample form.
  If a different form template shows up, adjust those two boxes.
- The bank-letter parser was built and tested against the National Bank
  of Egypt letter format you sent. Other banks' letters may have a
  different layout — check the first few rows from any new bank
  carefully; if a field comes back empty, open `extract_bank_letter.py`
  and tell me (or adjust) how that bank's fields are labeled.
- If a subfolder doesn't have exactly 2 images, that case is skipped and
  flagged with a warning in the Review sheet rather than guessed at.
