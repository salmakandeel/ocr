"""
Extracts data from the Menoufia National University refund-request form.

Two fields we need are HANDWRITTEN on this form:
  - اسم الطالب  (student name)
  - المبلغ      (amount)

Tesseract cannot reliably read Arabic handwriting (verified against your
sample: it read "50,225" as "30,22"). So instead of guessing, this module:
  1. Crops the small region of the image containing each handwritten field.
  2. Still runs OCR on the crop and returns it as a "best_guess" — sometimes
     it's right, especially for cleanly-written numerals — but flags it as
     low-confidence.
  3. Returns the cropped PIL Image itself so the caller can embed it in the
     draft Excel for a human to quickly glance at and correct.

If your university form template ever changes layout, adjust CROP_BOXES
below (each is a (x0, y0, x1, y1) box as a FRACTION of image width/height —
easiest way to redo this is to open the image, and eyeball where the field
sits as a percentage of the page).
"""
from ocr_utils import load_best_orientation, crop_relative, ocr_text, preprocess

CROP_BOXES = {
    "student_name": (0.0, 0.595, 0.55, 0.645),
    "amount": (0.55, 0.865, 0.85, 0.905),
}


def _ocr_crop(crop_img, psm=7):
    prepped = preprocess(crop_img, scale=3.0)
    return ocr_text(prepped, psm=psm).strip()


def extract_university_form_from_image(im) -> dict:
    """Core extraction — pass an already-oriented PIL Image (e.g. from
    ocr_utils.classify_image) to avoid redoing orientation detection."""
    name_crop = crop_relative(im, CROP_BOXES["student_name"])
    amount_crop = crop_relative(im, CROP_BOXES["amount"])

    name_guess = _ocr_crop(name_crop, psm=6)
    amount_guess = _ocr_crop(amount_crop, psm=7)

    return {
        "student_name_guess": name_guess,
        "student_name_crop": name_crop,
        "amount_guess": amount_guess,
        "amount_crop": amount_crop,
    }


def extract_university_form(path: str) -> dict:
    """Standalone/CLI convenience — loads+orients from a path."""
    im = load_best_orientation(path)
    return extract_university_form_from_image(im)


if __name__ == "__main__":
    import sys
    result = extract_university_form(sys.argv[1])
    print("student_name_guess:", result["student_name_guess"])
    print("amount_guess:", result["amount_guess"])
    result["student_name_crop"].save("/tmp/_debug_name_crop.png")
    result["amount_crop"].save("/tmp/_debug_amount_crop.png")
