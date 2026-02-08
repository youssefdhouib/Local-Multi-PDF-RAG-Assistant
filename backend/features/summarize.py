from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
import requests

from features.chroma_utils import fetch_doc_chunks, fetch_library_sample

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"


@dataclass
class SummaryResult:
    title: str
    markdown: str
    citations: List[Dict[str, Any]]  # [{"doc","page","chunk_index","evidence_id"}]


def ollama_generate(prompt: str, model: str, ollama_url: str, temperature: float = 0.2) -> str:
    endpoint = ollama_url.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    r = requests.post(endpoint, json=payload, timeout=240)
    r.raise_for_status()
    return r.json().get("response", "").strip()


def format_evidence(
    items: List[Dict[str, Any]],
    max_chars_total: int = 14000
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Build evidence text with stable IDs [E1], [E2], ...
    Also returns citation objects aligned with those IDs.
    """
    parts = []
    cits: List[Dict[str, Any]] = []
    used = 0

    for i, it in enumerate(items, start=1):
        text = (it.get("text") or "").strip()
        meta = it.get("meta") or {}
        if not text:
            continue

        doc = meta.get("doc", "unknown")
        page = int(meta.get("page", -1))
        chunk_index = int(meta.get("chunk_index", -1))

        header = f"[E{i}] doc={doc} page={page} chunk={chunk_index}"
        block = header + "\n" + text

        if used + len(block) > max_chars_total:
            break

        parts.append(block)
        cits.append({"evidence_id": f"E{i}", "doc": doc, "page": page, "chunk_index": chunk_index})
        used += len(block)

    return "\n\n".join(parts), cits


def build_summary_prompt(title: str, evidence_text: str) -> str:
    return f"""You are a document-grounded assistant.

TASK:
Write a general-purpose, clear summary using ONLY the EVIDENCE.

RULES:
- Use ONLY the evidence. Do not add outside knowledge.
- If something is missing, say so briefly.
- Keep it structured and readable.
- End with: "Citations: [E1], [E2], ..." (only those you actually used).

OUTPUT FORMAT (Markdown):
# {title}
## Overview
## Key points
## Key terms / glossary
## Notable referenced pages (optional)

EVIDENCE:
{evidence_text}
"""


def summarize_document(
    doc_name: str,
    model: str = DEFAULT_OLLAMA_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    max_chunks: int = 40
) -> SummaryResult:
    items = fetch_doc_chunks(doc_name, max_chunks=max_chunks)
    evidence_text, citations = format_evidence(items)

    title = f"Summary — {doc_name}"
    if not evidence_text.strip():
        return SummaryResult(
            title=title,
            markdown=f"# {title}\n\nNo text chunks available for this document.",
            citations=[]
        )

    prompt = build_summary_prompt(title, evidence_text)
    md = ollama_generate(prompt, model=model, ollama_url=ollama_url, temperature=0.2)

    return SummaryResult(title=title, markdown=md, citations=citations)


def summarize_library(
    model: str = DEFAULT_OLLAMA_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    per_doc: int = 12
) -> SummaryResult:
    items = fetch_library_sample(per_doc=per_doc)
    evidence_text, citations = format_evidence(items)

    title = "Summary — Entire Library"
    if not evidence_text.strip():
        return SummaryResult(
            title=title,
            markdown=f"# {title}\n\nNo text chunks available in the library.",
            citations=[]
        )

    prompt = build_summary_prompt(title, evidence_text)
    md = ollama_generate(prompt, model=model, ollama_url=ollama_url, temperature=0.2)

    return SummaryResult(title=title, markdown=md, citations=citations)
