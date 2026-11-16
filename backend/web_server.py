import logging
import hashlib
import os
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Run from the backend/ folder:  uvicorn web_server:app --port 8000
# No try/except here on purpose: if a module is missing, the server must fail
# at startup with the real ImportError instead of serving fake "dummy" answers.
from rag_answer import rag_answer, has_relevant_evidence
from langchain_rag import langchain_rag_answer
from graph_rag import graph_answer
from features.summarize import summarize_document, summarize_library
from features.mcq_generator import generate_mcqs_for_document, generate_mcqs_for_library
from features.router import classify_intent, chat_with_ollama
from features.ollama_client import OllamaError
from ingest.service import ingest_service, safe_pdf_path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "50"))

# Which document Q&A pipeline answers /api/chat:
#   langchain = built with LangChain components (langchain_rag.py), the default
#   classic   = same rules, hand-written pipeline (rag_answer.py); kept for rollback and comparison
#   langgraph = LangGraph workflow with tool calling and one retrieval retry (graph_rag.py)
RAG_ENGINES = {"classic": rag_answer, "langchain": langchain_rag_answer, "langgraph": graph_answer}
DEFAULT_RAG_ENGINE = "langchain"
RAG_ENGINE = os.environ.get("RAG_ENGINE", DEFAULT_RAG_ENGINE)
if RAG_ENGINE not in RAG_ENGINES:
    raise ValueError(f"RAG_ENGINE must be one of {list(RAG_ENGINES)}, got {RAG_ENGINE!r}")


# --- Data Models ---

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    doc_name: Optional[str] = None          # one document (kept for compatibility)
    doc_names: Optional[List[str]] = None   # several selected documents
    top_k: int = Field(default=5, ge=1, le=20)

class Citation(BaseModel):
    id: str  # E1, E2...
    doc: str
    page: int
    chunk_index: int
    text_snippet: Optional[str] = None
    distance: Optional[float] = None  # None for summary/quiz sources (not found by a search)

class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]

class SummaryRequest(BaseModel):
    doc_name: Optional[str] = None  # Required for document specific summary

class SummaryResponse(BaseModel):
    title: str
    markdown: str
    citations: List[Dict[str, Any]]

class QuizRequest(BaseModel):
    doc_name: Optional[str] = None
    num_questions: int = Field(default=5, ge=1, le=20)

class DocActionRequest(BaseModel):
    doc_name: str

class MCQItem(BaseModel):
    question: str
    options: List[str]
    correct_index: int
    explanation: str
    citations: List[Dict[str, Any]]

class QuizResponse(BaseModel):
    mcqs: List[MCQItem]


# --- App Setup ---

app = FastAPI(title="Local RAG API", version="1.0.0")

