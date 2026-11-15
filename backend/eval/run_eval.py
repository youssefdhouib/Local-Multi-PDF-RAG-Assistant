"""
Small end-to-end evaluation of the RAG pipeline (real embeddings, real Chroma, real Ollama).

    cd backend
    python eval/run_eval.py            # uses OLLAMA_MODEL (default qwen2.5:3b)

It indexes eval/sample_pdfs/ into a TEMPORARY folder (your real data/ and storage/
are never touched) and measures:
  - retrieval hit@1 / hit@3 : is the page that contains the answer the top source / among the sources?
  - answer accuracy         : does the answer contain the expected fact?
  - false refusals          : in-scope questions the app refused to answer
  - correct refusals        : out-of-scope questions the app refused (no made-up answer)
  - routing accuracy        : CHAT vs DOC decision (LLM router + document check)
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent))  # backend/

work = Path(tempfile.mkdtemp(prefix="rag_eval_"))
os.chdir(work)  # the app stores data/ and storage/ relative to the current folder

from ingest.service import ingest_service, safe_pdf_path        # noqa: E402
from rag_answer import rag_answer, has_relevant_evidence        # noqa: E402
from features.router import classify_intent                     # noqa: E402
from features.ollama_client import OLLAMA_MODEL                 # noqa: E402

REFUSAL_MARKERS = ["don't know", "couldn't find", "not mentioned", "does not mention", "not provided"]


def refused(answer: str) -> bool:
    return any(m in answer.lower() for m in REFUSAL_MARKERS)


def pct(n, d):
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


data = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))

# 1. Index the sample PDFs
for pdf in sorted((EVAL_DIR / "sample_pdfs").glob("*.pdf")):
    shutil.copy(pdf, safe_pdf_path(pdf.name))
    ingest_service.ingest_background(safe_pdf_path(pdf.name), pdf.name)
    print(f"indexed {pdf.name}: {ingest_service.get_doc(pdf.name)}")

rows, latencies = [], []
hit1 = hit3 = correct = false_refusals = 0

# 2. In-scope questions
for item in data["in_scope"]:
    t = time.time()
    answer, sources = rag_answer(item["q"])
    latencies.append(time.time() - t)
    found = [(s.doc, s.page) for s in sources]
    target = (item["doc"], item["page"])
    is_hit1 = bool(found) and found[0] == target
    is_hit3 = target in found
    is_refused = refused(answer)
    is_correct = (not is_refused) and any(e.lower() in answer.lower() for e in item["expect_any"])
    hit1 += is_hit1
    hit3 += is_hit3
    correct += is_correct
    false_refusals += is_refused
    rows.append((item["q"], f"{target[0]} p{target[1]}",
                 f"{found[0][0]} p{found[0][1]}" if found else "-",
                 "yes" if is_hit3 else "NO", "yes" if is_correct else ("REFUSED" if is_refused else "NO")))

# 3. Out-of-scope questions
correct_refusals = 0
oos_rows = []
for q in data["out_of_scope"]:
    answer, sources = rag_answer(q)
    ok = refused(answer)
    correct_refusals += ok
    oos_rows.append((q, "refused" if ok else "ANSWERED", len(sources), answer[:90].replace("\n", " ")))

# 4. Routing (same logic as the /api/chat endpoint)
route_ok, route_rows = 0, []
for expected, questions in [("CHAT", data["routing"]["chat"]), ("DOC", data["routing"]["doc"])]:
    for q in questions:
        llm = classify_intent(q)
        final = "DOC" if (llm == "CHAT" and has_relevant_evidence(q)) else llm
        route_ok += final == expected
        route_rows.append((q, expected, llm, final))

n, m, r = len(data["in_scope"]), len(data["out_of_scope"]), len(route_rows)
print(f"\n===== RAG evaluation | model={OLLAMA_MODEL} | {n} in-scope, {m} out-of-scope, {r} routing questions =====")
print(f"retrieval hit@1           : {pct(hit1, n)}")
print(f"retrieval hit@3 (sources) : {pct(hit3, n)}")
print(f"answer accuracy           : {pct(correct, n)}")
print(f"false refusals (in-scope) : {pct(false_refusals, n)}")
print(f"correct refusals (OOS)    : {pct(correct_refusals, m)}")
print(f"routing accuracy          : {pct(route_ok, r)}")
print(f"avg answer latency        : {sum(latencies) / len(latencies):.1f}s")

print("\n-- in-scope --")
for q, exp, top, h3, ok in rows:
    print(f"  [{ok:>7}] hit@3={h3:<3} expected={exp:<30} top={top:<30} {q}")
print("\n-- out-of-scope --")
for q, res, nsrc, ans in oos_rows:
    print(f"  [{res:>8}] sources={nsrc} {q} -> {ans}")
print("\n-- routing --")
for q, exp, llm, final in route_rows:
    print(f"  [{'ok' if exp == final else 'WRONG':>5}] expected={exp:<4} llm={llm:<4} final={final:<4} {q}")

print(f"\n(temporary index: {work})")
