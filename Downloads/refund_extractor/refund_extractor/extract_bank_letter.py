"""
Extracts, from a bank account-confirmation letter image:
  - creditor_name        (اسم العميل / اسم صاحب الحساب)
  - creditor_account_no  (رقم الحساب; falls back to IBAN if not found)
  - creditor_bank        (English abbreviation, via bank_map.json)
  - creditor_account_type ("Saving" / "Current" if we can find it)
  - national_id          (رقم الهوية) — extracted but, per instructions,
                          NOT written into the final sheet (left blank there)

This document is normally machine-printed by the bank, so OCR accuracy
here is usually good. Still, always spot-check a handful of rows the
first time you run this against a new bank's letter format.
"""
import json
import re
from pathlib import Path

from ocr_utils import best_effort_full_text, load_best_orientation, best_effort_full_text_from_image

BANK_MAP_PATH = Path(__file__).parent / "bank_map.json"
_bank_map = json.loads(BANK_MAP_PATH.read_text(encoding="utf-8"))
SWIFT_PREFIX_MAP = _bank_map.get("swift_prefix", {})
NAME_KEYWORD_MAP = _bank_map.get("name_keywords", {})

LONG_DIGITS_RE = re.compile(r"\d[\d\s]{6,20}\d")
# Valid Swift/BIC codes have letters for bank+country+location, so require
# at least the first 6 chars to be letters (avoids matching plain English words).
SWIFT_RE = re.compile(r"\b([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b")


