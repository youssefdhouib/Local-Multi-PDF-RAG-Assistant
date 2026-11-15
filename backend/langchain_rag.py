"""
LangChain version of the document Q&A pipeline (Phase 4).

Same inputs and outputs as rag_answer.rag_answer(), so the API and the React
app do not change. This is the default engine; RAG_ENGINE=classic switches back
to the hand-written pipeline (rollback / comparison).

What LangChain does here:
  - Chroma vector store  -> reads the EXISTING index (no re-upload)
  - Embeddings interface -> wraps the SAME cached Sentence-Transformers model as ingestion
  - ChatPromptTemplate   -> system instructions + question + evidence
  - ChatOllama           -> the same local model as the classic pipeline
  - LCEL chain           -> prompt | llm | StrOutputParser()

What stays shared with the classic pipeline (rag_answer.py), so both engines
follow exactly the same rules: summary detection, relevance threshold,
refusal without sources, evidence formatting and the prompt instructions.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import ollama
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from features import embeddings
from features.chroma_utils import _client_for, get_collection
from features.ollama_client import OllamaError
from rag_answer import (
    ANSWER_INSTRUCTIONS, SUMMARY_INSTRUCTIONS,
    DEFAULT_CHROMA_DIR, DEFAULT_COLLECTION, DEFAULT_EMBED_MODEL,
    DEFAULT_OLLAMA_MODEL, DEFAULT_OLLAMA_URL, RELEVANCE_THRESHOLD,
    EvidenceChunk, _format_evidence, select_evidence,
)


class CachedSentenceTransformerEmbeddings(Embeddings):
    """LangChain Embeddings interface around the model ingestion already uses (loaded once)."""

    def __init__(self, model_name: str = DEFAULT_EMBED_MODEL):
        self.model_name = model_name

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return embeddings.get_embedder(self.model_name).encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> List[float]:
        return embeddings.get_embedder(self.model_name).encode(text, normalize_embeddings=True).tolist()


# The human message is the same for both prompts: the question and the evidence.
_HUMAN = "QUESTION:\n{question}\n\nEVIDENCE:\n{context}"
ANSWER_PROMPT = ChatPromptTemplate.from_messages([("system", ANSWER_INSTRUCTIONS), ("human", _HUMAN)])
SUMMARY_PROMPT = ChatPromptTemplate.from_messages([("system", SUMMARY_INSTRUCTIONS), ("human", _HUMAN)])


def get_vectorstore(chroma_dir: str, collection_name: str, embed_model_name: str) -> Chroma:
    get_collection(chroma_dir, collection_name)  # make sure it exists, with cosine distance
    return Chroma(
        client=_client_for(str(Path(chroma_dir).resolve())),  # same cached client as the app
        collection_name=collection_name,
        embedding_function=CachedSentenceTransformerEmbeddings(embed_model_name),
    )


def get_chat_model(model: str, base_url: str) -> ChatOllama:
    return ChatOllama(model=model, base_url=base_url, temperature=0.2, client_kwargs={"timeout": 120})


def retrieve_with_langchain(
    question: str,
    chroma_dir: str = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION,
    embed_model_name: str = DEFAULT_EMBED_MODEL,
    top_k: int = 6,
    where: Optional[Dict[str, Any]] = None,
) -> List[EvidenceChunk]:
    """Top-k chunks with their cosine distance, via the LangChain Chroma store."""
    store = get_vectorstore(chroma_dir, collection_name, embed_model_name)
    results = store.similarity_search_with_score(question, k=top_k, filter=where)
    return [
        EvidenceChunk(
            doc=d.metadata.get("doc", "unknown"),
            page=int(d.metadata.get("page", -1)),
            chunk_index=int(d.metadata.get("chunk_index", -1)),
            text=d.page_content,
            distance=float(score),
        )
        for d, score in results
    ]


def langchain_rag_answer(
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
    """Drop-in replacement for rag_answer() built with LangChain components."""
    evidence = retrieve_with_langchain(question, chroma_dir, collection_name, embed_model_name, top_k, where)

    refusal, evidence_used, is_summary = select_evidence(question, evidence, use_top_n_in_prompt, max_distance)
    if refusal:
        return refusal, []  # the LLM is not called at all

    prompt = SUMMARY_PROMPT if is_summary else ANSWER_PROMPT
    chain = prompt | get_chat_model(ollama_model, ollama_url) | StrOutputParser()

    try:
        answer = chain.invoke({"question": question, "context": _format_evidence(evidence_used)})
    except (httpx.ConnectError, ConnectionError):
        raise OllamaError(f"Cannot reach Ollama at {ollama_url}. Start it with `ollama serve` and try again.")
    except httpx.TimeoutException:
        raise OllamaError("Ollama did not answer within 120 seconds. Try again or use a smaller model.")
    except ollama.ResponseError as e:
        if e.status_code == 404:
            raise OllamaError(f"Model '{ollama_model}' is not available in Ollama. Run `ollama pull {ollama_model}`.")
        raise OllamaError(f"Ollama returned an error: {e}")

    return answer.strip(), evidence_used
