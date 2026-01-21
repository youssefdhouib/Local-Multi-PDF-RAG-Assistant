from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Iterable, Tuple
import re

# Good defaults for RAG
DEFAULT_TARGET_CHARS = 800
DEFAULT_OVERLAP_CHARS = 150

def clean_text(s: str) -> str:
    s = (s or "").replace("\r", "\n")
    # remove excessive spaces but keep paragraph breaks
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def split_paragraphs(text: str) -> List[str]:
    text = clean_text(text)
    if not text:
        return []
    # split on blank lines (paragraphs)
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts

def chunk_by_paragraphs(
    text: str,
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> List[str]:
    """
    Preferred chunker:
    - keeps paragraphs together (better meaning)
    - builds chunks up to target_chars
    - overlap by characters (implemented by reusing tail paragraphs)
    """
    paras = split_paragraphs(text)
    if not paras:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    def flush():
        nonlocal current, current_len
        if current:
            chunks.append(clean_text("\n\n".join(current)))
        current = []
        current_len = 0

    for p in paras:
        p_len = len(p)
        # If single paragraph is huge, fallback to sliding window on that paragraph
        if p_len > target_chars * 1.5:
            # flush current first
            flush()
            chunks.extend(chunk_sliding_window(p, target_chars, overlap_chars))
            continue

        # If adding would exceed target, flush
        if current and (current_len + 2 + p_len) > target_chars:
            flush()

        current.append(p)
        current_len += (2 + p_len)

    flush()

    # Overlap: rebuild chunks with overlap using previous chunk tail
    if overlap_chars > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = overlapped[-1]
            tail = prev[-overlap_chars:] if len(prev) > overlap_chars else prev
            overlapped.append(clean_text(tail + "\n" + chunks[i]))
        chunks = overlapped

    # Final safety: remove empty / tiny noise
    chunks = [c for c in chunks if len(c) >= 40]
    return chunks

def chunk_sliding_window(text: str, target_chars: int, overlap_chars: int) -> List[str]:
    """
    Fallback chunker for long uninterrupted text.
    """
    text = clean_text(text)
    if not text:
        return []
    chunks = []
    step = max(1, target_chars - overlap_chars)
    for start in range(0, len(text), step):
        chunk = text[start:start + target_chars].strip()
        if len(chunk) >= 40:
            chunks.append(chunk)
    return chunks

def normalize_to_pages(records: Iterable[Dict]) -> List[Dict]:
    """
    Make Step 2 output uniform:
    - Unstructured gives element-level records
    - Fallback gives PageText records
    We convert both into ONE record per (doc,page): {"doc","page","text",...}
    """
    buckets: Dict[Tuple[str, int], List[Dict]] = {}

    for r in records:
        doc = r.get("doc", "unknown")
        page = int(r.get("page", 0) or 0)

        # Some unstructured elements might have page=0; keep them but they’ll be grouped
        key = (doc, page)
        buckets.setdefault(key, []).append(r)

    pages = []
    for (doc, page), items in buckets.items():
        # Keep original order as in jsonl (already good enough)
        merged_text = "\n\n".join((it.get("text") or "").strip() for it in items if (it.get("text") or "").strip())
        merged_text = clean_text(merged_text)
        if not merged_text:
            continue

        # merge metadata
        sources = sorted(set(it.get("source", "unknown") for it in items))
        types = sorted(set(it.get("type", "unknown") for it in items))
        lang = next((it.get("lang") for it in items if it.get("lang") and it.get("lang") != "unknown"), "unknown")

        pages.append({
            "doc": doc,
            "page": page,
            "source": "+".join(sources),
            "types": types,   # keep types for debugging
            "lang": lang,
            "text": merged_text,
            "char_len": len(merged_text),
        })

    # sort pages: doc then page
    pages.sort(key=lambda x: (x["doc"], x["page"]))
    return pages

def build_chunks(
    pages: List[Dict],
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> List[Dict]:
    out = []
    for p in pages:
        chunks = chunk_by_paragraphs(p["text"], target_chars=target_chars, overlap_chars=overlap_chars)
        for i, c in enumerate(chunks):
            out.append({
                "chunk_id": f'{p["doc"]}_p{p["page"]}_c{i}',
                "doc": p["doc"],
                "page": p["page"],
                "chunk_index": i,
                "lang": p.get("lang", "unknown"),
                "source": p.get("source", "unknown"),
                "types": p.get("types", []),   # optional but useful
                "text": c,
                "char_len": len(c),
            })
    return out
