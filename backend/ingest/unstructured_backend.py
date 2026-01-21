from pathlib import Path
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

def detect_lang(text: str, default="en"):
    try:
        return detect(text) if len(text) >= 50 else default
    except Exception:
        return default

def partition_pdf_unstructured(pdf_path: Path, strategy: str = "fast"):
    """
    Returns element-level records:
    doc, page, type, source, lang, text
    """
    from unstructured.partition.pdf import partition_pdf

    elements = partition_pdf(
        filename=str(pdf_path),
        strategy=strategy,   # "fast" default; switch to "hi_res" for better layout
    )

    out = []
    for el in elements:
        txt = (str(el) or "").strip()
        if not txt:
            continue

        meta = getattr(el, "metadata", None)
        page = int(getattr(meta, "page_number", 0) or 0)
        el_type = getattr(el, "category", el.__class__.__name__)
        lang = detect_lang(txt, default="en")

        out.append({
            "doc": pdf_path.name,
            "page": page,
            "type": el_type,
            "source": "unstructured",
            "lang": lang,
            "text": txt,
            "char_len": len(txt),
        })
    return out
