import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple

from features import embeddings, ollama_client
from features.chroma_utils import get_collection


# ---------------------------
# CONFIG
# ---------------------------
DEFAULT_CHROMA_DIR = "storage/chroma_db"
DEFAULT_COLLECTION = "pdf_chunks"
DEFAULT_EMBED_MODEL = embeddings.EMBED_MODEL_NAME
DEFAULT_OLLAMA_URL = ollama_client.OLLAMA_URL
DEFAULT_OLLAMA_MODEL = ollama_client.OLLAMA_MODEL

NO_EVIDENCE_ANSWER = "I don't know based on the provided documents."

# Cosine distance above which a chunk is "not relevant enough" (0 = identical, 2 = opposite).
RELEVANCE_THRESHOLD = 0.75
LOW_RELEVANCE_ANSWER = (
    "I couldn't find this in your documents. The closest passages were not "
    "relevant enough to answer reliably, so I won't guess."
)

logger = logging.getLogger(__name__)


@dataclass
class EvidenceChunk:
    doc: str
    page: int
    chunk_index: int
    text: str
    distance: Optional[float]  # None for summary/quiz sources (not found by a search)


def _format_evidence(chunks: List[EvidenceChunk]) -> str:
    """
    Context given to the LLM. We include stable IDs [E1], [E2], ...
    so the evidence list is deterministic and auditable.
    """
    parts = []
    for i, c in enumerate(chunks, start=1):
        header = f"[E{i}] doc={c.doc} page={c.page} chunk={c.chunk_index} dist={c.distance:.4f}"
        parts.append(header + "\n" + c.text.strip())
    return "\n\n".join(parts)


# Prompt instructions, shared by the classic pipeline and the LangChain pipeline
# (langchain_rag.py) so both engines ask the model for exactly the same thing.
ANSWER_INSTRUCTIONS = """You are a helpful, professional AI assistant.

INSTRUCTIONS:
- Answer ONLY using the EVIDENCE below. Do not add outside knowledge.
- If the EVIDENCE does not contain the answer, reply exactly "I don't know based on the provided documents." and stop.
- Start with one short sentence that answers the question directly.
- Then give the details as short Markdown bullet points (one idea per bullet).
- End with a short "### Why this matters" section.
- Do not repeat these instructions, and do not write inline references like [E1]."""

SUMMARY_INSTRUCTIONS = """You are a helpful assistant summarizing document content.

INSTRUCTIONS:
1. **Structure**: Use Markdown headings (##) for main sections.
2. **Format**: Use short bullet points for key takeaways.
3. **Content**: Synthesize the core ideas from the excerpts below. Use only these excerpts.
4. **Resilience**: If text is fragmented, piece together the context.
5. **Closing**: End with a section "### Key Implication" or "### Why this matters"."""


def _build_prompt(question: str, evidence_text: str, n_evidence: int) -> str:
    """
    Consumer-facing prompt: no inline [E1] citations, just clean structured text.
    Sources are shown by the UI from the returned evidence list.
    """
    return f"""{ANSWER_INSTRUCTIONS}

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
    """Calls Ollama. Raises ollama_client.OllamaError if it is unreachable."""
    return ollama_client.generate(
        prompt, model=model, ollama_url=ollama_url, temperature=temperature, timeout=120
    )


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
    where can be: {"doc": "a.pdf"} or {"doc": {"$in": ["a.pdf", "b.pdf"]}}.
    """
    embedder = embeddings.get_embedder(embed_model_name)  # cached, loaded once
    q_emb = embedder.encode(question, normalize_embeddings=True).tolist()

    collection = get_collection(chroma_dir, collection_name)

    results = collection.query(
        query_embeddings=[q_emb],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    docs = results["documents"][0] if results.get("documents") else []
    metas = results["metadatas"][0] if results.get("metadatas") else []
    dists = results["distances"][0] if results.get("distances") else [None] * len(docs)

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


def has_relevant_evidence(question: str, where: Optional[Dict[str, Any]] = None) -> bool:
    """
    Quick check without the LLM: is there at least one chunk close enough to answer from?
    Used to overrule the router when it wrongly labels a document question as small talk.
    """
    best = retrieve_chunks(question, top_k=1, where=where)
    return bool(best) and best[0].distance <= RELEVANCE_THRESHOLD


SUMMARY_KEYWORDS = [
    "core idea", "key points", "main points", "overview", "aspects",
    "résumé", "idée générale", "summarize", "summary"
]


def select_evidence(
    question: str,
    evidence: List[EvidenceChunk],
    use_top_n_in_prompt: int,
    max_distance: float,
) -> Tuple[Optional[str], List[EvidenceChunk], bool]:
    """
    The relevance rules, shared by both engines (classic and LangChain):
    - summary-style questions get more context and a relaxed threshold
    - if the best chunk is too far away: refuse (and return NO sources)
    - otherwise keep the top-N chunks that pass the threshold

    Returns (refusal_answer or None, evidence_to_use, is_summary).
    """
    if not evidence:
        return NO_EVIDENCE_ANSWER, [], False

    # sort best-first (lower cosine distance = better match)
    evidence_sorted = sorted(evidence, key=lambda x: x.distance)
    best = evidence_sorted[0].distance
    logger.info("Best chunk distance: %.4f", best)

    is_summary = any(kw in question.lower() for kw in SUMMARY_KEYWORDS)
    if is_summary:
        use_top_n_in_prompt = 10  # Allow more context
        max_distance = 1.0        # Relax guardrail for summaries

    # Relevance guardrail: abstain instead of answering from unrelated text.
    if best > max_distance:
        logger.info("Guardrail triggered: best %.4f > %.2f", best, max_distance)
        return LOW_RELEVANCE_ANSWER, [], is_summary

    # Only the strongest chunks that ALSO pass the threshold go into the prompt
    # (and therefore into the sources shown to the user).
    used = [e for e in evidence_sorted[:use_top_n_in_prompt] if e.distance <= max_distance]
    return None, used, is_summary


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
    max_distance: float = RELEVANCE_THRESHOLD,
) -> Tuple[str, List[EvidenceChunk]]:
    """
    Full RAG:
    - retrieve evidence
    - guardrail: if the best chunk is too far away, abstain (and return NO citations)
    - ONLY pass top-N best chunks to the LLM
    - return answer + evidence actually given to the LLM (for the UI sources panel)
    """
    evidence = retrieve_chunks(
        question=question,
        chroma_dir=chroma_dir,
        collection_name=collection_name,
        embed_model_name=embed_model_name,
        top_k=top_k,
        where=where,
    )

    refusal, evidence_used, is_summary = select_evidence(question, evidence, use_top_n_in_prompt, max_distance)
    if refusal:
        return refusal, []

    evidence_text = _format_evidence(evidence_used)

    if is_summary:
        prompt = _build_summary_prompt(question, evidence_text)
    else:
        prompt = _build_prompt(question, evidence_text, n_evidence=len(evidence_used))

    logger.debug("Prompt (first 2000 chars):\n%s", prompt[:2000])

    answer = _ollama_generate(
        prompt=prompt,
        model=ollama_model,
        ollama_url=ollama_url,
        temperature=0.2,
    )

    return answer, evidence_used


def _build_summary_prompt(question: str, evidence_text: str) -> str:
    return f"""{SUMMARY_INSTRUCTIONS}

QUESTION:
{question}

EVIDENCE:
{evidence_text}

Answer:
"""
