"""
LangGraph version of /api/chat (Phase 5): RAG_ENGINE=langgraph.

One StateGraph, one LLM tool-selection step, at most one retrieval retry:

  START -> choose_tool --search_documents--> run_search -> check_relevance --relevant--> write_answer -> END
               |                                 ^               |--not relevant, retry unused--> rewrite_query --+
               |                                 +-------------------------------------------------------------------+
               |                                                 +--not relevant, retry used--> refuse -> END
               |--summarize_document--> run_summary -> END
               |--generate_quiz-------> run_quiz -> END
               +--no tool call--------> safety_check --documents match--> run_search
                                                     +--no match--> END (the model's own short reply, no sources)

Nothing is rewritten, the graph only connects existing pieces:
retrieval + answer chain (langchain_rag.py), relevance rules and has_relevant_evidence
(rag_answer.py), summarize_document (features/summarize.py), generate_mcqs_for_document
(features/mcq_generator.py).
"""
import logging
import operator
from typing import Annotated, Any, Dict, List, Optional, Tuple, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from features.mcq_generator import generate_mcqs_for_document
from features.summarize import summarize_document
from ingest.service import ingest_service
from langchain_rag import generate_answer, get_chat_model, invoke_llm, retrieve_with_langchain
from rag_answer import (
    DEFAULT_CHROMA_DIR, DEFAULT_COLLECTION, DEFAULT_EMBED_MODEL,
    DEFAULT_OLLAMA_MODEL, DEFAULT_OLLAMA_URL, LOW_RELEVANCE_ANSWER, RELEVANCE_THRESHOLD,
    EvidenceChunk, has_relevant_evidence, select_evidence,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 1          # at most one extra search with a rewritten query
MAX_QUIZ_QUESTIONS = 10
EMPTY_REPLY_ANSWER = ("I can answer questions about the selected documents, summarize one of them "
                      "or make a quiz. What would you like to do?")


# --- Tools -----------------------------------------------------------------
# The model only sees each tool's name, arguments and description. The real work
# is done by the graph nodes below, so they can always apply the user's document
# filter and the checks (the model never controls the filter).

@tool("search_documents")
def search_tool(query: str) -> str:
    """DEFAULT tool. Search the user's PDF documents. Use it for ANY question about facts,
    people, places, dates, numbers, definitions or explanations, even if you think you know the answer.

    Args:
        query: what to look for, in the user's words.
    """


@tool("summarize_document")
def summary_tool(doc_name: str) -> str:
    """Write a summary of ONE whole document. Use it ONLY when the user explicitly asks
    for a summary or an overview of a document.

    Args:
        doc_name: exact file name of the document, from the list of available documents.
    """


@tool("generate_quiz")
def quiz_tool(doc_name: str, num_questions: int = 5) -> str:
    """Create a multiple-choice quiz about ONE document. Use it ONLY when the user explicitly
    asks for a quiz, a test or practice questions.

    Args:
        doc_name: exact file name of the document, from the list of available documents.
        num_questions: how many questions (1 to 10).
    """


TOOLS = [search_tool, summary_tool, quiz_tool]

SYSTEM_PROMPT = """You are the assistant of a PDF library. Available documents: {docs}.
You do NOT know what is inside these documents. Never answer a factual question from memory: call search_documents.
Call summarize_document only if the user explicitly asks for a summary or an overview of a document.
Call generate_quiz only if the user explicitly asks for a quiz, a test or practice questions.
For greetings or small talk (hello, thanks, who are you), answer in one short sentence without a tool."""

GRADE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You check search results."),
    # Evidence first, question last, plain yes/no: with qwen2.5:3b a JSON true/false format
    # answered "false" for almost everything (see the Phase 5 report).
    ("human", "EVIDENCE:\n{context}\n\nQUESTION:\n{question}\n\n"
              "Does the EVIDENCE contain the answer to the QUESTION? Answer only yes or no."),
])

REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "Rewrite the user's question as a short search query for a document search engine. "
               "Use other keywords or synonyms than the question. Reply with the query only."),
    ("human", "{question}"),
])


# --- State -------------------------------------------------------------------

class GraphState(TypedDict, total=False):
    question: str                       # the user's question (never changed)
    where: Optional[Dict[str, Any]]     # document filter from the UI selection (set by the API)
    settings: Dict[str, Any]            # models, index location, top_k, threshold
    tool_name: Optional[str]            # tool chosen by the model (None = no tool)
    tool_args: Dict[str, Any]
    search_query: str                   # the question, or the rewritten query on the retry
    retry_count: int
    evidence: List[EvidenceChunk]       # chunks that passed the distance rule
    is_summary: bool
    relevant: bool
    answer: str
    sources: List[EvidenceChunk]
    steps: Annotated[List[str], operator.add]  # path through the graph, for logs and evaluation


# --- Models (small functions so tests can replace them with fakes) -----------------

def get_tool_model(model: str, base_url: str):
    return get_chat_model(model, base_url).bind_tools(TOOLS)


def get_grader_model(model: str, base_url: str) -> ChatOllama:
    return ChatOllama(model=model, base_url=base_url, temperature=0, client_kwargs={"timeout": 120})


# --- Helpers ---------------------------------------------------------------------

def allowed_docs(where: Optional[Dict[str, Any]]) -> List[str]:
    """Ready documents the user can use: the UI selection, or the whole library."""
    ready = [name for name, info in ingest_service.get_all_docs().items() if info.get("status") == "ready"]
    if not where:
        return ready
    selected = where["doc"]
    selected = selected["$in"] if isinstance(selected, dict) else [selected]
    return [name for name in ready if name in selected]


def _valid_doc_name(state: GraphState) -> Tuple[Optional[str], Optional[str]]:
    """(document name, None) if the model's doc_name is usable, else (None, message for the user)."""
    name = str(state["tool_args"].get("doc_name") or "").strip().lower()
    allowed = allowed_docs(state.get("where"))
    for doc in allowed:
        if doc.lower() in (name, name + ".pdf"):  # also accept the name without ".pdf"
            return doc, None
    return None, f"I can only use these documents: {', '.join(allowed) or 'none'}. Which one do you mean?"


def _source(citation: Dict[str, Any], note: str) -> EvidenceChunk:
    """A summary/quiz citation shown as a source (no distance: it was not found by a search)."""
    return EvidenceChunk(doc=citation["doc"], page=citation["page"],
                         chunk_index=citation["chunk_index"], text=note, distance=None)


# --- Nodes -----------------------------------------------------------------------

def choose_tool(state: GraphState) -> GraphState:
    """The only tool-selection step: the model picks one tool, or answers small talk directly."""
    s = state["settings"]
    docs = ", ".join(allowed_docs(state.get("where"))) or "(none)"
    messages = [SystemMessage(SYSTEM_PROMPT.format(docs=docs)), HumanMessage(state["question"])]
    reply = invoke_llm(get_tool_model(s["ollama_model"], s["ollama_url"]), messages, s["ollama_model"], s["ollama_url"])
    if reply.tool_calls:
        call = reply.tool_calls[0]  # one tool per question: keep the first call
        return {"tool_name": call["name"], "tool_args": call["args"], "steps": [f"choose_tool:{call['name']}"]}
    # Seen live: asked about a document outside the selection, the model returned no tool AND no text.
    answer = reply.content.strip() or EMPTY_REPLY_ANSWER
    return {"tool_name": None, "tool_args": {}, "answer": answer, "steps": ["choose_tool:none"]}


def safety_check(state: GraphState) -> GraphState:
    """Safeguard for a skipped search: if the documents clearly match, search anyway."""
    matched = has_relevant_evidence(state["question"], state.get("where"))
    return {"relevant": matched, "steps": [f"safety_check:{'documents match' if matched else 'no match'}"]}


