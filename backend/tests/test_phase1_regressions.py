"""
Regression tests for the Phase 1 fixes.

Every test runs inside its own temporary folder (pytest's tmp_path), so it
never touches real documents, registry.json or the real ChromaDB.

- The Sentence-Transformers model is replaced by a tiny bag-of-words
  embedder: shared words => similar vectors. Fast, deterministic, no download.
- Ollama is never called: tests either stub the generation step or simulate
  "Ollama is down".
"""
import hashlib
import re
import threading

import numpy as np
import pytest

fitz = pytest.importorskip("fitz")
pytest.importorskip("fastapi")
pytest.importorskip("chromadb")
requests = pytest.importorskip("requests")
from fastapi.testclient import TestClient  # noqa: E402


# ---------- helpers ----------

class FakeEmbedder:
    """Bag-of-words vectors: texts sharing words get a small cosine distance."""
    DIM = 256

    def _vec(self, text):
        v = np.zeros(self.DIM)
        for w in re.findall(r"[a-z]+", text.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.DIM] += 1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode(self, texts, normalize_embeddings=True):
        if isinstance(texts, str):
            return self._vec(texts)
        return np.array([self._vec(t) for t in texts])


def make_pdf(pages):
    """Build a PDF in memory. pages: list of page texts ("" = blank page)."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(fitz.Rect(50, 50, 550, 800), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def long_text(topic_words, n=40):
    # Enough text per page to pass the "weak page" threshold and form chunks.
    sentence = " ".join(topic_words) + "."
    return " ".join([sentence] * n)


PHOTO = long_text(["photosynthesis", "chlorophyll", "plants", "sunlight", "glucose", "leaves"])
ROMAN = long_text(["roman", "empire", "caesar", "legion", "senate", "rome"])
OCEAN = long_text(["ocean", "tides", "moon", "waves", "coral", "salt"])


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Fresh, isolated app: own data/, storage/ and Chroma folder per test."""
    monkeypatch.chdir(tmp_path)

    from features import embeddings
    monkeypatch.setattr(embeddings, "get_embedder", lambda *a, **k: FakeEmbedder())

    # Force the PyMuPDF path (fast, deterministic) and simulate a machine
    # WITHOUT Tesseract, so any OCR attempt fails.
    import ingest.router as ingest_router
    import ingest.custom_fallback as fallback

    def no_unstructured(*a, **k):
        raise ImportError("unstructured not available in tests")

    def no_tesseract(*a, **k):
        raise RuntimeError("tesseract is not installed or it's not in your PATH")

    monkeypatch.setattr(ingest_router, "partition_pdf_unstructured", no_unstructured)
    monkeypatch.setattr(fallback, "ocr_page", no_tesseract)

    import web_server
    from ingest.service import ingest_service
    ingest_service._ensure_storage()  # create storage/ inside this tmp folder

    # Default: router says DOC, LLM returns a fixed answer (no real Ollama).
    import rag_answer
    real_ollama_generate = rag_answer._ollama_generate
    monkeypatch.setattr(web_server, "classify_intent", lambda q: "DOC")
    monkeypatch.setattr(rag_answer, "_ollama_generate", lambda **kw: "STUB ANSWER")

    client = TestClient(web_server.app)
    return {"client": client, "service": ingest_service, "tmp": tmp_path,
            "real_ollama_generate": real_ollama_generate}


def upload(client, name, pdf_bytes):
    # TestClient runs background tasks before returning, so ingestion is done.
    return client.post("/api/upload", files={"file": (name, pdf_bytes, "application/pdf")})


def chroma_rows(service, doc):
    return service.collection.get(where={"doc": doc}, include=["documents", "metadatas"])


# ---------- reindex / delete ----------

def test_reindex_keeps_pdf_and_document_becomes_ready(env):
    client, service, tmp = env["client"], env["service"], env["tmp"]
    assert upload(client, "bio.pdf", make_pdf([PHOTO, PHOTO])).status_code == 200
    assert service.get_doc("bio.pdf")["status"] == "ready"

    r = client.post("/api/reindex", json={"doc_name": "bio.pdf"})
    assert r.status_code == 200, r.text

    assert (tmp / "data" / "bio.pdf").exists(), "re-index must not delete the PDF"
    doc = service.get_doc("bio.pdf")
    assert doc["status"] == "ready", doc
    assert doc["fingerprint"], "fingerprint should survive a re-index"
    assert len(chroma_rows(service, "bio.pdf")["ids"]) == doc["chunk_count"] > 0


