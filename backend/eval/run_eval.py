"""
Small end-to-end evaluation of the RAG pipeline (real embeddings, real Chroma, real Ollama).

    cd backend
    python eval/run_eval.py                       # LangGraph workflow (default: tool calling + one retry)
    RAG_ENGINE=langchain python eval/run_eval.py  # LangChain engine
    RAG_ENGINE=classic python eval/run_eval.py    # classic engine, for comparison

Uses OLLAMA_MODEL (default qwen2.5:3b) and the same RAG_ENGINE switch as the API.

It indexes eval/sample_pdfs/ into a TEMPORARY folder (your real data/ and storage/
are never touched) and measures:
  - retrieval hit@1 / hit@3 : is the page that contains the answer the top source / among the sources?
  - answer accuracy         : does the answer contain the expected fact?
  - false refusals          : in-scope questions the app refused to answer
  - correct refusals        : out-of-scope questions the app refused (no made-up answer)
  - paraphrased questions   : in-scope questions written with other words than the PDF
  - routing accuracy        : classic/langchain: CHAT vs DOC decision (LLM router + document check)
  - tool choice             : langgraph: tool picked by the model, and the final route after the safety check
  - retries                 : langgraph: how often the one retry ran, and how often it rescued the answer
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
from rag_answer import has_relevant_evidence                    # noqa: E402
from web_server import RAG_ENGINE, RAG_ENGINES                  # noqa: E402  same switch as the API
from features.router import classify_intent                     # noqa: E402
from features.ollama_client import OLLAMA_MODEL                 # noqa: E402
import graph_rag                                                # noqa: E402

answer_fn = RAG_ENGINES[RAG_ENGINE]  # the engine under test

# "don't have": the LangGraph model sometimes declines directly ("I don't have information about ...").
REFUSAL_MARKERS = ["don't know", "don't have", "couldn't find", "not mentioned", "does not mention", "not provided"]


REFUSAL_WINDOW = 150  # a real refusal starts the answer; "Saturn has dozens of moons ... I don't know" is NOT a refusal


def refused(answer: str) -> bool:
    start = answer.lower()[:REFUSAL_WINDOW]
    return any(m in start for m in REFUSAL_MARKERS)


def pct(n, d):
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def ask(question):
    """(answer, sources, graph path). The graph path is only known for the LangGraph engine."""
    if RAG_ENGINE == "langgraph":
        state = graph_rag.run_graph(question)  # same as graph_answer(), but keeps the path
        return state["answer"], state.get("sources", []), state["steps"]
    answer, sources = answer_fn(question)
    return answer, sources, []


def run_questions(items):
    """Answer each in-scope item and score it."""
    rows, latencies = [], []
    totals = {"hit1": 0, "hit3": 0, "correct": 0, "refused": 0, "retried": 0, "rescued": 0}
    for item in items:
        t = time.time()
        answer, sources, steps = ask(item["q"])
        latencies.append(time.time() - t)
        found = [(s.doc, s.page) for s in sources]
        target = (item["doc"], item["page"])
        is_refused = refused(answer)
        is_correct = (not is_refused) and any(e.lower() in answer.lower() for e in item["expect_any"])
        retried = any(s.startswith("rewrite_query") for s in steps)
        totals["hit1"] += bool(found) and found[0] == target
        totals["hit3"] += target in found
        totals["correct"] += is_correct
        totals["refused"] += is_refused
        totals["retried"] += retried
        totals["rescued"] += retried and is_correct
        rows.append((item["q"], f"{target[0]} p{target[1]}",
                     f"{found[0][0]} p{found[0][1]}" if found else "-",
                     "yes" if target in found else "NO",
                     "yes" if is_correct else ("REFUSED" if is_refused else "NO"),
                     " -> ".join(steps)))
    return rows, latencies, totals


data = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))

# 1. Index the sample PDFs
for pdf in sorted((EVAL_DIR / "sample_pdfs").glob("*.pdf")):
    shutil.copy(pdf, safe_pdf_path(pdf.name))
    ingest_service.ingest_background(safe_pdf_path(pdf.name), pdf.name)
    print(f"indexed {pdf.name}: {ingest_service.get_doc(pdf.name)}")

# 2. In-scope and paraphrased questions
rows, latencies, t = run_questions(data["in_scope"])
para_rows, para_latencies, p = run_questions(data["paraphrased"])

# 3. Out-of-scope questions
correct_refusals, oos_retried = 0, 0
oos_rows = []
for q in data["out_of_scope"]:
    answer, sources, steps = ask(q)
    ok = refused(answer)
    correct_refusals += ok
    oos_retried += any(s.startswith("rewrite_query") for s in steps)
    oos_rows.append((q, "refused" if ok else "ANSWERED", len(sources), answer[:160].replace("\n", " "), " -> ".join(steps)))

# 4a. Routing (classic / langchain: same logic as the /api/chat endpoint)
route_ok, route_rows = 0, []
# 4b. Tool choice (langgraph): only the decision step + safety check, no summary/quiz is generated
tool_raw_ok = tool_final_ok = 0
tool_rows = []
if RAG_ENGINE == "langgraph":
    cases = ([(q, "none") for q in data["routing"]["chat"]]
             + [(q, "search_documents") for q in data["routing"]["doc"]]
             + [(c["q"], c["tool"]) for c in data["tools"]])
    for q, expected in cases:
        state = {"question": q, "where": None, "settings": graph_rag.DEFAULT_SETTINGS}
        raw = graph_rag.choose_tool(state)["tool_name"] or "none"
        final = raw
        if graph_rag.route_tool({"tool_name": raw}) == "safety_check":
            final = "search_documents" if graph_rag.safety_check(state)["relevant"] else "none"
        tool_raw_ok += raw == expected
        tool_final_ok += final == expected
        tool_rows.append((q, expected, raw, final))
else:
    for expected, questions in [("CHAT", data["routing"]["chat"]), ("DOC", data["routing"]["doc"])]:
        for q in questions:
            llm = classify_intent(q)
            final = "DOC" if (llm == "CHAT" and has_relevant_evidence(q)) else llm
            route_ok += final == expected
            route_rows.append((q, expected, llm, final))

n, m, k = len(data["in_scope"]), len(data["out_of_scope"]), len(data["paraphrased"])
print(f"\n===== RAG evaluation | engine={RAG_ENGINE} ({answer_fn.__name__}) | model={OLLAMA_MODEL} | "
      f"{n} in-scope, {k} paraphrased, {m} out-of-scope questions =====")
print(f"retrieval hit@1           : {pct(t['hit1'], n)}")
print(f"retrieval hit@3 (sources) : {pct(t['hit3'], n)}")
print(f"answer accuracy           : {pct(t['correct'], n)}")
print(f"false refusals (in-scope) : {pct(t['refused'], n)}")
print(f"correct refusals (OOS)    : {pct(correct_refusals, m)}")
print(f"paraphrased accuracy      : {pct(p['correct'], k)}  (refused {p['refused']})")
if RAG_ENGINE == "langgraph":
    print(f"tool choice (model only)  : {pct(tool_raw_ok, len(tool_rows))}")
    print(f"tool choice (+ safety)    : {pct(tool_final_ok, len(tool_rows))}")
    print(f"retry ran                 : in-scope {t['retried']}/{n}, paraphrased {p['retried']}/{k}, OOS {oos_retried}/{m}")
    print(f"retry rescued the answer  : in-scope {t['rescued']}, paraphrased {p['rescued']}")
else:
    print(f"routing accuracy          : {pct(route_ok, len(route_rows))}")
print(f"avg answer latency        : {sum(latencies) / len(latencies):.1f}s (in-scope)")

for title, table in [("in-scope", rows), ("paraphrased", para_rows)]:
    print(f"\n-- {title} --")
    for q, exp, top, h3, ok, path in table:
        print(f"  [{ok:>7}] hit@3={h3:<3} expected={exp:<30} top={top:<30} {q}" + (f"\n            path: {path}" if path else ""))
print("\n-- out-of-scope --")
for q, res, nsrc, ans, path in oos_rows:
    print(f"  [{res:>8}] sources={nsrc} {q} -> {ans}" + (f"\n            path: {path}" if path else ""))
if tool_rows:
    print("\n-- tool choice --")
    for q, exp, raw, final in tool_rows:
        print(f"  [{'ok' if exp == final else 'WRONG':>5}] expected={exp:<18} model={raw:<18} final={final:<18} {q}")
else:
    print("\n-- routing --")
    for q, exp, llm, final in route_rows:
        print(f"  [{'ok' if exp == final else 'WRONG':>5}] expected={exp:<4} llm={llm:<4} final={final:<4} {q}")

print(f"\n(temporary index: {work})")
