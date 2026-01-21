from pathlib import Path
import json
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import torch

# -----------------------
# CONFIG
# -----------------------
CHUNKS_FILE = Path("storage/chunks.jsonl")
OUT_FILE = Path("storage/chunks_with_embeddings.jsonl")

MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 32   # increase if you have more RAM / GPU

# -----------------------
# LOAD MODEL
# -----------------------
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🧠 Loading embedding model on {device}")

model = SentenceTransformer(MODEL_NAME, device=device)

# -----------------------
# MAIN
# -----------------------
def main():
    if not CHUNKS_FILE.exists():
        print("❌ chunks.jsonl not found. Run Step 3 first.")
        return

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load all chunks
    chunks = []
    with CHUNKS_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))

    print(f"📄 Loaded {len(chunks)} chunks")

    texts = [c["text"] for c in chunks]

    # Embed in batches
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    # Write enriched chunks
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for chunk, emb in zip(chunks, embeddings):
            chunk["embedding"] = emb.tolist()
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    print(f"✅ Embeddings written to: {OUT_FILE.resolve()}")

if __name__ == "__main__":
    main()
