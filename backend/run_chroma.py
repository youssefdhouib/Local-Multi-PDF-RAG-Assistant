from pathlib import Path
import json
import math
import chromadb

EMBED_FILE = Path("storage/chunks_with_embeddings.jsonl")
CHROMA_DIR = "storage/chroma_db"
COLLECTION_NAME = "pdf_chunks"
BATCH_SIZE = 512


def normalize(vec):
    """Normalize a vector for cosine similarity (safe even if already normalized)."""
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def make_id(doc: str, page: int, chunk_index: int) -> str:
    """Globally unique chunk id across all PDFs/pages."""
    return f"{doc}::p{page}::c{chunk_index}"


def main():
    if not EMBED_FILE.exists():
        print("❌ Missing storage/chunks_with_embeddings.jsonl (run Step 5 first).")
        return

    # Persistent client = stored on disk
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # cosine search space
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    ids, embeddings, documents, metadatas = [], [], [], []
    total = 0

    with EMBED_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)

            doc = c["doc"]
            page = int(c["page"])
            chunk_index = int(c["chunk_index"])
            text = c["text"]
            emb = c["embedding"]

            # robust unique id
            cid = make_id(doc, page, chunk_index)

            # ensure embedding is normalized for cosine similarity
            emb = normalize(emb)

            ids.append(cid)
            embeddings.append(emb)
            documents.append(text)
            metadatas.append({
                "doc": doc,
                "page": page,
                "chunk_index": chunk_index,
                "lang": c.get("lang", "unknown"),
                "source": c.get("source", "unknown"),
                "char_len": len(text),
            })

            # batch upsert for speed + safe reruns
            if len(ids) >= BATCH_SIZE:
                collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas,
                )
                total += len(ids)
                print(f"✅ Upserted {total} chunks...")
                ids, embeddings, documents, metadatas = [], [], [], []

    # final leftover batch
    if ids:
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        total += len(ids)

    print(f"\n🎉 DONE. Stored {total} chunks.")
    print(f"📦 Chroma DB persisted at: {Path(CHROMA_DIR).resolve()}")
    print(f"📚 Collection name: {COLLECTION_NAME}")


if __name__ == "__main__":
    main()
