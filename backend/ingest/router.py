import logging
from pathlib import Path
from ingest.unstructured_backend import partition_pdf_unstructured
from ingest.custom_fallback import process_pdf_custom

logger = logging.getLogger(__name__)


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
        logger.info("Unstructured extracted too little text from %s; using PyMuPDF/OCR fallback", pdf_path.name)
    except Exception as e:
        # Not silent any more: a missing optional dependency shows up in the logs.
        logger.warning("Unstructured failed for %s (%s: %s); using PyMuPDF/OCR fallback",
                       pdf_path.name, type(e).__name__, e)

    # 2) Fallback custom AUTO OCR
    return process_pdf_custom(pdf_path)
