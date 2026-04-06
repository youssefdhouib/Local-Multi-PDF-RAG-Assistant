import logging
import asyncio
import shutil
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import existing functionality (path must be set correctly by uv run/python path)
# Assuming web_server.py is in 'PDF processing/' alongside features/ and rag_answer.py

try:
    from rag_answer import rag_answer
    from features.chroma_utils import list_docs
    from features.summarize import summarize_document, summarize_library
    from features.mcq_generator import generate_mcqs_for_document, generate_mcqs_for_library
    from ingest.service import ingest_service
    from features.router import classify_intent, chat_with_ollama
    from features.chroma_extensions import delete_document_from_chroma
except ImportError as e:
    logging.warning(f"Failed to import local modules: {e}. Check your python path.")
    # Dummy imports for testing/linting purpose if path is wrong
    def rag_answer(*args, **kwargs): return "Error: Backend not found", []
    def list_docs(*args, **kwargs): return []
    def summarize_document(*args, **kwargs): return {}
    def summarize_library(*args, **kwargs): return {}
    def generate_mcqs_for_document(*args, **kwargs): return []
    def generate_mcqs_for_library(*args, **kwargs): return []
    ingest_service = None


# --- Data Models ---

class ChatRequest(BaseModel):
    question: str
    doc_name: Optional[str] = None  # If None, query all docs
    top_k: int = 5

class Citation(BaseModel):
    id: str  # E1, E2...
    doc: str
    page: int
    chunk_index: int
    text_snippet: Optional[str] = None
    distance: float

class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]

class SummaryRequest(BaseModel):
    doc_name: Optional[str] = None  # Required for document specific summary

class SummaryResponse(BaseModel):
    title: str
    markdown: str
    # Simply list citations as objects
    citations: List[Dict[str, Any]]

class QuizRequest(BaseModel):
    doc_name: Optional[str] = None
    num_questions: int = 5

class DocActionRequest(BaseModel):
    doc_name: str

class MCQOption(BaseModel):
    text: str
    label: str # A, B, C, D

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

# Allow CORS for local dev frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Endpoints ---

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "Local RAG Assistant"}

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks

# ... (rest of imports)

