"""
Tests for the LangChain Q&A engine (RAG_ENGINE=langchain).

They reuse the Phase 1 helpers (temporary folder, fake embedder, fake PDFs) and
LangChain's own FakeListChatModel, so no real data and no Ollama are needed.
"""
import inspect

import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_chroma")
pytest.importorskip("langchain_ollama")
from langchain_core.language_models import FakeListChatModel  # noqa: E402

from test_phase1_regressions import env, upload, make_pdf, long_text, PHOTO, ROMAN, OCEAN  # noqa: E402,F401


@pytest.fixture
def lc(env, monkeypatch):
    """Switch the API to the LangChain engine and replace ChatOllama with a fake model."""
    import web_server
    import langchain_rag

    calls = []

    def fake_chat_model(model, base_url):
        calls.append(model)
        return FakeListChatModel(responses=["LC ANSWER"])

    monkeypatch.setattr(web_server, "RAG_ENGINE", "langchain")
    monkeypatch.setattr(langchain_rag, "get_chat_model", fake_chat_model)
    return {**env, "llm_calls": calls}


def ask(client, question, **extra):
    r = client.post("/api/chat", json={"question": question, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_same_parameters_as_classic_rag_answer():
    from rag_answer import rag_answer
    from langchain_rag import langchain_rag_answer
    assert inspect.signature(langchain_rag_answer).parameters.keys() == inspect.signature(rag_answer).parameters.keys()


def test_langchain_answers_with_correct_document_and_page(lc):
    client = lc["client"]
    upload(client, "bio.pdf", make_pdf([ROMAN, PHOTO]))  # photosynthesis on page 2
    upload(client, "ocean.pdf", make_pdf([OCEAN]))

    body = ask(client, "How do plants use sunlight and chlorophyll?")
    assert body["answer"] == "LC ANSWER"
    assert (body["citations"][0]["doc"], body["citations"][0]["page"]) == ("bio.pdf", 2)
    assert all(c["distance"] <= 0.75 for c in body["citations"])


def test_both_engines_return_identical_sources(lc, monkeypatch):
    import web_server
    client = lc["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO, ROMAN]))
    upload(client, "ocean.pdf", make_pdf([OCEAN]))
    question = "How do plants use sunlight and chlorophyll?"

    langchain_sources = ask(client, question)["citations"]
    monkeypatch.setattr(web_server, "RAG_ENGINE", "classic")
    classic_sources = ask(client, question)["citations"]

    key = lambda c: (c["doc"], c["page"], c["chunk_index"], round(c["distance"], 4))  # noqa: E731
    assert [key(c) for c in langchain_sources] == [key(c) for c in classic_sources]


def test_langchain_refuses_without_calling_the_llm(lc):
    client = lc["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))

    body = ask(client, "What is the capital gains tax rate?")
    assert "couldn't find" in body["answer"].lower()
    assert body["citations"] == []
    assert lc["llm_calls"] == [], "the LLM must not be called when the guardrail refuses"


def test_langchain_only_searches_selected_documents(lc):
    client = lc["client"]
    shared = long_text(["energy", "system", "process"])
    upload(client, "a.pdf", make_pdf([shared + " " + PHOTO]))
    upload(client, "b.pdf", make_pdf([shared + " " + ROMAN]))
    upload(client, "c.pdf", make_pdf([shared + " " + OCEAN]))

    body = ask(client, "energy system process", doc_names=["a.pdf", "b.pdf"], top_k=10)
    docs = {c["doc"] for c in body["citations"]}
    assert docs and docs <= {"a.pdf", "b.pdf"}


def test_langchain_returns_503_when_ollama_is_down(lc, monkeypatch):
    import langchain_rag
    from langchain_ollama import ChatOllama

    # A real ChatOllama pointed at a closed port: exercises the real error mapping.
    monkeypatch.setattr(langchain_rag, "get_chat_model",
                        lambda model, base_url: ChatOllama(model=model, base_url="http://127.0.0.1:9"))
    client = lc["client"]
    upload(client, "bio.pdf", make_pdf([PHOTO]))

    r = client.post("/api/chat", json={"question": "How do plants use sunlight and chlorophyll?"})
    assert r.status_code == 503
    assert "ollama serve" in r.json()["detail"]
    assert lc["service"].get_doc("bio.pdf")["status"] == "ready"  # user data untouched


def test_health_reports_the_active_engine(lc):
    assert lc["client"].get("/api/health").json()["rag_engine"] == "langchain"


@pytest.mark.parametrize("env_value, expected", [(None, "langchain"), ("classic", "classic"), ("langchain", "langchain")])
def test_rag_engine_setting_at_startup(tmp_path, env_value, expected):
    """Starts a fresh Python process, like the real server: default is langchain, classic stays available."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {k: v for k, v in os.environ.items() if k != "RAG_ENGINE"}
    if env_value:
        env["RAG_ENGINE"] = env_value
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])  # backend/
    out = subprocess.run([sys.executable, "-c", "import web_server; print(web_server.RAG_ENGINE)"],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == expected


def test_unknown_rag_engine_stops_startup(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {**os.environ, "RAG_ENGINE": "typo", "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    out = subprocess.run([sys.executable, "-c", "import web_server"],
                         cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode != 0 and "RAG_ENGINE must be one of" in out.stderr
