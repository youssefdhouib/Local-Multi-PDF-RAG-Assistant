from pathlib import Path
from ingest.unstructured_backend import partition_pdf_unstructured
from ingest.custom_fallback import process_pdf_custom

def quality_bad(records) -> bool:
    # common pro rule: if extraction is too small, it's probably scanned/failed
    if not records:
        return True
    total_chars = sum(r["char_len"] for r in records)
    return total_chars < 800

def process_pdf(pdf_path: Path, unstructured_strategy="fast"):
    """
    Returns records in a unified schema (ready for chunking step).
    """
    # 1) Try Unstructured
    try:
        recs = partition_pdf_unstructured(pdf_path, strategy=unstructured_strategy)
        if not quality_bad(recs):
            return recs
    except Exception:
        pass

    # 2) Fallback custom AUTO OCR
    return process_pdf_custom(pdf_path)