def run_search(state: GraphState) -> GraphState:
    s = state["settings"]
    query = state.get("search_query") or state["question"]
    found = retrieve_with_langchain(query, s["chroma_dir"], s["collection_name"], s["embed_model_name"],
                                    s["top_k"], state.get("where"))
    _, used, is_summary = select_evidence(state["question"], found, s["use_top_n_in_prompt"], s["max_distance"])
    return {"evidence": used, "is_summary": is_summary, "steps": [f"run_search:{len(used)} chunks"]}


def check_relevance(state: GraphState) -> GraphState:
    """Distance rule first (no LLM call), then one small LLM check: does the evidence answer the question?"""
    if not state["evidence"]:
        return {"relevant": False, "steps": ["check_relevance:no close chunk"]}
    s = state["settings"]
    chain = GRADE_PROMPT | get_grader_model(s["ollama_model"], s["ollama_url"]) | StrOutputParser()
    reply = invoke_llm(chain, {"question": state["question"], "context": "\n\n".join(c.text for c in state["evidence"])},
                       s["ollama_model"], s["ollama_url"])
    # Only a clear "no" rejects the evidence; an unclear reply keeps it (it already passed the distance rule).
    relevant = not reply.strip().lower().startswith("no")
    return {"relevant": relevant, "steps": [f"check_relevance:{'relevant' if relevant else 'not relevant'}"]}


def rewrite_query(state: GraphState) -> GraphState:
    """The one retry: search again with other words. The answer still uses the original question."""
    s = state["settings"]
    chain = REWRITE_PROMPT | get_chat_model(s["ollama_model"], s["ollama_url"]) | StrOutputParser()
    new_query = invoke_llm(chain, {"question": state["question"]}, s["ollama_model"], s["ollama_url"])
    new_query = new_query.strip().strip('"') or state["question"]
    return {"search_query": new_query, "retry_count": state.get("retry_count", 0) + 1,
            "steps": [f"rewrite_query:{new_query}"]}


def write_answer(state: GraphState) -> GraphState:
    s = state["settings"]
    text = generate_answer(state["question"], state["evidence"], state["is_summary"], s["ollama_model"], s["ollama_url"])
    return {"answer": text, "sources": state["evidence"], "steps": ["write_answer"]}


def refuse(state: GraphState) -> GraphState:
    return {"answer": LOW_RELEVANCE_ANSWER, "sources": [], "steps": ["refuse"]}


def run_summary(state: GraphState) -> GraphState:
    doc, problem = _valid_doc_name(state)
    if problem:
        return {"answer": problem, "sources": [], "steps": ["run_summary:unknown document"]}
    s = state["settings"]
    result = summarize_document(doc, model=s["ollama_model"], ollama_url=s["ollama_url"])
    cited = [c for c in result.citations if f"[{c['evidence_id']}]" in result.markdown]
    return {"answer": result.markdown, "sources": [_source(c, "Used in the summary") for c in cited],
            "steps": [f"run_summary:{doc}"]}


