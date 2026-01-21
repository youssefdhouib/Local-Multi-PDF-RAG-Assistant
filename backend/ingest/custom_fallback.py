from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

# For OCR you can pass combined langs like "fra+eng"
DEFAULT_OCR_LANGS = "fra+eng"

LANG_MAP = {"en": "eng", "fr": "fra", "ar": "ara", "de": "deu", "es": "spa"}

def clean(s: str) -> str:
    return " ".join((s or "").split()).strip()

def detect_lang(text: str, default="unknown"):
    try:
        t = clean(text)
        return detect(t) if len(t) >= 60 else default
    except Exception:
        return default

def map_tesseract(lang_code: str) -> str:
    # single-language mapping (when you want it)
    return LANG_MAP.get(lang_code, "eng")

def extract_native(page: fitz.Page) -> str:
    return clean(page.get_text("text", sort=True))

def render_page(page: fitz.Page, dpi: int = 200) -> Image.Image:
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

def ocr_page(page: fitz.Page, lang_tess: str, dpi: int = 200) -> str:
    img = render_page(page, dpi=dpi)
    # OEM 3 = default LSTM, PSM 6 = assume a block of text (good general default)
    config = "--oem 3 --psm 6"
    return clean(pytesseract.image_to_string(img, lang=lang_tess, config=config))

def is_scanned_pdf(doc: fitz.Document, sample_pages: int = 8, empty_th: int = 30, ratio_th: float = 0.6) -> bool:
    n = min(sample_pages, len(doc))
    if n == 0:
        return False
    empty = 0
    for i in range(n):
        if len(extract_native(doc[i])) < empty_th:
            empty += 1
    return (empty / n) >= ratio_th

def guess_doc_lang_from_ocr(doc: fitz.Document, dpi: int = 200, ocr_langs: str = DEFAULT_OCR_LANGS, sample_pages: int = 2):
    """
    For scanned PDFs: run OCR on first 1-2 pages with multi-lang,
    then detect language from the OCR text (more reliable than native='').
    """
    texts = []
    for i in range(min(sample_pages, len(doc))):
        try:
            t = ocr_page(doc[i], ocr_langs, dpi=dpi)
            if t:
                texts.append(t)
        except Exception:
            pass

    merged = "\n".join(texts)
    lang = detect_lang(merged, default="unknown")

    # Normalize common cases from langdetect:
    # fr/en/ar/de/es -> keep, else unknown
    if lang not in {"fr", "en", "ar", "de", "es"}:
        lang = "unknown"
    return lang

def process_pdf_custom(pdf_path: Path, weak_th: int = 80, dpi: int = 200, ocr_langs: str = DEFAULT_OCR_LANGS):
    """
    Page-level records:
    doc, page, type, source, lang, text
    AUTO mode:
      - if scanned -> OCR all pages
      - else OCR only weak pages

    Professional tweaks:
      - doc_lang decided once (stable)
      - OCR uses multi-language by default (fra+eng)
    """
    doc = fitz.open(str(pdf_path))
    scanned = is_scanned_pdf(doc)

    # Decide a stable doc language
    if scanned:
        doc_lang = guess_doc_lang_from_ocr(doc, dpi=dpi, ocr_langs=ocr_langs, sample_pages=2)
        # If we confidently detect a single language, you can optionally tighten OCR:
        # (keep multi-lang anyway; it's safer for mixed slides)
        page_ocr_langs = ocr_langs
    else:
        # For digital PDFs, detect from native text sample
        sample_text = "\n".join(extract_native(doc[i]) for i in range(min(2, len(doc))))
        doc_lang = detect_lang(sample_text, default="unknown")
        page_ocr_langs = ocr_langs  # still keep multi-lang if we ever OCR weak pages

    out = []
    for i in range(len(doc)):
        page = doc[i]
        page_num = i + 1

        native = extract_native(page)
        need_ocr = scanned or (len(native) < weak_th)

        ocr = ocr_page(page, page_ocr_langs, dpi=dpi) if need_ocr else ""

        # Merge
        if native and not need_ocr:
            text, source = native, "custom_native"
        elif (not native) and ocr:
            text, source = ocr, "custom_ocr"
        elif native and ocr:
            text, source = (native + "\n[OCR]\n" + ocr), "custom_mixed"
        else:
            continue

        text = clean(text)
        if text:
            out.append({
                "doc": pdf_path.name,
                "page": page_num,
                "type": "PageText",
                "source": source,
                "lang": doc_lang if doc_lang != "unknown" else detect_lang(text, default="unknown"),
                "text": text,
                "char_len": len(text),
            })

    return out