def _clean(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _find_iban(text: str):
    """
    Egyptian IBANs are 'EG' + 27 digits (29 chars total). OCR sometimes runs
    the IBAN straight into the next table cell with just a space between, so
    we deliberately stop after exactly 27 digits instead of matching greedily.
    """
    flat = text.replace("\n", " ")
    upper = flat.upper()
    start = 0
    while True:
        idx = upper.find("EG", start)
        if idx == -1:
            return None
        digits = []
        i = idx + 2
        while i < len(flat) and len(digits) < 27:
            c = flat[i]
            if c.isdigit():
                digits.append(c)
            elif not c.isspace():
                break
            i += 1
        if len(digits) >= 25:  # tolerate 1-2 missed digits from noisy OCR
            return "EG" + "".join(digits)
        start = idx + 2


def _table_row_line(text: str):
    """The line holding the actual account data usually sits right after
    (or is) the line naming the Swift Code / IBAN column headers. 'IBAN'
    often also appears earlier in a title sentence, so prefer the LAST
    matching line (closest to the actual data table), and prefer a line
    that literally says 'swift' over one that only says 'iban'."""
    lines = text.splitlines()
    last_swift_idx = None
    last_iban_idx = None
    for i, line in enumerate(lines):
        low = line.lower()
        if "swift" in low:
            last_swift_idx = i
        elif "iban" in low:
            last_iban_idx = i
    idx = last_swift_idx if last_swift_idx is not None else last_iban_idx
    if idx is not None:
        return " ".join(lines[idx:idx + 4])
    return text.replace("\n", " ")


def _find_swift(text: str):
    row = _table_row_line(text)
    # Keep whitespace/punctuation as word boundaries — collapsing spaces
    # would fuse the Swift code onto the immediately-adjacent IBAN digits.
    m = SWIFT_RE.search(row.upper())
    return m.group(1) if m else None


def _find_account_number(text: str, iban: str):
    """
    The account number usually sits right next to the IBAN in the same
    table row (e.g. '...IBAN... 4125000547040600018'). Rather than
    re-searching for 'EG' in the row (which can false-match letters
    embedded inside the Swift code, e.g. the 'EG' inside 'NBEGEGCX412'),
    we anchor on the tail digits of the IBAN we already found (from the
    full text) within the row's digit-only stream, then read whatever
    digits come right after.
    """
    row = _table_row_line(text)
    if iban:
        iban_digits = re.sub(r"\D", "", iban)
        anchor = iban_digits[-6:]
        digit_positions = [i for i, ch in enumerate(row) if ch.isdigit()]
        digit_stream = "".join(row[i] for i in digit_positions)
        pos = digit_stream.find(anchor)
        if pos != -1:
            remainder = digit_stream[pos + len(anchor):pos + len(anchor) + 22]
            if len(remainder) >= 8:
                return remainder
    # Fallback: any standalone long digit run elsewhere in the row that
    # isn't the IBAN itself.
    candidates = [_clean(m) for m in LONG_DIGITS_RE.findall(row)]
    candidates = [c for c in candidates if c and len(c) >= 8]
    if iban:
        candidates = [c for c in candidates if c not in iban and iban not in c]
    if not candidates:
        return None
    return max(candidates, key=len)


def _find_label_value(text: str, labels):
    """Exact-label lookup (works when OCR read the label correctly)."""
    for label in labels:
        pattern = re.compile(re.escape(label) + r"\s*[/:\-]?\s*([^\n]+)")
        m = pattern.search(text)
        if m:
            val = m.group(1).strip(" -:/\t")
            val = re.split(r"\s{2,}|\|", val)[0].strip()
            if val:
                return val
    return None


AR_WORD_RE = re.compile(r"[\u0600-\u06FF]+")


def _find_customer_name(text: str):
    """
    The 'اسم العميل' label frequently gets OCR-mangled (e.g. 'اسم' -> 'أنسة').
    Instead of relying on the exact label, find the line that mentions
    'العميل' but has NO digits on it (a name line) rather than
    'رقم العميل' (the customer *number* line, which has digits).
    """
    for line in text.splitlines():
        # Use ASCII-digit check only — Arabic OCR noise sometimes includes a
        # stray Arabic-Indic numeral (e.g. '١') that Python's \d would also
        # match, wrongly disqualifying a genuine name line.
        if "العميل" in line and not re.search(r"[0-9]", line):
            after_slash = line.split("/", 1)
            candidate = after_slash[1] if len(after_slash) > 1 else line
            words = AR_WORD_RE.findall(candidate)
            if len(words) >= 2:  # a real name has at least 2 words
                return " ".join(words)
    return None


def _bank_abbrev(text: str, swift: str):
    if swift:
        for prefix, abbrev in SWIFT_PREFIX_MAP.items():
            if swift.upper().startswith(prefix):
                return abbrev
    low = text.lower()
    for keyword, abbrev in NAME_KEYWORD_MAP.items():
        if keyword.lower() in low:
            return abbrev
    return ""


def _account_type(text: str):
    # Loose substrings to tolerate common OCR noise (e.g. "Savin eS" for "Saving").
    low = text.lower()
    for word, norm in (("savin", "Saving"), ("توفير", "Saving"),
                       ("curr", "Current"), ("جاري", "Current"), ("cacc", "Current")):
        if word in low:
            return norm
    return ""


def extract_bank_letter_from_text(text: str) -> dict:
    """Core extraction — reuse this when you already ran OCR (e.g. via
    ocr_utils.classify_image) to avoid doing it a second time."""
    iban = _find_iban(text)
    swift = _find_swift(text)
    account_no = _find_account_number(text, iban)
    name = (_find_label_value(text, ["اسم صاحب الحساب", "اسم العميل"])
            or _find_customer_name(text))
    national_id = _find_label_value(text, ["رقم الهوية"])
    bank_abbrev = _bank_abbrev(text, swift)
    account_type = _account_type(text)

    creditor_account_no = account_no or iban or ""

    return {
        "creditor_name": name or "",
        "creditor_account_no": creditor_account_no,
        "creditor_account_type": account_type,
        "creditor_bank": bank_abbrev,
        "national_id": national_id or "",  # kept for debugging only, not written to final sheet
        "_raw_text": text,
        "_iban_found": iban or "",
        "_swift_found": swift or "",
    }


def extract_bank_letter(path: str) -> dict:
    """Standalone/CLI convenience — loads+orients+OCRs from a path."""
    text = best_effort_full_text(path)
    return extract_bank_letter_from_text(text)


if __name__ == "__main__":
    import sys
    result = extract_bank_letter(sys.argv[1])
    for k, v in result.items():
        if k != "_raw_text":
            print(f"{k}: {v}")
