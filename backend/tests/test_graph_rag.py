"""
Tests for the LangGraph engine (RAG_ENGINE=langgraph).

Same isolation as the other tests (temporary folder, fake embedder, fake PDFs).
Every model call is replaced by a LangChain fake model, so the tests decide
which tool the "model" picks and what the relevance check / rewrite return.
"""
import inspect

import pytest

pytest.importorskip("langgraph")
from langchain_core.language_models import FakeListChatModel, FakeMessagesListChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from test_phase1_regressions import env, upload, make_pdf, PHOTO, ROMAN, OCEAN  # noqa: E402,F401

PLANT_WORDS = "photosynthesis chlorophyll plants sunlight"   # matches PHOTO
NO_MATCH_QUESTION = "How do green things make food from light?"  # shares no word with PHOTO


@pytest.fixture
def lg(env, monkeypatch):
    """API on the LangGraph engine, every LLM replaced by a fake. Records what the graph does."""
    import web_server
    import graph_rag
    import langchain_rag

    rec = {"tool_reply": AIMessage(content="", tool_calls=[{"name": "search_documents", "args": {"query": "q"}, "id": "1"}]),
           "grades": ["yes"] * 2, "rewrite": PLANT_WORDS,
           "grader_calls": 0, "searches": [], "answer_questions": [], "summaries": [], "quizzes": []}

    def fake_grader(model, base_url):
        rec["grader_calls"] += 1
        return FakeListChatModel(responses=[rec["grades"][rec["grader_calls"] - 1]])

    real_retrieve, real_generate = graph_rag.retrieve_with_langchain, graph_rag.generate_answer

    def recording_retrieve(query, *args):
        rec["searches"].append({"query": query, "where": args[-1]})
        return real_retrieve(query, *args)

    def recording_generate(question, *args):
        rec["answer_questions"].append(question)
        return real_generate(question, *args)

    monkeypatch.setattr(web_server, "RAG_ENGINE", "langgraph")
    monkeypatch.setattr(graph_rag, "get_tool_model", lambda m, u: FakeMessagesListChatModel(responses=[rec["tool_reply"]]))
    monkeypatch.setattr(graph_rag, "get_grader_model", fake_grader)
    monkeypatch.setattr(graph_rag, "get_chat_model", lambda m, u: FakeListChatModel(responses=[rec["rewrite"]]))
    monkeypatch.setattr(langchain_rag, "get_chat_model", lambda m, u: FakeListChatModel(responses=["LG ANSWER"]))
    monkeypatch.setattr(graph_rag, "retrieve_with_langchain", recording_retrieve)
    monkeypatch.setattr(graph_rag, "generate_answer", recording_generate)
    return {**env, "rec": rec, "monkeypatch": monkeypatch}


def model_calls_tool(lg, name, **args):
    lg["rec"]["tool_reply"] = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "1"}])


