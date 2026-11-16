import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from datetime import datetime

from features import embeddings
from features.chroma_utils import get_collection

# Re-use existing logic
from ingest.router import process_pdf
from ingest.chunking import normalize_to_pages, build_chunks

# Constants (relative to the backend/ folder, where the server is started)
DATA_DIR = Path("data")
REGISTRY_FILE = Path("storage/registry.json")
PAGES_FILE = Path("storage/pages.jsonl")
CHUNKS_FILE = Path("storage/chunks.jsonl")
EMBED_FILE = Path("storage/chunks_with_embeddings.jsonl")
CHROMA_DIR = "storage/chroma_db"
COLLECTION_NAME = "pdf_chunks"
EMBED_MODEL_NAME = embeddings.EMBED_MODEL_NAME

# Registry lock: every read-modify-write of registry.json happens under it.
registry_lock = threading.RLock()
# JSONL lock: appends and rewrites of the cache files must not interleave.
jsonl_lock = threading.Lock()

logger = logging.getLogger(__name__)


def make_id(doc: str, page: int, chunk_index: int) -> str:
    return f"{doc}::p{page}::c{chunk_index}"


def safe_pdf_path(doc_name: str) -> Path:
    """
    Map a document name to its file inside DATA_DIR.

    Rejects names like "../web_server.py" so an API call can never read or
    delete a file outside the data folder. Both "/" and "\\" are refused on
    every OS: on Linux "\\" is not a path separator, so Path(...).name alone
    would accept "..\\secret.pdf" there.
    """
    if not doc_name or "/" in doc_name or "\\" in doc_name or doc_name in (".", ".."):
        raise ValueError(f"Invalid document name: {doc_name!r}")
    if not doc_name.lower().endswith(".pdf"):
        raise ValueError(f"Invalid document name (must end with .pdf): {doc_name!r}")
    path = (DATA_DIR / doc_name).resolve()
    if path.parent != DATA_DIR.resolve():
        raise ValueError(f"Invalid document name: {doc_name!r}")
    return path


