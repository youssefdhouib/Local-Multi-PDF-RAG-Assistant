from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb

DEFAULT_CHROMA_DIR = "storage/chroma_db"
DEFAULT_COLLECTION_NAME = "pdf_chunks"


@lru_cache(maxsize=8)
def _client_for(abs_path: str):
    # One client per storage folder, reused across requests.
    return chromadb.PersistentClient(path=abs_path)


def get_collection(
    chroma_dir: str = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME
):
    """
    Return the chunk collection, creating it if needed.

    get_or_create (instead of get) means asking a question before the first
    upload returns "no evidence" instead of a 500 "collection does not exist".
    The cosine setting must match what ingestion uses, because the relevance
    guardrail in rag_answer compares cosine distances.
    """
    client = _client_for(str(Path(chroma_dir).resolve()))
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def list_docs(
    chroma_dir: str = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME
) -> List[str]:
    col = get_collection(chroma_dir, collection_name)
    docs = set()

    offset = 0
    limit = 1000
    while True:
        data = col.get(include=["metadatas"], limit=limit, offset=offset)
        metas = data.get("metadatas", [])
        if not metas:
            break

        for m in metas:
            if m and "doc" in m:
                docs.add(m["doc"])

        if len(metas) < limit:
            break
        offset += limit

    return sorted(docs)


def fetch_doc_chunks(
    doc_name: str,
    chroma_dir: str = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    max_chunks: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Fetch chunks belonging to a specific document.
    Returns list of dicts: {"text": ..., "meta": ...}
    Sorted by (page, chunk_index).
    """
    print(f"DEBUG: fetching chunks for doc='{doc_name}' from {chroma_dir}/{collection_name}")
    try:
        col = get_collection(chroma_dir, collection_name)
    except Exception as e:
        print(f"ERROR: Failed to get collection: {e}")
        return []

    docs = []
    metas = []

    # Prefer server-side filter if supported
    try:
        # Note: ChromaDB .get() returns a dict with 'documents' and 'metadatas' keys
        data = col.get(where={"doc": doc_name}, include=["documents", "metadatas"])
        if data:
            docs = data.get("documents", [])
            metas = data.get("metadatas", [])
            
        print(f"DEBUG: Found {len(docs) if docs else 0} chunks for '{doc_name}'")
        
        # Fallback: If no docs found, maybe the doc name in DB is slightly different?
        if not docs:
            print("DEBUG: Zero chunks found. Checking available docs...")
            all_data = col.get(include=["metadatas"])
            all_metas = all_data.get("metadatas", [])
            existing_docs = set()
            for m in all_metas:
                if m and "doc" in m:
                    existing_docs.add(m["doc"])
            print(f"DEBUG: Available docs in DB: {list(existing_docs)}")
            
    except Exception as e:
        print(f"ERROR: fetch_doc_chunks failed: {e}")
        # Last resort fallback: fetch all then filter manually
        try:
            data = col.get(include=["documents", "metadatas"])
            docs_all = data.get("documents", [])
            metas_all = data.get("metadatas", [])
            pairs = [(d, m) for d, m in zip(docs_all, metas_all) if m and m.get("doc") == doc_name]
            docs = [p[0] for p in pairs]
            metas = [p[1] for p in pairs]
            print(f"DEBUG: Fallback manual filter found {len(docs)} chunks")
        except Exception as e2:
            print(f"ERROR: Fallback failed: {e2}")
            return []

    items = [{"text": d, "meta": m} for d, m in zip(docs, metas) if d and m]

    def key_fn(it):
        m = it["meta"]
        return (int(m.get("page", 10**9)), int(m.get("chunk_index", 10**9)))

    try:
        items.sort(key=key_fn)
    except Exception:
        pass # sort might fail if meta missing

    if max_chunks is not None:
        items = items[:max_chunks]

    return items


def fetch_library_sample(
    chroma_dir: str = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    per_doc: int = 12
) -> List[Dict[str, Any]]:
    """
    Sample first N chunks per document (ordered).
    Good for a quick library-wide summary or MCQ generation.
    """
    docs = list_docs(chroma_dir, collection_name)
    out: List[Dict[str, Any]] = []
    for d in docs:
        out.extend(fetch_doc_chunks(d, chroma_dir, collection_name, max_chunks=per_doc))
    return out
