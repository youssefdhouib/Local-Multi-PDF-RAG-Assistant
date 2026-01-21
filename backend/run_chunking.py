from pathlib import Path
import json
from ingest.chunking import normalize_to_pages, build_chunks

IN_FILE = Path("storage/pages.jsonl")
OUT_FILE = Path("storage/chunks.jsonl")

# Tune if you want
TARGET_CHARS = 800
OVERLAP_CHARS = 150

def main():
    if not IN_FILE.exists():
        print(f"❌ Missing {IN_FILE}. Run Step 2 first (run_pdf_processing.py).")
        return

    records = []
    with IN_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    # 1) Normalize (element-level OR page-level) => page-level
    pages = normalize_to_pages(records)

    # 2) Chunk
    chunks = build_chunks(pages, target_chars=TARGET_CHARS, overlap_chars=OVERLAP_CHARS)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"✅ Pages normalized: {len(pages)}")
    print(f"✅ Chunks written: {len(chunks)}")
    print(f"📄 Output: {OUT_FILE.resolve()}")

if __name__ == "__main__":
    main()
