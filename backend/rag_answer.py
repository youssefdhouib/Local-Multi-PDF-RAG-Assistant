import requests
import chromadb
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from sentence_transformers import SentenceTransformer


# ---------------------------
# CONFIG
# ---------------------------
DEFAULT_CHROMA_DIR = "storage/chroma_db"
DEFAULT_COLLECTION = "pdf_chunks"
DEFAULT_EMBED_MODEL = "all-MiniLM-L6-v2"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"


@dataclass
class EvidenceChunk:
    doc: str
    page: int
    chunk_index: int
    text: str
    distance: float


def _format_evidence(chunks: List[EvidenceChunk]) -> str:
    """
    Context given to the LLM. We include stable IDs [E1], [E2], ...
    so citations are deterministic and auditable.
    """
    parts = []
    for i, c in enumerate(chunks, start=1):
        header = f"[E{i}] doc={c.doc} page={c.page} chunk={c.chunk_index} dist={c.distance:.4f}"
        parts.append(header + "\n" + c.text.strip())
    return "\n\n".join(parts)


def _build_prompt(question: str, evidence_text: str, n_evidence: int) -> str:
    """
    Consumer-facing prompt: no inline [E1] citations, just clean structured text.
    Attributes are handled by the UI via the evidence object.
    """
    return f"""You are a helpful, professional AI assistant.

INSTRUCTIONS:
1. **Structure**: Use Markdown headings (##) to organize your answer.
2. **Format**: Use short bullet points (one idea per bullet) for the main content.
3. ** terminology**: Normalize terms to standard Scrum concepts (e.g., use "Daily Scrum" instead of "Daily Meeting" if applicable).
4. **Content**: Answer ONLY using the EVIDENCE provided. Avoid repetition.
5. **Intro**: Start with a single, short introductory sentence.
6. **Closing**: End with a section titled "### Why this matters" explaining the practical importance of these points.
7. **Citations**: Do NOT use inline citations like [E1].

QUESTION:
{question}

EVIDENCE:
{evidence_text}

Answer:
"""


def _ollama_generate(
    prompt: str,
    model: str = DEFAULT_OLLAMA_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    temperature: float = 0.2,
) -> str:
    """
    Calls Ollama locally via HTTP API.
    Returns a friendly message if Ollama is not reachable.
    """
    url = ollama_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }

    try:
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return (
            "❌ Ollama server not reachable.\n"
            "Start it with: `ollama serve`\n"
            "Then retry."
        )
    except requests.exceptions.RequestException as e:
        return f"❌ Ollama request failed: {e}"


def retrieve_chunks(
    question: str,
    chroma_dir: str = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    embed_model_name: str = DEFAULT_EMBED_MODEL,
    top_k: int = 5,
    where: Optional[Dict[str, Any]] = None,
) -> List[EvidenceChunk]:
    """
    Retrieve top-k evidence chunks from Chroma for a given question.
    where can be: {"doc": "...pdf"} or {"lang": "fr"} etc.
    """
    embedder = SentenceTransformer(embed_model_name)
    q_emb = embedder.encode(question, normalize_embeddings=True).tolist()

    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_collection(collection_name)

    results = collection.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results.get("distances", [[None] * len(docs)])[0]

    evidence: List[EvidenceChunk] = []
    for text, meta, dist in zip(docs, metas, dists):
        evidence.append(
            EvidenceChunk(
                doc=meta.get("doc", "unknown"),
                page=int(meta.get("page", -1)),
                chunk_index=int(meta.get("chunk_index", -1)),
                text=text,
                distance=float(dist) if dist is not None else 999.0,
            )
        )
    return evidence


def rag_answer(
    question: str,
    chroma_dir: str = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    embed_model_name: str = DEFAULT_EMBED_MODEL,
    ollama_model: str = DEFAULT_OLLAMA_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    top_k: int = 6,
    use_top_n_in_prompt: int = 3,
    where: Optional[Dict[str, Any]] = None,
    max_distance: float = 0.75,
) -> Tuple[str, List[EvidenceChunk]]:
    """
    Full RAG:
    - retrieve evidence
    - guardrail: if best chunk is too weak, refuse
    - ONLY pass top-N best chunks to the LLM (to avoid messy citations)
    - return answer + evidence_used (for UI citations panel)
    """
    evidence = retrieve_chunks(
        question=question,
        chroma_dir=chroma_dir,
        collection_name=collection_name,
        embed_model_name=embed_model_name,
        top_k=top_k,
        where=where,
    )

    if not evidence:
        return "I don't know based on the provided documents.", []

    # sort best-first (lower distance = better match)
    evidence_sorted = sorted(evidence, key=lambda x: x.distance)
    best = evidence_sorted[0].distance
    print(f"DEBUG: Best chunk distance: {best}")

    # SUMMARY INTENT DETECTION
    summary_keywords = [
        "core idea", "key points", "main points", "overview", "aspects", 
        "résumé", "idée générale", "summarize", "summary"
    ]
    is_summary = any(kw in question.lower() for kw in summary_keywords)
    
    # Adjust parameters for summary
    if is_summary:
        print("DEBUG: Summary intent detected using specific summary prompt.")
        use_top_n_in_prompt = 10 # Allow more context
        max_distance = 1.0       # Relax guardrail significantly for summaries
    
    # hallucination guard
    if best > max_distance:
        print(f"DEBUG: Guardrail triggered. Best {best} > {max_distance}")
        return "I don't know based on the provided documents (relevance too low).", evidence_sorted[:use_top_n_in_prompt]

    # only strongest chunks go into prompt
    evidence_used = evidence_sorted[:use_top_n_in_prompt]

    evidence_text = _format_evidence(evidence_used)
    
    if is_summary:
        prompt = _build_summary_prompt(question, evidence_text)
    else:
        prompt = _build_prompt(question, evidence_text, n_evidence=len(evidence_used))

    print(f"DEBUG PROMPT (first 2000 chars):\n{prompt[:2000]}")

    answer = _ollama_generate(
        prompt=prompt,
        model=ollama_model,
        ollama_url=ollama_url,
        temperature=0.2,
    )

    return answer, evidence_used

def _build_summary_prompt(question: str, evidence_text: str) -> str:
    return f"""You are a helpful assistant summarizing document content.
    
INSTRUCTIONS:
1. **Structure**: Use Markdown headings (##) for main sections.
2. **Format**: Use short bullet points for key takeaways.
3. **Content**: Synthesize the core ideas from the excerpts below.
4. **Resilience**: If text is fragmented, piece together the context. Do NOT refuse to answer.
5. **Closing**: End with a section "### Key Implication" or "### Why this matters".

QUESTION:
{question}

EVIDENCE:
{evidence_text}

Answer:
"""