# Only the local Vite dev server may call the API from a browser. With "*",
# any website open in the same browser could call /api/delete on localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(OllamaError)
async def ollama_error_handler(request: Request, exc: OllamaError):
    # The LLM is unavailable: 503 + a message telling the user what to do.
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def _validated_doc_name(doc_name: str) -> str:
    try:
        safe_pdf_path(doc_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return doc_name


def build_where(doc_name: Optional[str], doc_names: Optional[List[str]]) -> Optional[Dict[str, Any]]:
    """Chroma metadata filter for the selected documents (None = whole library)."""
    names = [n for n in (doc_names or []) if n]
    if doc_name and doc_name not in names:
        names.append(doc_name)
    if not names:
        return None
    if len(names) == 1:
        return {"doc": names[0]}
    return {"doc": {"$in": names}}


# --- Endpoints ---
# Endpoints are plain `def` (not `async def`): they call blocking code
# (embedding model, Chroma, HTTP to Ollama). FastAPI runs `def` endpoints in a
# thread pool, so one slow LLM call no longer freezes the whole server.

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Local RAG Assistant", "rag_engine": RAG_ENGINE}


@app.get("/api/documents")
def get_documents():
    """List all indexed documents with status (registry is the source of truth for the UI)."""
    docs_map = ingest_service.get_all_docs()
    return {"documents": list(docs_map.values())}


@app.post("/api/upload")
def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload a PDF file and ingest it into the RAG system in background."""
    filename = os.path.basename((file.filename or "").replace("\\", "/"))
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    _validated_doc_name(filename)

    content = file.file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is larger than {MAX_UPLOAD_MB} MB")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="This file is not a valid PDF (missing %PDF header)")

    file_hash = hashlib.sha256(content).hexdigest()

    # Same bytes already indexed (possibly under another name) -> skip
    existing_doc = ingest_service.get_doc_by_fingerprint(file_hash)
    if existing_doc and existing_doc.get("status") == "ready":
        return {
            "message": f"Document already indexed as '{existing_doc['name']}'. Skipping ingestion.",
            "doc_name": existing_doc['name'],
            "status": "ready"
        }

    current = ingest_service.get_doc(filename)
    if current and current.get("status") == "indexing":
        raise HTTPException(status_code=409, detail=f"'{filename}' is already being indexed. Wait for it to finish.")

    save_path = safe_pdf_path(filename)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(content)

    # Register "indexing" status immediately (so UI sees it)
    ingest_service.update_status(filename, "indexing", fingerprint=file_hash)
    background_tasks.add_task(ingest_service.ingest_background, save_path, filename)

    return {
        "message": f"Upload accepted. Indexing '{filename}' in background.",
        "doc_name": filename,
        "status": "indexing"
    }


@app.post("/api/delete")
def delete_document_endpoint(req: DocActionRequest):
    """Delete a document from index and disk."""
    doc_name = _validated_doc_name(req.doc_name)
    if ingest_service.get_doc(doc_name) is None and not safe_pdf_path(doc_name).exists():
        raise HTTPException(status_code=404, detail=f"Document '{doc_name}' not found")
    try:
        ingest_service.delete_doc(doc_name)
    except Exception as e:
        logging.exception("Delete failed")
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    return {"message": f"Deleted {doc_name}", "status": "success"}


@app.post("/api/reindex")
def reindex_document_endpoint(req: DocActionRequest, background_tasks: BackgroundTasks):
    """
    Re-index an existing document.

    Bug fixed: this used to call delete_doc(), which also deleted the PDF from
    disk, so the background re-ingestion always failed and the file was lost.
    Now we keep the PDF; ingest_background() clears the old chunks itself.
    """
    doc_name = _validated_doc_name(req.doc_name)
    file_path = safe_pdf_path(doc_name)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF file for '{doc_name}' not found on disk")

    current = ingest_service.get_doc(doc_name)
    if current and current.get("status") == "indexing":
        raise HTTPException(status_code=409, detail=f"'{doc_name}' is already being indexed")

    ingest_service.update_status(doc_name, "indexing")
    background_tasks.add_task(ingest_service.ingest_background, file_path, doc_name)
    return {"message": f"Re-indexing {doc_name} started", "status": "indexing"}


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """Route the question (CHAT vs DOC) and answer it, with RAG for DOC."""
    where_clause = build_where(req.doc_name, req.doc_names)

    try:
        if RAG_ENGINE == "langgraph":
            # The graph does its own routing (tool choice + safety check): no CHAT/DOC router here.
            answer, evidence_chunks = graph_answer(question=req.question, top_k=req.top_k, where=where_clause)
            return ChatResponse(answer=answer, citations=_citations(evidence_chunks))

        intent = classify_intent(req.question)

        # The small LLM router sometimes labels a real document question as CHAT,
        # which produced answers from the model's memory with no sources. If the
        # documents clearly contain a match, we answer from them instead.
        if intent == "CHAT" and has_relevant_evidence(req.question, where_clause):
            intent = "DOC"

        if intent == "CHAT":
            ans = chat_with_ollama(req.question)
            return ChatResponse(answer=ans, citations=[])

        # DOC intent -> RAG, with the engine chosen by RAG_ENGINE (same inputs and outputs)
        answer, evidence_chunks = RAG_ENGINES[RAG_ENGINE](
            question=req.question,
            top_k=req.top_k,
            where=where_clause,
        )
    except OllamaError:
        raise  # handled above -> 503
    except Exception as e:
        logging.exception("Error in chat_endpoint")
        raise HTTPException(status_code=500, detail=f"RAG Error: {e}")

    return ChatResponse(answer=answer, citations=_citations(evidence_chunks))


def _citations(evidence_chunks) -> List[Citation]:
    return [
        Citation(
            id=f"E{i}",
            doc=chunk.doc,
            page=chunk.page,
            chunk_index=chunk.chunk_index,
            text_snippet=chunk.text,
            distance=chunk.distance,
        )
        for i, chunk in enumerate(evidence_chunks, start=1)
    ]


@app.post("/api/summary/document", response_model=SummaryResponse)
def summary_document_endpoint(req: SummaryRequest):
    if not req.doc_name:
        raise HTTPException(status_code=400, detail="doc_name is required for document summary")
    res = summarize_document(doc_name=req.doc_name)
    return SummaryResponse(title=res.title, markdown=res.markdown, citations=res.citations)


@app.post("/api/summary/library", response_model=SummaryResponse)
def summary_library_endpoint():
    res = summarize_library()
    return SummaryResponse(title=res.title, markdown=res.markdown, citations=res.citations)


def _quiz_response(mcqs) -> QuizResponse:
    if not mcqs:
        # Before: 200 with an empty list, which the quiz page could not display.
        raise HTTPException(
            status_code=502,
            detail="The model did not return valid quiz questions (or there is no indexed text). Please try again.",
        )
    return QuizResponse(mcqs=[
        MCQItem(
            question=m.question,
            options=m.options,
            correct_index=m.correct_index,
            explanation=m.explanation,
            citations=m.citations
        ) for m in mcqs
    ])


@app.post("/api/quiz/document", response_model=QuizResponse)
def quiz_document_endpoint(req: QuizRequest):
    if not req.doc_name:
        raise HTTPException(status_code=400, detail="doc_name is required")
    return _quiz_response(generate_mcqs_for_document(doc_name=req.doc_name, n=req.num_questions))


@app.post("/api/quiz/library", response_model=QuizResponse)
def quiz_library_endpoint(req: QuizRequest):
    return _quiz_response(generate_mcqs_for_library(n=req.num_questions))


if __name__ == "__main__":
    import uvicorn
    # Bind to localhost only: this API has no authentication.
    uvicorn.run(app, host="127.0.0.1", port=8000)
