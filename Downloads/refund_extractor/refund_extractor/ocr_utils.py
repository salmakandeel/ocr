"""
Shared OCR helpers.

Tesseract reads MACHINE-PRINTED Arabic/English reasonably well once the
image is right-side-up and reasonably sharp. It does NOT reliably read
HANDWRITING (Arabic or Latin). Keep that in mind when using these helpers
on fields that are filled in by hand.
"""
import re
import pytesseract
from PIL import Image, ImageOps

LANG = "ara+eng"

KEYWORDS_BANK_LETTER = [
    "iban", "swift", "بنك", "الحساب الدولى", "الحساب الدولي", "national bank",
]
KEYWORDS_UNIVERSITY_FORM = [
    "استرداد", "الطالب", "مرفقات", "جامعة", "المصروفات", "university",
]


def _score_text(text: str, keywords) -> int:
    t = text.lower()
    return sum(1 for k in keywords if k.lower() in t)


def load_best_orientation(path: str) -> Image.Image:
    """
    Photos of documents are sometimes rotated (portrait doc shot sideways,
    etc). Use Tesseract's dedicated orientation-detection (OSD) — it's a
    single fast pass purpose-built for this, much quicker and more
    reliable here than brute-forcing 4 full OCR passes. Falls back to the
    brute-force method only if OSD can't get a confident reading (it
    sometimes fails on very sparse-text images).
    """
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)  # respect camera EXIF orientation first

    try:
        osd = pytesseract.image_to_osd(im)
        m = re.search(r"Rotate:\s*(\d+)", osd)
        if m:
            rotate_cw = int(m.group(1))
            if rotate_cw:
                return im.rotate(-rotate_cw, expand=True)
            return im
    except Exception:
        pass

    # Fallback: brute-force scoring on a downscaled copy.
    small = im.copy()
    small.thumbnail((1000, 1000))
    best_angle, best_score = 0, -1
    for angle in (0, 90, 180, 270):
        candidate = small.rotate(angle, expand=True) if angle else small
        gray = candidate.convert("L")
        txt = pytesseract.image_to_string(gray, lang=LANG, config="--psm 6")
        score = len(txt.strip())
        if score > best_score:
            best_score = score
            best_angle = angle
    return im.rotate(best_angle, expand=True) if best_angle else im


def preprocess(im: Image.Image, scale: float = 2.0) -> Image.Image:
    gray = im.convert("L")
    w, h = gray.size
    return gray.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def ocr_text(im: Image.Image, psm: int = 4) -> str:
    return pytesseract.image_to_string(im, lang=LANG, config=f"--psm {psm}")


SIGNAL_KEYWORDS = ["iban", "swift", "eg4", "eg6", "eg2", "national bank", "بنك"]


def _signal_score(text: str) -> int:
    low = text.lower()
    # reward hitting known-useful keywords, not just raw character count
    # (a noisier OCR pass often has MORE characters but LESS useful signal)
    return sum(low.count(k) for k in SIGNAL_KEYWORDS)


def best_effort_full_text_from_image(im: Image.Image) -> str:
    prepped = preprocess(im)
    candidates = [ocr_text(prepped, psm) for psm in (4, 6)]
    scored = [(_signal_score(c), len(c), c) for c in candidates]
    scored.sort(reverse=True)
    return scored[0][2]


def best_effort_full_text(path: str) -> str:
    """Convenience wrapper for standalone/CLI use — loads+orients from a path."""
    im = load_best_orientation(path)
    return best_effort_full_text_from_image(im)


def classify_image(path: str):
    """
    Returns ('bank_letter' | 'university_form' | 'unknown', ocr_text, oriented_image)
    Classification is by CONTENT, not filename, since filenames aren't
    guaranteed consistent across folders. The returned oriented_image and
    ocr_text can be reused by the caller to avoid redoing orientation
    detection and OCR.
    """
    im = load_best_orientation(path)
    text = best_effort_full_text_from_image(im)
    bank_score = _score_text(text, KEYWORDS_BANK_LETTER)
    form_score = _score_text(text, KEYWORDS_UNIVERSITY_FORM)
    if bank_score == 0 and form_score == 0:
        kind = "unknown"
    elif bank_score >= form_score:
        kind = "bank_letter"
    else:
        kind = "university_form"
    return kind, text, im


def crop_relative(im: Image.Image, box_ratio):
    """box_ratio = (x0,y0,x1,y1) as fractions of width/height (0..1)."""
    w, h = im.size
    x0, y0, x1, y1 = box_ratio
    return im.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))


def clean_digits(s: str) -> str:
    return re.sub(r"[^\d]", "", s or "")