class IngestService:
    def __init__(self):
        self._ensure_storage()

    def _ensure_storage(self):
        Path("storage").mkdir(exist_ok=True)
        DATA_DIR.mkdir(exist_ok=True)
        if not REGISTRY_FILE.exists():
            self._save_registry({})

        # Ensure JSONL files exist
        for f in [PAGES_FILE, CHUNKS_FILE, EMBED_FILE]:
            if not f.exists():
                f.touch()

    @property
    def embed_model(self):
        # Shared, cached model (same instance used for retrieval).
        return embeddings.get_embedder(EMBED_MODEL_NAME)

    @property
    def collection(self):
        # Shared, cached Chroma client; collection created with cosine distance.
        return get_collection(CHROMA_DIR, COLLECTION_NAME)

    # --- Registry Management ---

    def _load_registry(self) -> dict:
        with registry_lock:
            if not REGISTRY_FILE.exists():
                return {}
            try:
                with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                logger.exception("registry.json could not be read; treating it as empty")
                return {}

    def _save_registry(self, data: dict):
        # Write to a temp file then rename: a crash mid-write can't leave a
        # half-written (corrupted) registry behind.
        with registry_lock:
            fd, tmp = tempfile.mkstemp(dir=REGISTRY_FILE.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, REGISTRY_FILE)

    def update_status(self, doc_name: str, status: str, **kwargs):
        # The whole load -> modify -> save is under the lock, otherwise two
        # background ingestions can overwrite each other's status.
        with registry_lock:
            reg = self._load_registry()
            if doc_name not in reg:
                reg[doc_name] = {
                    "name": doc_name,
                    "created_at": datetime.now().isoformat()
                }

            reg[doc_name]["status"] = status
            reg[doc_name]["updated_at"] = datetime.now().isoformat()
            if status != "failed":
                reg[doc_name].pop("error", None)  # don't show an old error on a ready doc
            for k, v in kwargs.items():
                reg[doc_name][k] = v

            self._save_registry(reg)

    def get_all_docs(self):
        return self._load_registry()

    def get_doc(self, doc_name: str):
        return self._load_registry().get(doc_name)

    def get_doc_by_fingerprint(self, fingerprint: str) -> dict:
        """
        Check if a document with this fingerprint already exists.
        Returns the doc dict if found, else None.
        """
        reg = self._load_registry()
        for doc in reg.values():
            if doc.get("fingerprint") == fingerprint:
                return doc
        return None

    # --- Ingestion Pipeline ---

    def _clear_index(self, doc_name: str):
        """
        Remove a document's chunks from Chroma and the JSONL caches.
        Does NOT touch the PDF file or the registry.
        """
        self.collection.delete(where={"doc": doc_name})
        with jsonl_lock:
            self._remove_from_jsonl(PAGES_FILE, doc_name)
            self._remove_from_jsonl(CHUNKS_FILE, doc_name)
            self._remove_from_jsonl(EMBED_FILE, doc_name)

    def _append_jsonl(self, filepath: Path, rows):
        with jsonl_lock:
            with open(filepath, "a", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def ingest_background(self, file_path: Path, doc_name: str):
        """
        Runs the full pipeline in background:
        0. Clear any previous index for this doc (re-upload / re-index)
        1. Extract -> Append to pages.jsonl
        2. Chunk -> Append to chunks.jsonl
        3. Embed -> Append to chunks_with_embeddings.jsonl
        4. Upsert to Chroma
        """
        try:
            self.update_status(doc_name, "indexing")

            # 0. Old chunks must go first. Upsert alone only overwrites chunk IDs
            #    that still exist, so a shorter new version would leave stale
            #    chunks from the old version searchable (wrong citations).
            self._clear_index(doc_name)

            # 1. Extract
            records = process_pdf(file_path, unstructured_strategy="fast")
            if not records:
                raise ValueError("No text could be extracted (scanned PDF without OCR?)")

            for r in records:
                r["doc"] = doc_name  # Ensure doc name is consistent
            self._append_jsonl(PAGES_FILE, records)

            # 2. Chunk
            pages = normalize_to_pages(records)
            chunks = build_chunks(pages)
            if not chunks:
                raise ValueError("No chunks generated")

            for c in chunks:
                c["doc"] = doc_name
            self._append_jsonl(CHUNKS_FILE, chunks)

            # 3. Embed
            texts = [c["text"] for c in chunks]
            vectors = self.embed_model.encode(texts, normalize_embeddings=True)

            ids, vecs, metadatas, docs = [], [], [], []
            for chunk, emb in zip(chunks, vectors):
                chunk["embedding"] = emb.tolist()
                ids.append(make_id(doc_name, chunk["page"], chunk["chunk_index"]))
                vecs.append(chunk["embedding"])
                docs.append(chunk["text"])
                metadatas.append({
                    "doc": doc_name,
                    "page": chunk["page"],
                    "chunk_index": chunk["chunk_index"],
                    "source": "uploaded"
                })
            self._append_jsonl(EMBED_FILE, chunks)

            # 4. Chroma Upsert
            self.collection.upsert(
                ids=ids,
                embeddings=vecs,
                documents=docs,
                metadatas=metadatas
            )

            self.update_status(doc_name, "ready", chunk_count=len(ids), page_count=len(pages))
            logger.info("Ingestion complete for %s (%d chunks)", doc_name, len(ids))

        except Exception as e:
            logger.exception("Ingestion failed for %s", doc_name)
            self.update_status(doc_name, "failed", error=str(e))

    def delete_doc(self, doc_name: str):
        """Fully remove a document: vectors, caches, registry entry and the PDF."""
        pdf_path = safe_pdf_path(doc_name)  # raises ValueError on "../" tricks
        logger.info("Deleting %s from all storage", doc_name)

        # 1. Vectors + JSONL caches. If Chroma fails we stop here and let the
        #    error reach the API, instead of reporting a fake success while the
        #    document is still searchable.
        self._clear_index(doc_name)

        # 2. Registry
        with registry_lock:
            reg = self._load_registry()
            if doc_name in reg:
                del reg[doc_name]
                self._save_registry(reg)

        # 3. The PDF file itself
        if pdf_path.exists():
            try:
                pdf_path.unlink()
            except PermissionError:
                # Index is already gone; only the file remains (e.g. open in a viewer on Windows).
                logger.warning("Could not delete %s (file in use?)", pdf_path)

        return True

    def _remove_from_jsonl(self, filepath: Path, doc_name: str):
        """Remove all entries for a document from a JSONL file using streaming."""
        if not filepath.exists():
            return

        temp_path = None
        try:
            # Create a temporary file in the same directory
            temp_fd, temp_path = tempfile.mkstemp(dir=filepath.parent, suffix='.tmp')

            with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_file:
                with open(filepath, 'r', encoding='utf-8') as source_file:
                    for line in source_file:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            temp_file.write(line + '\n')  # keep malformed lines
                            continue
                        if obj.get("doc") != doc_name:
                            temp_file.write(line + '\n')

            # Replace original file with temp file
            os.replace(temp_path, filepath)

        except Exception as e:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            logger.warning("Error cleaning %s: %s", filepath.name, e)


ingest_service = IngestService()