def run_quiz(state: GraphState) -> GraphState:
    doc, problem = _valid_doc_name(state)
    if problem:
        return {"answer": problem, "sources": [], "steps": ["run_quiz:unknown document"]}
    try:
        n = int(state["tool_args"].get("num_questions", 5))
    except (TypeError, ValueError):
        n = 5
    n = max(1, min(n, MAX_QUIZ_QUESTIONS))
    s = state["settings"]
    mcqs = generate_mcqs_for_document(doc, n=n, model=s["ollama_model"], ollama_url=s["ollama_url"])
    if not mcqs:
        return {"answer": "The model did not return valid quiz questions. Please try again.", "sources": [],
                "steps": [f"run_quiz:{doc}:empty"]}

    letters = "ABCD"
    lines = [f"## Quiz: {doc}", ""]
    for i, q in enumerate(mcqs, start=1):
        lines.append(f"**{i}. {q.question}**")
        lines += [f"- {letters[j]}) {option}" for j, option in enumerate(q.options)]
        lines.append("")
    lines.append("### Answers")
    lines += [f"{i}. {letters[q.correct_index]}) {q.explanation}" for i, q in enumerate(mcqs, start=1)]

    sources, seen = [], set()
    for i, q in enumerate(mcqs, start=1):
        for c in q.citations:
            key = (c["doc"], c["page"], c["chunk_index"])
            if key not in seen:
                seen.add(key)
                sources.append(_source(c, f"Used for question {i}"))
    return {"answer": "\n".join(lines), "sources": sources, "steps": [f"run_quiz:{doc}:{len(mcqs)} questions"]}


# --- Routing (conditional edges) ------------------------------------------------

def route_tool(state: GraphState) -> str:
    nodes = {"search_documents": "run_search", "summarize_document": "run_summary", "generate_quiz": "run_quiz"}
    return nodes.get(state.get("tool_name"), "safety_check")  # no tool (or an unknown one) -> safety check


def route_safety(state: GraphState) -> str:
    return "run_search" if state["relevant"] else END


def route_relevance(state: GraphState) -> str:
    if state["relevant"]:
        return "write_answer"
    if state.get("retry_count", 0) < MAX_RETRIES:
        return "rewrite_query"
    return "refuse"


def build_graph():
    graph = StateGraph(GraphState)
    for node in [choose_tool, safety_check, run_search, check_relevance, rewrite_query,
                 write_answer, refuse, run_summary, run_quiz]:
        graph.add_node(node.__name__, node)

    graph.add_edge(START, "choose_tool")
    graph.add_conditional_edges("choose_tool", route_tool, ["run_search", "run_summary", "run_quiz", "safety_check"])
    graph.add_conditional_edges("safety_check", route_safety, ["run_search", END])
    graph.add_edge("run_search", "check_relevance")
    graph.add_conditional_edges("check_relevance", route_relevance, ["write_answer", "rewrite_query", "refuse"])
    graph.add_edge("rewrite_query", "run_search")  # the only loop, bounded by MAX_RETRIES
    for node in ["write_answer", "refuse", "run_summary", "run_quiz"]:
        graph.add_edge(node, END)
    return graph.compile()


GRAPH = build_graph()

DEFAULT_SETTINGS = {
    "chroma_dir": DEFAULT_CHROMA_DIR, "collection_name": DEFAULT_COLLECTION, "embed_model_name": DEFAULT_EMBED_MODEL,
    "ollama_model": DEFAULT_OLLAMA_MODEL, "ollama_url": DEFAULT_OLLAMA_URL,
    "top_k": 6, "use_top_n_in_prompt": 3, "max_distance": RELEVANCE_THRESHOLD,
}


def run_graph(question: str, where: Optional[Dict[str, Any]] = None,
              settings: Optional[Dict[str, Any]] = None) -> GraphState:
    """Run the graph and return the whole final state (the evaluation reads `steps`)."""
    state = GRAPH.invoke({"question": question, "where": where, "settings": {**DEFAULT_SETTINGS, **(settings or {})},
                          "retry_count": 0, "steps": []})
    logger.info("Graph path: %s", " -> ".join(state["steps"]))
    return state


def graph_answer(
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
    """Same inputs and outputs as rag_answer() / langchain_rag_answer()."""
    state = run_graph(question, where, {
        "chroma_dir": chroma_dir, "collection_name": collection_name, "embed_model_name": embed_model_name,
        "ollama_model": ollama_model, "ollama_url": ollama_url,
        "top_k": top_k, "use_top_n_in_prompt": use_top_n_in_prompt, "max_distance": max_distance,
    })
    return state["answer"], state.get("sources", [])
