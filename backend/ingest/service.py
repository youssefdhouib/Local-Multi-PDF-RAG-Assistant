
import json
import time
import shutil
import threading
from pathlib import Path
from datetime import datetime
import chromadb
from sentence_transformers import SentenceTransformer

# Re-use existing logic
from ingest.router import process_pdf
from ingest.chunking import normalize_to_pages, build_chunks

# Constants
DATA_DIR = Path("data")
REGISTRY_FILE = Path("storage/registry.json")
PAGES_FILE = Path("storage/pages.jsonl")
CHUNKS_FILE = Path("storage/chunks.jsonl")
EMBED_FILE = Path("storage/chunks_with_embeddings.jsonl")
CHROMA_DIR = "storage/chroma_db"
COLLECTION_NAME = "pdf_chunks"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

# Lock for registry ensuring thread safety for status updates
registry_lock = threading.RLock()

def make_id(doc: str, page: int, chunk_index: int) -> str:
    return f"{doc}::p{page}::c{chunk_index}"

class IngestService:
    def __init__(self):
        self._embed_model = None
        self._chroma_client = None
        self._collection = None
        self._ensure_storage()

    def _ensure_storage(self):
        Path("storage").mkdir(exist_ok=True)
        if not REGISTRY_FILE.exists():
            self._save_registry({})
        
        # Ensure JSONL files exist
        for f in [PAGES_FILE, CHUNKS_FILE, EMBED_FILE]:
            if not f.exists():
                f.touch()

    @property
    def embed_model(self):
        if self._embed_model is None:
            # Lazy load
            self._embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        return self._embed_model

    @property
    def collection(self):
        if self._collection is None:
            self._chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
            self._collection = self._chroma_client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
        return self._collection

    # --- Registry Management ---

    def _load_registry(self) -> dict:
        with registry_lock:
            if not REGISTRY_FILE.exists():
                return {}
            try:
                with open(REGISTRY_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                return {}

    def _save_registry(self, data: dict):
        with registry_lock:
            with open(REGISTRY_FILE, "w") as f:
                json.dump(data, f, indent=2)

    def update_status(self, doc_name: str, status: str, **kwargs):
        reg = self._load_registry()
        if doc_name not in reg:
            reg[doc_name] = {
                "name": doc_name,
                "created_at": datetime.now().isoformat()
            }
        
        reg[doc_name]["status"] = status
        reg[doc_name]["updated_at"] = datetime.now().isoformat()
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

    def ingest_background(self, file_path: Path, doc_name: str):
        """
        Runs the full pipeline in background:
        1. Extract -> Append to pages.jsonl
        2. Chunk -> Append to chunks.jsonl
        3. Embed -> Append to chunks_with_embeddings.jsonl
        4. Upsert to Chroma
        """
        try:
            self.update_status(doc_name, "indexing")
            
            # 1. Extract
            records = process_pdf(file_path, unstructured_strategy="fast")
            if not records:
                raise ValueError("No text extracted")
            
            # Append pages (thread-safeish for append, but ideally we'd lock file)
            # For this scale, simple append is fine.
            with open(PAGES_FILE, "a", encoding="utf-8") as f:
                for r in records:
                    r["doc"] = doc_name # Ensure doc name is consistent
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

            # 2. Chunk
            pages = normalize_to_pages(records)
            chunks = build_chunks(pages)
            if not chunks:
                 raise ValueError("No chunks generated")

            with open(CHUNKS_FILE, "a", encoding="utf-8") as f:
                for c in chunks:
                    c["doc"] = doc_name
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")

            # 3. Embed
            texts = [c["text"] for c in chunks]
            embeddings = self.embed_model.encode(texts, normalize_embeddings=True)
            
            ids, vecs, metadatas, docs = [], [], [], []

            with open(EMBED_FILE, "a", encoding="utf-8") as f:
                for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                    chunk["embedding"] = emb.tolist()
                    chunk["doc"] = doc_name
                    f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    
                    # Prep for Chroma
                    cid = make_id(doc_name, chunk["page"], chunk["chunk_index"])
                    ids.append(cid)
                    vecs.append(chunk["embedding"])
                    docs.append(chunk["text"])
                    metadatas.append({
                        "doc": doc_name,
                        "page": chunk["page"],
                        "chunk_index": chunk["chunk_index"],
                        "source": "uploaded"
                    })

            # 4. Chroma Upsert
            self.collection.upsert(
                ids=ids,
                embeddings=vecs,
                documents=docs,
                metadatas=metadatas
            )

            self.update_status(doc_name, "ready", chunk_count=len(ids), page_count=len(pages))
            print(f"✅ Ingestion complete for {doc_name}")

        except Exception as e:
            print(f"❌ Ingestion failed for {doc_name}: {e}")
            self.update_status(doc_name, "failed", error=str(e))

    def delete_doc(self, doc_name: str):
        """Fully remove a document from the entire pipeline."""
        print(f"🗑️ Deleting {doc_name} from all storage...")
        
        # 1. Remove from Chroma vector store (SOURCE OF TRUTH for RAG)
        try:
            self.collection.delete(where={"doc": doc_name})
            print(f"  ✓ Removed from vector store")
        except Exception as e:
            print(f"  ⚠ Chroma delete error: {e}")

        # 2. Remove from Registry
        with registry_lock:
            reg = self._load_registry()
            if doc_name in reg:
                del reg[doc_name]
                self._save_registry(reg)
                print(f"  ✓ Removed from registry")

        # 3. Clean JSONL cache files (pages, chunks, embeddings)
        # Now safe to run because:
        # 1. We use RLock (no deadlock)
        # 2. We use streaming I/O (no memory hang)
        self._remove_from_jsonl(PAGES_FILE, doc_name)
        self._remove_from_jsonl(CHUNKS_FILE, doc_name)
        self._remove_from_jsonl(EMBED_FILE, doc_name)
        print(f"  ✓ Removed from JSONL cache files")
                
        # 4. Delete the actual PDF file
        try:
            pdf_path = DATA_DIR / doc_name
            if pdf_path.exists():
                pdf_path.unlink()
                print(f"  ✓ Deleted PDF file")
            else:
                print(f"  ⚠ PDF file not found: {pdf_path}")
        except PermissionError:
             print(f"  ❌ Permission denied deleting file (is it open?): {pdf_path}")
             # Don't crash, just log it. The user can delete it manually or retry.
        except Exception as e:
            print(f"  ❌ Error deleting file: {e}")

        print(f"✅ {doc_name} completely removed from pipeline")
        return True
    
    def _remove_from_jsonl(self, filepath: Path, doc_name: str):
        """Remove all entries for a document from a JSONL file using streaming."""
        if not filepath.exists():
            return
        
        import tempfile
        import os
        
        try:
            # Create a temporary file in the same directory
            temp_fd, temp_path = tempfile.mkstemp(dir=filepath.parent, suffix='.tmp')
            
            removed_count = 0
            kept_count = 0
            
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_file:
                with open(filepath, 'r', encoding='utf-8') as source_file:
                    for line in source_file:
                        line = line.strip()
                        if not line:
                            continue
                        
                        try:
                            obj = json.loads(line)
                            # Check various possible field names for doc identifier
                            doc_field = obj.get("doc") or obj.get("doc_name") or obj.get("source", "")
                            
                            if doc_field != doc_name:
                                temp_file.write(line + '\n')
                                kept_count += 1
                            else:
                                removed_count += 1
                        except json.JSONDecodeError:
                            # Keep malformed lines (shouldn't happen)
                            temp_file.write(line + '\n')
                            kept_count += 1
            
            # Replace original file with temp file
            os.replace(temp_path, filepath)
            print(f"    Cleaned {filepath.name}: removed {removed_count} entries, kept {kept_count}")
            
        except Exception as e:
            # Clean up temp file if it exists
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)
            print(f"  ⚠ Error cleaning {filepath.name}: {e}")

    def reindex_doc(self, doc_name: str):
        # 1. Check if file exists
        pdf_path = DATA_DIR / doc_name
        if not pdf_path.exists():
            raise FileNotFoundError(f"File {doc_name} not found on disk")

        # 2. Delete existing data in Chroma
        # (We don't delete from JSONL files to avoid rewriting huge files, 
        #  Chroma is the source of truth for RAG)
        self.collection.delete(where={"doc": doc_name})

        # 3. Re-run ingestion
        # We run it synchronously or background? Background is better for UI.
        # But for simplicity here, we'll let the threading happen in web_server 
        # calling `ingest_background`
        return pdf_path

ingest_service = IngestService()