@app.get("/api/documents")
async def get_documents():
    """List all indexed documents with status."""
    try:
        logging.info("GET /api/documents - starting")
        # Use ingest_service registry if available for status
        if ingest_service:
            logging.info("ingest_service available, calling get_all_docs()")
            docs_map = ingest_service.get_all_docs()
            logging.info(f"Got docs_map with {len(docs_map)} documents")
            # Convert dict to list
            docs = list(docs_map.values())
            logging.info(f"Returning {len(docs)} documents")
            # If registry is empty but chromadb has docs (legacy), we might want to merge?
            # For "Option A", we rely on registry as source of truth for UI.
            return {"documents": docs}
        else:
            logging.warning("ingest_service is None, returning empty list")
            # Fallback
            return {"documents": []}
    except Exception as e:
        logging.exception(f"Error in get_documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload a PDF file and ingest it into the RAG system in background."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    if ingest_service is None:
        raise HTTPException(status_code=503, detail="Ingest service not available on backend")

    filename = Path(file.filename).name
    
    # Compute SHA-256 Fingerprint
    try:
        file.file.seek(0)
        content = file.file.read()
        file_hash = hashlib.sha256(content).hexdigest()
        file.file.seek(0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute file hash: {e}")

    # Check for existing duplicate
    existing_doc = ingest_service.get_doc_by_fingerprint(file_hash)
    if existing_doc and existing_doc.get("status") == "ready":
         return {
             "message": f"Document already indexed as '{existing_doc['name']}'. Skipping ingestion.",
             "doc_name": existing_doc['name'],
             "status": "ready"
         }

    save_path = Path("data") / filename
    
    # Ensure data directory exists
    save_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Save uploaded file
        with save_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Register "indexing" status immediately (so UI sees it)
        ingest_service.update_status(filename, "indexing", fingerprint=file_hash)

        # Run Ingestion in Background
        background_tasks.add_task(ingest_service.ingest_background, save_path, filename)
        
        return {
            "message": f"Upload accepted. Indexing '{filename}' in background.", 
            "doc_name": filename,
            "status": "indexing"
        }
    except Exception as e:
        logging.exception("Upload failed")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/api/delete")
async def delete_document_endpoint(req: DocActionRequest):
    """Delete a document from index and disk."""
    try:
        if ingest_service:
            ingest_service.delete_doc(req.doc_name)
        else:
            # Fallback legacy delete
            delete_document_from_chroma(req.doc_name)
            
        return {"message": f"Deleted {req.doc_name}", "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

@app.post("/api/reindex")
async def reindex_document_endpoint(req: DocActionRequest, background_tasks: BackgroundTasks):
    """Re-index an existing document."""
    try:
        if ingest_service:
             # We need to find the file path. 
             # reindex_doc in service could return path or we calc it here.
             # Let's assume standard path:
             file_path = Path("data") / req.doc_name
             if not file_path.exists():
                 raise HTTPException(status_code=404, detail="File not found")
             
             # Set status
             ingest_service.update_status(req.doc_name, "indexing")
             
             # Clear old (synchronous ok for delete)
             ingest_service.delete_doc(req.doc_name)
             
             # Re-ingest background
             background_tasks.add_task(ingest_service.ingest_background, file_path, req.doc_name)
             
             return {"message": f"Re-indexing {req.doc_name} started", "status": "indexing"}
        else:
             raise HTTPException(status_code=503, detail="Ingest service unavailable")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Re-index failed: {str(e)}")


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Answer a question using RAG."""
    # Build 'where' filter if doc_name is provided
    where_clause = {"doc": req.doc_name} if req.doc_name else None


    # Determine intent
    try:
        # If specific doc is selected, we assume DOC intent unless it's explicitly chitchat
        # But generally if a doc is selected, user wants to query it. 
        # However, "hello" with a doc selected should still be chat.
        intent = classify_intent(req.question)
        
        if intent == "CHAT":
             # Route to direct LLM chat
             model = "llama3.2:latest" # Default, or make configurable
             ans = chat_with_ollama(req.question, model=model)
             return ChatResponse(answer=ans, citations=[])
        
        # Else DOC intent -> RAG
        answer, evidence_chunks = rag_answer(
            question=req.question,
            top_k=req.top_k,
            where=where_clause
            # using defaults for others (ollama_model etc.)
        )

        # Convert EvidenceChunk objects to Pydantic models
        citations_out = []
        for i, chunk in enumerate(evidence_chunks, start=1):
            citations_out.append(Citation(
                id=f"E{i}",
                doc=chunk.doc,
                page=chunk.page,
                chunk_index=chunk.chunk_index,
                text_snippet=chunk.text,
                distance=chunk.distance
            ))

        return ChatResponse(answer=answer, citations=citations_out)

    except Exception as e:
        logging.exception("Error in chat_endpoint")
        raise HTTPException(status_code=500, detail=f"RAG Error: {str(e)}")

@app.post("/api/summary/document", response_model=SummaryResponse)
async def summary_document_endpoint(req: SummaryRequest):
    if not req.doc_name:
        raise HTTPException(status_code=400, detail="doc_name is required for document summary")

    try:
        # returns SummaryResult(title, markdown, citations)
        res = summarize_document(doc_name=req.doc_name)
        return SummaryResponse(
            title=res.title,
            markdown=res.markdown,
            citations=res.citations
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/summary/library", response_model=SummaryResponse)
async def summary_library_endpoint():
    try:
        res = summarize_library()
        return SummaryResponse(
            title=res.title,
            markdown=res.markdown,
            citations=res.citations
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/quiz/document", response_model=QuizResponse)
async def quiz_document_endpoint(req: QuizRequest):
    if not req.doc_name:
        raise HTTPException(status_code=400, detail="doc_name is required")
    try:
        mcqs = generate_mcqs_for_document(doc_name=req.doc_name, n=req.num_questions)
        # mcqs is list of MCQ objects
        return QuizResponse(mcqs=[
            MCQItem(
                question=m.question,
                options=m.options,
                correct_index=m.correct_index,
                explanation=m.explanation,
                citations=m.citations
            ) for m in mcqs
        ])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/quiz/library", response_model=QuizResponse)
async def quiz_library_endpoint(req: QuizRequest):
    try:
        mcqs = generate_mcqs_for_library(n=req.num_questions)
        return QuizResponse(mcqs=[
            MCQItem(
                question=m.question,
                options=m.options,
                correct_index=m.correct_index,
                explanation=m.explanation,
                citations=m.citations
            ) for m in mcqs
        ])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    # Run API
    uvicorn.run(app, host="0.0.0.0", port=8000)
