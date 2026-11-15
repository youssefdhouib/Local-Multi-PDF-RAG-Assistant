import logging
import os
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0
logger = logging.getLogger(__name__)

# Where the Tesseract program is. On Windows the installer does not add it to
# PATH, so we also try its standard install folder. Override with TESSERACT_CMD.
_WINDOWS_DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
_tesseract_cmd = os.environ.get("TESSERACT_CMD") or (
    _WINDOWS_DEFAULT_TESSERACT if Path(_WINDOWS_DEFAULT_TESSERACT).exists() else None
)
if _tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd

# OCR languages, combined with "+" (e.g. "fra+eng"). Override with OCR_LANGS.
DEFAULT_OCR_LANGS = os.environ.get("OCR_LANGS", "fra+eng")

LANG_MAP = {"en": "eng", "fr": "fra", "ar": "ara", "de": "deu", "es": "spa"}

def clean(s: str) -> str:
    return " ".join((s or "").split()).strip()

def detect_lang(text: str, default="unknown"):
    try:
        t = clean(text)
        return detect(t) if len(t) >= 60 else default
    except Exception:
        return default

def usable_ocr_langs(wanted: str) -> str:
    """
    Keep only the languages Tesseract actually has installed.
    A default Windows install has only English; asking for "fra+eng" would
    then fail for every page, so we fall back to what is available.
    """
    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        return wanted  # Tesseract missing: OCR will fail later and the page is skipped
    usable = [lang for lang in wanted.split("+") if lang in installed]
    if len(usable) < len(wanted.split("+")):
        logger.warning("OCR languages %s requested, only %s installed", wanted, usable or ["eng"])
    return "+".join(usable) or "eng"

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
    ocr_langs = usable_ocr_langs(ocr_langs)

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

        ocr = ""
        if need_ocr:
            try:
                ocr = ocr_page(page, page_ocr_langs, dpi=dpi)
            except Exception as e:
                # e.g. Tesseract not installed. Before, one blank/short page made the
                # whole upload fail. Now we keep the page's native text (if any).
                logger.warning("OCR failed for %s page %d (%s); using native text only",
                               pdf_path.name, page_num, e)
                need_ocr = False

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

    # Release the file handle (on Windows an open handle blocks deleting the PDF).
    doc.close()
    return out
