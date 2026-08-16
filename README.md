<div align="center">

# Local Multi-PDF RAG Assistant

**A fully local, citation-grounded question-answering assistant for your PDF knowledge base.**

Query, summarize, and quiz your documents — powered by a private RAG pipeline. No data ever leaves your machine.

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-1.4.1-4B0082)](https://www.trychroma.com/)
[![Ollama](https://img.shields.io/badge/Ollama-llama3.2-00AEEF)](https://ollama.com/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)

[![CI](https://github.com/youssefdhouib/Local-Multi-PDF-RAG-Assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/youssefdhouib/Local-Multi-PDF-RAG-Assistant/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/youssefdhouib/Local-Multi-PDF-RAG-Assistant/pulls)

</div>

---

## Highlights

- **Fully private & local** — extraction, embeddings, and generation all run on your machine (Ollama + Sentence-Transformers). Nothing is sent to the cloud.
- **Hybrid PDF ingestion** — Unstructured parsing with an automatic PyMuPDF + Tesseract OCR fallback for scanned or multilingual pages (EN/FR/AR/DE/ES).
- **Semantic chunking** — paragraph-aware chunks (~800 chars) with character-level overlap so context survives chunk boundaries.
- **Persistent vector index** — ChromaDB with HNSW + cosine distance, plus SHA-256 fingerprinting to prevent duplicate uploads.
- **Citation-grounded answers** — every response references `[E1]…[En]` with document, page, and chunk provenance; a relevance guardrail filters low-confidence retrieval to reduce hallucination.
- **Beyond Q&A** — structured document/library summaries, MCQ quiz generation, and Markdown / PDF export.
- **Intent-aware routing** — an LLM classifier sends small talk to chat mode and content questions to the RAG pipeline.
- **Modern UI** — React 19 + Tailwind CSS + shadcn/ui with dark-ready design and an onboarding flow.

## Demo

[![Watch the demo](docs/screenshots/demo_thumbnail.png)](docs/demo.mp4)

Add a short walkthrough to `docs/demo.mp4` — upload a PDF, chat with citations, generate a summary, and run a quiz. *(Thumbnail is a placeholder.)*

## Screenshots

<div align="center">
  <img src="docs/screenshots/chat.png" alt="Chat with citations" width="49%" />
  <img src="docs/screenshots/documents.png" alt="Document library" width="49%" />
  <img src="docs/screenshots/summary.png" alt="Structured summary" width="49%" />
  <img src="docs/screenshots/quiz.png" alt="MCQ quiz" width="49%" />
</div>

Replace the placeholders with your own captures in [`docs/screenshots/`](docs/screenshots/).

---

## How it works

```mermaid
flowchart LR
    U[User] --> UI[React + Tailwind UI]
    UI -->|REST /api| API[FastAPI Backend]
    API --> ING[Ingestion Pipeline]
    ING --> EX[Unstructured + OCR fallback]
    EX --> CH[Semantic Chunking]
    CH --> EM[Sentence-Transformers<br/>all-MiniLM-L6-v2]
    EM --> DB[(ChromaDB<br/>cosine HNSW)]
    UI --> Q[Query]
    Q --> RET[Top-k retrieval<br/>+ distance guardrail]
    RET --> DB
    RET --> LLM[Ollama llama3.2]
    LLM --> A[Answer + citations [E1..En]]
    A --> UI
```

1. **Ingest** — a PDF is parsed by Unstructured and automatically routed to an OCR pipeline (PyMuPDF + Tesseract) if a page is scanned or weak.
2. **Chunk** — pages are normalized and split into paragraph-aware chunks with overlap, preserving meaning and page provenance.
3. **Embed** — chunks are embedded with `all-MiniLM-L6-v2` (normalized) and upserted into a persistent ChromaDB collection.
4. **Retrieve** — a question is embedded and matched against the index; the top-`k` chunks pass a cosine distance guardrail.
5. **Answer** — Ollama `llama3.2` writes a Markdown answer grounded strictly in the retrieved evidence; the UI renders clickable citations.
6. **Extend** — the same evidence powers summaries, MCQs, and Markdown/PDF exports.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI · Uvicorn |
| Vector store | ChromaDB (persistent, cosine HNSW) |
| Embeddings | Sentence-Transformers `all-MiniLM-L6-v2` |
| LLM | Ollama — `llama3.2` (local) |
| PDF parsing | Unstructured · PyMuPDF · Tesseract OCR · langdetect |
| Frontend | React 19 · Vite · TypeScript · Tailwind CSS · shadcn/ui |
| Export | jsPDF / ReportLab · Markdown |

## Getting started

### Prerequisites

- **Python 3.12** and **Node.js ≥ 20**
- **Ollama** with Llama 3.2 pulled:

  ```bash
  ollama pull llama3.2
  ```

- **Tesseract OCR** installed and on your `PATH` (only needed for scanned PDFs).

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # macOS / Linux

pip install -r ../requirements.txt
uvicorn web_server:app --reload --port 8000
```

The API is now live at `http://localhost:8000` — interactive docs at [`http://localhost:8000/docs`](http://localhost:8000/docs). Drop PDFs into `backend/data/` or upload them from the UI.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [`http://localhost:5173`](http://localhost:5173) — the UI is wired to the backend at `http://localhost:8000`.

### 3. Test it

```bash
pytest                      # unit tests (backend/tests)
cd frontend && npm run lint && npm run build
```

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Service health check |
| `GET` | `/api/documents` | List indexed documents with status |
| `POST` | `/api/upload` | Upload + ingest a PDF (background) |
| `POST` | `/api/delete` | Remove a document from index & disk |
| `POST` | `/api/reindex` | Re-ingest an existing document |
| `POST` | `/api/chat` | RAG Q&A (or chat mode) with citations |
| `POST` | `/api/summary/document` | Structured summary of one document |
| `POST` | `/api/summary/library` | Summary across the whole library |
| `POST` | `/api/quiz/document` | MCQ quiz for one document |
| `POST` | `/api/quiz/library` | MCQ quiz across the library |

## Project structure

```
├── .github/workflows/       # CI: frontend lint + build, backend unit tests
├── backend/                 # Python RAG engine + FastAPI API
│   ├── ingest/              # Hybrid extraction (Unstructured + OCR), chunking, ingestion service
│   ├── features/            # Summaries, MCQ quiz, exports, intent router
│   ├── scripts/             # Ollama connectivity checks
│   ├── tests/               # Unit tests + manual integration scripts
│   ├── rag_answer.py        # Retrieval + grounded answer generation
│   └── web_server.py        # FastAPI application (the API layer)
├── frontend/                # React + Vite + TypeScript + Tailwind + shadcn/ui
│   └── src/
│       ├── pages/           # Chat, Documents, Summary, Quiz, Onboarding
│       ├── contexts/        # User / Document / Chat providers
│       └── lib/             # API client, Markdown & PDF export helpers
├── docs/                    # Demo video + screenshots
├── requirements.txt
└── README.md
```

## Roadmap

- [x] Hybrid PDF ingestion with OCR fallback
- [x] Persistent vector index with deduplication
- [x] Citation-grounded Q&A + intent router
- [x] Summaries, quizzes, Markdown/PDF export
- [ ] Streaming chat responses (SSE)
- [ ] Cross-encoder reranking for retrieval quality
- [ ] Docker Compose one-command setup
- [ ] Optional configurable embedding backend (local or API)

## Contributing

Contributions are welcome. Open an issue to discuss changes, then submit a pull request on a feature branch. Keep commit messages in [Conventional Commits](https://www.conventionalcommits.org/) style.

## License

Distributed under the [MIT License](LICENSE).