def test_reindex_missing_file_returns_404_not_500(env):
    r = env["client"].post("/api/reindex", json={"doc_name": "nope.pdf"})
    assert r.status_code == 404


def test_delete_removes_vectors_registry_cache_and_file(env):
    client, service, tmp = env["client"], env["service"], env["tmp"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))
    upload(client, "rome.pdf", make_pdf([ROMAN]))

    r = client.post("/api/delete", json={"doc_name": "bio.pdf"})
    assert r.status_code == 200, r.text

    assert service.get_doc("bio.pdf") is None
    assert chroma_rows(service, "bio.pdf")["ids"] == []
    assert not (tmp / "data" / "bio.pdf").exists()
    assert "bio.pdf" not in (tmp / "storage" / "chunks.jsonl").read_text(encoding="utf-8")
    # the other document is untouched
    assert service.get_doc("rome.pdf")["status"] == "ready"
    assert len(chroma_rows(service, "rome.pdf")["ids"]) > 0


@pytest.mark.parametrize("bad_name", ["../secret.pdf", "..\\secret.pdf", "sub/secret.pdf", "web_server.py"])
def test_delete_rejects_paths_outside_data_folder(env, bad_name):
    secret = env["tmp"] / "secret.pdf"
    secret.write_bytes(b"%PDF-1.4 do not delete")
    r = env["client"].post("/api/delete", json={"doc_name": bad_name})
    assert r.status_code == 400
    assert secret.exists()


# ---------- upload ----------

def test_upload_rejects_non_pdf_content(env):
    client = env["client"]
    assert client.post("/api/upload", files={"file": ("notes.txt", b"hello", "text/plain")}).status_code == 400
    fake = client.post("/api/upload", files={"file": ("fake.pdf", b"just text", "application/pdf")})
    assert fake.status_code == 400
    assert "not a valid PDF" in fake.json()["detail"]
    assert env["service"].get_doc("fake.pdf") is None


def test_reupload_same_name_leaves_no_stale_chunks(env):
    client, service = env["client"], env["service"]
    upload(client, "notes.pdf", make_pdf([ROMAN, ROMAN, ROMAN]))
    old_count = service.get_doc("notes.pdf")["chunk_count"]

    upload(client, "notes.pdf", make_pdf([OCEAN]))  # new content, same name, fewer pages
    doc = service.get_doc("notes.pdf")
    rows = chroma_rows(service, "notes.pdf")

    assert doc["chunk_count"] < old_count
    assert len(rows["ids"]) == doc["chunk_count"], "old chunks must not survive"
    assert not any("caesar" in t for t in rows["documents"])


def test_pdf_with_blank_page_indexes_without_tesseract(env):
    # Before: a blank page triggered OCR, Tesseract was missing, and the whole
    # upload ended as "failed".
    upload(env["client"], "mixed.pdf", make_pdf([PHOTO, "", PHOTO]))
    doc = env["service"].get_doc("mixed.pdf")
    assert doc["status"] == "ready", doc
    pages = {m["page"] for m in chroma_rows(env["service"], "mixed.pdf")["metadatas"]}
    assert pages == {1, 3}


# ---------- retrieval / citations ----------