def ask(client, question, **extra):
    r = client.post("/api/chat", json={"question": question, **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- search path ----------

def test_same_parameters_as_the_other_engines(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # importing the app creates storage/ in the current folder
    from rag_answer import rag_answer
    from graph_rag import graph_answer
    assert inspect.signature(graph_answer).parameters.keys() == inspect.signature(rag_answer).parameters.keys()


def test_search_answers_with_correct_document_and_page(lg):
    client = lg["client"]
    upload(client, "bio.pdf", make_pdf([ROMAN, PHOTO]))  # photosynthesis on page 2
    upload(client, "ocean.pdf", make_pdf([OCEAN]))

    body = ask(client, "How do plants use sunlight and chlorophyll?")
    assert body["answer"] == "LG ANSWER"
    assert (body["citations"][0]["doc"], body["citations"][0]["page"]) == ("bio.pdf", 2)
    assert len(lg["rec"]["searches"]) == 1, "no retry when the first search is good"


def test_off_topic_question_is_refused_after_one_retry_without_answer_llm(lg):
    client = lg["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))
    lg["rec"]["rewrite"] = "capital gains tax"

    body = ask(client, "What is the capital gains tax rate?")
    assert "couldn't find" in body["answer"].lower() and body["citations"] == []
    assert len(lg["rec"]["searches"]) == 2, "exactly one retry"
    assert lg["rec"]["grader_calls"] == 0, "no close chunk -> no LLM relevance call"
    assert lg["rec"]["answer_questions"] == [], "the answer LLM must not be called"


def test_retry_with_rewritten_query_rescues_the_answer(lg):
    client = lg["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))

    body = ask(client, NO_MATCH_QUESTION)
    assert body["answer"] == "LG ANSWER" and body["citations"][0]["doc"] == "bio.pdf"
    assert [s["query"] for s in lg["rec"]["searches"]] == [NO_MATCH_QUESTION, PLANT_WORDS]
    assert lg["rec"]["answer_questions"] == [NO_MATCH_QUESTION], "the answer uses the ORIGINAL question"


def test_relevance_check_says_no_twice_then_refuses(lg):
    client = lg["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))
    lg["rec"]["grades"] = ["no", "no"]

    body = ask(client, "How do plants use sunlight and chlorophyll?")  # close chunks, but "not relevant"
    assert "couldn't find" in body["answer"].lower() and body["citations"] == []
    assert lg["rec"]["grader_calls"] == 2 and len(lg["rec"]["searches"]) == 2
    assert lg["rec"]["answer_questions"] == []


def test_unclear_relevance_reply_keeps_the_evidence(lg):
    client = lg["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))
    lg["rec"]["grades"] = ["I am not sure."]

    assert ask(client, "How do plants use sunlight and chlorophyll?")["answer"] == "LG ANSWER"


def test_document_filter_is_kept_on_the_retry(lg):
    client = lg["client"]
    upload(client, "a.pdf", make_pdf([PHOTO]))
    upload(client, "b.pdf", make_pdf([PHOTO + " " + ROMAN]))

    body = ask(client, NO_MATCH_QUESTION, doc_names=["b.pdf"])
    assert {c["doc"] for c in body["citations"]} == {"b.pdf"}
    assert len(lg["rec"]["searches"]) == 2
    assert all(s["where"] == {"doc": "b.pdf"} for s in lg["rec"]["searches"])


def test_no_tool_call_but_documents_match_runs_the_search(lg):
    client = lg["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))
    lg["rec"]["tool_reply"] = AIMessage(content="Plants are green.")  # model skipped the search

    body = ask(client, "How do plants use sunlight and chlorophyll?")
    assert body["answer"] == "LG ANSWER" and body["citations"], "safety check must force the search"


def test_small_talk_gets_the_direct_reply_without_sources(lg):
    client = lg["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))
    lg["rec"]["tool_reply"] = AIMessage(content="Hello! Ask me about your documents.")

    body = ask(client, "hello")
    assert body == {"answer": "Hello! Ask me about your documents.", "citations": []}
    assert lg["rec"]["searches"] == []


def test_empty_direct_reply_gets_a_helpful_message(lg):
    import graph_rag
    upload(lg["client"], "bio.pdf", make_pdf([PHOTO]))
    lg["rec"]["tool_reply"] = AIMessage(content="")  # seen live: no tool and no text

    body = ask(lg["client"], "Summarize history.pdf")
    assert body == {"answer": graph_rag.EMPTY_REPLY_ANSWER, "citations": []}


# ---------- summary and quiz tools ----------

@pytest.fixture
def tools(lg, monkeypatch):
    import graph_rag
    from features.summarize import SummaryResult
    from features.mcq_generator import MCQ

    def fake_summary(doc, model, ollama_url):
        lg["rec"]["summaries"].append(doc)
        cits = [{"evidence_id": "E1", "doc": doc, "page": 1, "chunk_index": 0},
                {"evidence_id": "E2", "doc": doc, "page": 2, "chunk_index": 1}]
        return SummaryResult(title=f"Summary — {doc}", markdown="# Summary\nPlants make glucose [E1].", citations=cits)

    def fake_quiz(doc, n, model, ollama_url):
        lg["rec"]["quizzes"].append((doc, n))
        cit = {"evidence_id": "E1", "doc": doc, "page": 1, "chunk_index": 0}
        return [MCQ(question="What do plants make?", options=["Salt", "Glucose", "Iron", "Rock"],
                    correct_index=1, explanation="Glucose, from sunlight.", citations=[cit])]

    monkeypatch.setattr(graph_rag, "summarize_document", fake_summary)
    monkeypatch.setattr(graph_rag, "generate_mcqs_for_document", fake_quiz)
    upload(lg["client"], "bio.pdf", make_pdf([PHOTO]))
    upload(lg["client"], "ocean.pdf", make_pdf([OCEAN]))
    return lg


def test_summary_tool_calls_the_existing_summary(tools):
    model_calls_tool(tools, "get_summary", doc_name="bio")  # name without .pdf is accepted
    body = ask(tools["client"], "Summarize bio")
    assert tools["rec"]["summaries"] == ["bio.pdf"]
    assert body["answer"].startswith("# Summary")
    assert [(c["page"], c["distance"]) for c in body["citations"]] == [(1, None)], "only the cited chunk [E1]"


def test_summary_without_markers_keeps_its_sources(tools, monkeypatch):
    import graph_rag
    from features.summarize import SummaryResult
    cits = [{"evidence_id": "E1", "doc": "bio.pdf", "page": 1, "chunk_index": 0}]
    monkeypatch.setattr(graph_rag, "summarize_document",
                        lambda doc, model, ollama_url: SummaryResult(title="t", markdown="# Summary\nNo markers.", citations=cits))
    model_calls_tool(tools, "get_summary", doc_name="bio.pdf")
    assert [c["page"] for c in ask(tools["client"], "What is this document about?")["citations"]] == [1]


@pytest.mark.parametrize("doc_name, selection", [("history.pdf", None), ("bio.pdf", ["ocean.pdf"])])
def test_unknown_or_unselected_document_is_not_used(tools, doc_name, selection):
    model_calls_tool(tools, "get_summary", doc_name=doc_name)
    extra = {"doc_names": selection} if selection else {}
    body = ask(tools["client"], f"Summarize {doc_name}", **extra)
    assert "I can only use these documents" in body["answer"] and body["citations"] == []
    assert tools["rec"]["summaries"] == []


def test_quiz_tool_limits_questions_and_returns_markdown(tools):
    model_calls_tool(tools, "generate_quiz", doc_name="bio.pdf", num_questions=50)
    body = ask(tools["client"], "Quiz me with 50 questions on bio.pdf")
    assert tools["rec"]["quizzes"] == [("bio.pdf", 10)]
    assert "**1. What do plants make?**" in body["answer"] and "### Answers" in body["answer"]
    assert body["answer"].index("### Answers") > body["answer"].index("- D) Rock"), "answers at the end"
    assert body["citations"][0]["doc"] == "bio.pdf"


def test_selected_documents_are_named_in_the_prompt(lg):
    """With a UI selection, the model is told that "this book" / "this PDF" means the selected file."""
    import graph_rag
    from langchain_core.runnables import RunnableLambda
    seen = []

    def fake_tool_model(messages):
        seen.append(messages[0].content)
        return AIMessage(content="Hello!")

    lg["monkeypatch"].setattr(graph_rag, "get_tool_model", lambda m, u: RunnableLambda(fake_tool_model))
    upload(lg["client"], "bio.pdf", make_pdf([PHOTO]))
    upload(lg["client"], "ocean.pdf", make_pdf([OCEAN]))
    ask(lg["client"], "hello", doc_names=["bio.pdf"])
    ask(lg["client"], "hello")
    assert 'selected these documents in the app: bio.pdf. "This document", "this book"' in seen[0]
    assert "selected these documents" not in seen[1], "no selection -> no extra sentence"


def test_unknown_tool_name_goes_to_the_safety_check(tools):
    model_calls_tool(tools, "delete_everything")
    body = ask(tools["client"], "How do plants use sunlight and chlorophyll?")
    assert body["answer"] == "LG ANSWER"


# ---------- errors and settings ----------

def test_returns_503_when_ollama_is_down(lg, monkeypatch):
    import graph_rag
    from langchain_ollama import ChatOllama

    monkeypatch.setattr(graph_rag, "get_tool_model",
                        lambda m, u: ChatOllama(model=m, base_url="http://127.0.0.1:9").bind_tools(graph_rag.TOOLS))
    upload(lg["client"], "bio.pdf", make_pdf([PHOTO]))
    r = lg["client"].post("/api/chat", json={"question": "How do plants use sunlight and chlorophyll?"})
    assert r.status_code == 503 and "ollama serve" in r.json()["detail"]
    assert lg["service"].get_doc("bio.pdf")["status"] == "ready"


def test_langgraph_engine_can_be_selected_at_startup(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {**os.environ, "RAG_ENGINE": "langgraph", "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    out = subprocess.run([sys.executable, "-c", "import web_server; print(web_server.RAG_ENGINE)"],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "langgraph"
