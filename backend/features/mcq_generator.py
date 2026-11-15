from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
import json
import re

from features import ollama_client
from features.chroma_utils import fetch_doc_chunks, fetch_library_sample

DEFAULT_OLLAMA_URL = ollama_client.OLLAMA_URL
DEFAULT_OLLAMA_MODEL = ollama_client.OLLAMA_MODEL


@dataclass
class MCQ:
    question: str
    options: List[str]          # length 4
    correct_index: int          # 0..3
    explanation: str
    citations: List[Dict[str, Any]]  # [{"doc","page","chunk_index","evidence_id"}]


def ollama_generate(prompt: str, system: str, model: str, ollama_url: str, temperature: float = 0.2) -> str:
    # format=json asks Ollama for valid JSON; num_ctx keeps the context small.
    # Raises ollama_client.OllamaError (-> HTTP 503) if Ollama is unavailable.
    return ollama_client.generate(
        prompt,
        model=model,
        system=system,
        temperature=temperature,
        timeout=300,
        json_format=True,
        extra_options={"num_ctx": 4096},
        ollama_url=ollama_url,
    )


def format_evidence(
    items: List[Dict[str, Any]],
    max_chars_total: int = 4500  # Drastically reduced to prevent distraction
) -> Tuple[str, List[Dict[str, Any]]]:
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
        # chunk_index = int(meta.get("chunk_index", -1)) 

        # Simplified header to save tokens
        block = f"[ID:E{i}] {text}"

        if used + len(block) > max_chars_total:
            break

        parts.append(block)
        cits.append({"evidence_id": f"E{i}", "doc": doc, "page": page, "chunk_index": int(meta.get("chunk_index", -1))})
        used += len(block)

    return "\n\n".join(parts), cits


def build_mcq_prompt(n: int, evidence_text: str) -> Tuple[str, str]:
    """Returns (system_prompt, user_prompt)"""
    
    system_prompt = """You are a Quiz API that outputs JSON only. 
Strict Rules:
1. Output MUST be a valid JSON object {"mcqs": [...]}. 
2. Do not include any text outside the JSON.
3. Generate valid questions based strictly on the provided text.
4. Write the questions in the same language as the TEXT (English text -> English questions, French text -> French questions)."""

    user_prompt = f"""Generate {n} multiple-choice questions (MCQs) based on this text:

TEXT:
{evidence_text}

JSON SCHEMA:
{{
  "mcqs": [
    {{
      "question": "Question?",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "Explanation",
      "evidence_ids": ["E1"]
    }}
  ]
}}
"""
    return system_prompt, user_prompt


def _extract_json(text: str) -> Optional[dict]:
    # ... (existing robust extraction) ...
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) > 2:
            if lines[0].startswith("```"): lines = lines[1:]
            if lines[-1].startswith("```"): lines = lines[:-1]
            text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
             return json.loads(text[start : end + 1])
    except Exception:
        pass

    return None

# ... (omitted) ...

def _normalize_mcqs(raw: dict, evidence_map: Dict[str, Dict[str, Any]]) -> List[MCQ]:
    out: List[MCQ] = []
    
    # Handle if the LLM returned a list directly instead of {"mcqs": [...]}
    if isinstance(raw, list):
        mcqs = raw
    else:
        mcqs = raw.get("mcqs", [])

    if not isinstance(mcqs, list):
        return out

    for item in mcqs:
        if not isinstance(item, dict):
            continue

        q = str(item.get("question", "")).strip()
        opts = item.get("options", [])
        ci = item.get("correct_index", None)
        exp = str(item.get("explanation", "")).strip()
        eids = item.get("evidence_ids", [])

        # Validate structure
        if not q:
            continue
        if not isinstance(opts, list) or len(opts) < 2: 
            continue
        
        # Validate correct_index
        try:
            ci = int(ci)
        except (ValueError, TypeError):
            continue
            
        if ci < 0 or ci >= len(opts):
            continue

        citations: List[Dict[str, Any]] = []
        if isinstance(eids, list):
            for eid in eids:
                eid = str(eid).strip()
                if eid in evidence_map:
                    citations.append(evidence_map[eid])

        out.append(MCQ(
            question=q,
            options=[str(x) for x in opts],
            correct_index=ci,
            explanation=exp,
            citations=citations
        ))

    return out


import random

def generate_mcqs_for_document(
    doc_name: str,
    n: int = 5,
    model: str = DEFAULT_OLLAMA_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    max_chunks: int = 50
) -> List[MCQ]:
    # Fetch ALL chunks (pass None for max_chunks) to ensure we can sample from the whole doc
    items = fetch_doc_chunks(doc_name, max_chunks=None)
    if not items:
         return []
    
    # Randomize inputs to get different questions each time
    random.shuffle(items)
         
    evidence_text, citations = format_evidence(items)

    if not evidence_text.strip():
        return []

    evidence_map = {c["evidence_id"]: c for c in citations}

    sys_p, user_p = build_mcq_prompt(n, evidence_text)
    
    # Retry loop
    for attempt in range(2):
        try:
            print(f"DEBUG: Generating Quiz (Attempt {attempt+1})...")
            raw_text = ollama_generate(
                prompt=user_p, 
                system=sys_p, 
                model=model, 
                ollama_url=ollama_url, 
                temperature=0.2
            )
            
            print(f"DEBUG: Raw LLM Response length: {len(raw_text)}")
            print(f"DEBUG: Raw LLM Response preview: {raw_text[:500]}...") # Print first 500 chars

            raw_json = _extract_json(raw_text)
            if not raw_json:
                print("DEBUG: JSON extraction failed.")
                continue
            
            print(f"DEBUG: JSON extracted. Keys: {raw_json.keys()}")
            
            res = _normalize_mcqs(raw_json, evidence_map)
            print(f"DEBUG: Normalized MCQs count: {len(res)}")
            
            if res: 
                return res
            else:
                print("DEBUG: Normalization resulted in 0 valid MCQs.")

        except ollama_client.OllamaError:
            raise  # Ollama is down / model missing: retrying won't help, report it.
        except Exception as e:
            print(f"Attempt {attempt} failed with error: {e}")
            
    print("DEBUG: All attempts failed.")
    return []

def generate_mcqs_for_library(
     n: int = 8,
    model: str = DEFAULT_OLLAMA_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    per_doc: int = 12
) -> List[MCQ]:
    print("DEBUG: Generating Library Quiz...")
    items = fetch_library_sample(per_doc=per_doc)
    if not items: 
        print("DEBUG: No library items found.")
        return []

    evidence_text, citations = format_evidence(items)
    print(f"DEBUG: Library Evidence length: {len(evidence_text)}")
    if not evidence_text.strip(): 
        return []

    evidence_map = {c["evidence_id"]: c for c in citations}

    sys_p, user_p = build_mcq_prompt(n, evidence_text)
    
    try:
        raw_text = ollama_generate(user_p, sys_p, model, ollama_url)
        print(f"DEBUG: Library Raw Response: {raw_text[:200]}...")
        
        raw_json = _extract_json(raw_text)
        if not raw_json: 
            print("DEBUG: Library JSON extraction failed.")
            return []

        res = _normalize_mcqs(raw_json, evidence_map)
        print(f"DEBUG: Library Normalized MCQs: {len(res)}")
        return res
    except ollama_client.OllamaError:
        raise
    except Exception as e:
        print(f"DEBUG: Library generation failed: {e}")
        return []
