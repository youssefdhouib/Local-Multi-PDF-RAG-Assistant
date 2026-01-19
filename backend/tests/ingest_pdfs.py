from pathlib import Path
import json
from tqdm import tqdm

from pypdf import PdfReader
import fitz  # PyMuPDF


DATA_DIR = Path("data")
OUT_FILE = Path("storage/pages.jsonl")


def clean_text(text: str) -> str:
    """Basic cleanup: remove extra whitespace/newlines."""
    return " ".join((text or "").split()).strip()


def extract_with_pypdf(pdf_path: Path):
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = clean_text(page.extract_text())
        if text:
            pages.append({"doc": pdf_path.name, "page": i, "text": text})
    return pages


def extract_with_pymupdf(pdf_path: Path):
    doc = fitz.open(str(pdf_path))
    pages = []
    for i in range(len(doc)):
        page = doc[i]
        # sort=True helps reading order for many PDFs
        text = clean_text(page.get_text("text", sort=True))
        if text:
            pages.append({"doc": pdf_path.name, "page": i + 1, "text": text})
    return pages


def choose_best_extraction(pdf_path: Path):
    """Try pypdf first; if too many empty pages, fallback to pymupdf."""
    pypdf_pages = extract_with_pypdf(pdf_path)

    # If pypdf gets almost nothing, fallback
    if len(pypdf_pages) < 0.4 * max(1, get_page_count(pdf_path)):
        pymu_pages = extract_with_pymupdf(pdf_path)
        # choose whichever gives more extracted pages
        return pymu_pages if len(pymu_pages) > len(pypdf_pages) else pypdf_pages

    return pypdf_pages


def get_page_count(pdf_path: Path) -> int:
    try:
        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception:
        try:
            doc = fitz.open(str(pdf_path))
            return len(doc)
        except Exception:
            return 0


def main():
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        print("❌ No PDFs found in ./data")
        return

    all_pages = []
    for pdf in tqdm(pdfs, desc="Processing PDFs"):
        try:
            pages = choose_best_extraction(pdf)
            all_pages.extend(pages)
        except Exception as e:
            print(f"⚠️ Failed on {pdf.name}: {e}")

    # Write JSONL
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for item in all_pages:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Quick stats
    docs = len(set(p["doc"] for p in all_pages))
    print(f"\n✅ Done.")
    print(f"- PDFs processed: {len(pdfs)}")
    print(f"- Docs extracted: {docs}")
    print(f"- Pages extracted: {len(all_pages)}")
    print(f"- Output: {OUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