def test_relevant_question_cites_correct_document_and_page(env):
    client = env["client"]
    upload(client, "bio.pdf", make_pdf([ROMAN, PHOTO]))  # photosynthesis is on page 2
    upload(client, "ocean.pdf", make_pdf([OCEAN]))

    r = client.post("/api/chat", json={"question": "How do plants use sunlight and chlorophyll?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "STUB ANSWER"
    assert body["citations"], "a grounded answer must come with sources"
    top = body["citations"][0]
    assert (top["doc"], top["page"]) == ("bio.pdf", 2)


def test_unrelated_question_abstains_with_no_citations(env):
    client = env["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))

    r = client.post("/api/chat", json={"question": "What is the capital gains tax rate?"})
    assert r.status_code == 200
    body = r.json()
    assert "couldn't find" in body["answer"].lower()
    assert body["citations"] == [], "no sources should be shown for an abstention"


def test_question_before_any_upload_does_not_crash(env):
    r = env["client"].post("/api/chat", json={"question": "What is photosynthesis?"})
    assert r.status_code == 200, r.text
    assert r.json()["citations"] == []


def test_multi_document_selection_only_searches_selected_docs(env):
    client = env["client"]
    shared = long_text(["energy", "system", "process"])
    upload(client, "a.pdf", make_pdf([shared + " " + PHOTO]))
    upload(client, "b.pdf", make_pdf([shared + " " + ROMAN]))
    upload(client, "c.pdf", make_pdf([shared + " " + OCEAN]))

    r = client.post("/api/chat", json={"question": "energy system process", "doc_names": ["a.pdf", "b.pdf"], "top_k": 10})
    assert r.status_code == 200, r.text
    docs = {c["doc"] for c in r.json()["citations"]}
    assert docs and docs <= {"a.pdf", "b.pdf"}


def test_sources_only_include_chunks_that_pass_the_threshold(env):
    client = env["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))
    upload(client, "rome.pdf", make_pdf([ROMAN]))
    upload(client, "ocean.pdf", make_pdf([OCEAN]))

    r = client.post("/api/chat", json={"question": "How do plants use sunlight and chlorophyll?"})
    cits = r.json()["citations"]
    assert cits
    assert all(c["distance"] <= 0.75 for c in cits), cits
    assert {c["doc"] for c in cits} == {"bio.pdf"}


def test_router_saying_chat_is_overruled_when_documents_match(env, monkeypatch):
    import web_server
    monkeypatch.setattr(web_server, "classify_intent", lambda q: "CHAT")
    monkeypatch.setattr(web_server, "chat_with_ollama", lambda q: "MEMORY ANSWER")
    client = env["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))

    doc_q = client.post("/api/chat", json={"question": "Compare how plants use sunlight and chlorophyll"}).json()
    assert doc_q["answer"] == "STUB ANSWER" and doc_q["citations"], "must be answered from the documents"

    small_talk = client.post("/api/chat", json={"question": "hello there"}).json()
    assert small_talk == {"answer": "MEMORY ANSWER", "citations": []}


def test_ocr_uses_only_installed_languages(monkeypatch):
    import ingest.custom_fallback as fallback
    monkeypatch.setattr(fallback.pytesseract, "get_languages", lambda config="": ["eng", "osd"])
    assert fallback.usable_ocr_langs("fra+eng") == "eng"
    monkeypatch.setattr(fallback.pytesseract, "get_languages", lambda config="": ["eng", "fra", "osd"])
    assert fallback.usable_ocr_langs("fra+eng") == "fra+eng"


def test_build_where_filter(env):
    from web_server import build_where
    assert build_where(None, None) is None
    assert build_where("a.pdf", None) == {"doc": "a.pdf"}
    assert build_where(None, ["a.pdf"]) == {"doc": "a.pdf"}
    assert build_where(None, ["a.pdf", "b.pdf"]) == {"doc": {"$in": ["a.pdf", "b.pdf"]}}


# ---------- Ollama unavailable ----------

@pytest.fixture
def ollama_down(env, monkeypatch):
    """Real router + real generation code, but every HTTP call to Ollama is refused."""
    import rag_answer
    import web_server
    from features import ollama_client, router

    monkeypatch.setattr(web_server, "classify_intent", router.classify_intent)
    monkeypatch.setattr(rag_answer, "_ollama_generate", env["real_ollama_generate"])

    def refused(*a, **k):
        raise requests.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr(ollama_client.requests, "post", refused)
    return env


def test_chat_returns_503_with_clear_message_when_ollama_down(ollama_down):
    client = ollama_down["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))
    r = client.post("/api/chat", json={"question": "How do plants use sunlight?"})
    assert r.status_code == 503
    assert "ollama serve" in r.json()["detail"]
    # user data untouched
    assert ollama_down["service"].get_doc("bio.pdf")["status"] == "ready"


def test_quiz_and_summary_return_503_when_ollama_down(ollama_down):
    client = ollama_down["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))
    q = client.post("/api/quiz/document", json={"doc_name": "bio.pdf", "num_questions": 3})
    s = client.post("/api/summary/document", json={"doc_name": "bio.pdf"})
    assert q.status_code == 503 and "ollama serve" in q.json()["detail"]
    assert s.status_code == 503 and "ollama serve" in s.json()["detail"]


def test_ollama_client_reports_connection_refused():
    from features.ollama_client import generate, OllamaError
    with pytest.raises(OllamaError, match="ollama serve"):
        generate("hi", ollama_url="http://127.0.0.1:9", timeout=5)


# ---------- registry ----------

def test_concurrent_status_updates_are_not_lost(env):
    service = env["service"]
    threads = [threading.Thread(target=service.update_status, args=(f"d{i}.pdf", "indexing")) for i in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(service.get_all_docs()) == 25
