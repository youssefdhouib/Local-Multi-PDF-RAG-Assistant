from pathlib import Path
import json
from tqdm import tqdm

from ingest.router import process_pdf

DATA_DIR = Path("data")
OUT_FILE = Path("storage/pages.jsonl")

def main():
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        print("❌ Put PDFs inside ./data")
        return

    with OUT_FILE.open("w", encoding="utf-8") as f:
        for pdf in tqdm(pdfs, desc="PDF Processing (Unstructured + fallback)"):
            records = process_pdf(pdf, unstructured_strategy="fast")
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"✅ Done. Output: {OUT_FILE.resolve()}")

if __name__ == "__main__":
    main()
