import requests
import logging

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"

def _call_ollama(prompt: str, model: str = DEFAULT_OLLAMA_MODEL, system: str = None) -> str:
    url = f"{DEFAULT_OLLAMA_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1}, # Low temp for router
    }
    if system:
        payload["system"] = system

    try:
        r = requests.post(url, json=payload, timeout=60)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception as e:
        logging.error(f"Ollama call failed: {e}")
        # Return empty string or handle error
        raise e

def classify_intent(query: str, model: str = DEFAULT_OLLAMA_MODEL) -> str:
    """
    Classifies the user query as 'CHAT' or 'DOC'.
    """
    prompt = f"""Classify the user's intent based on the following query.
    
    Query: "{query}"

    - If the query is a greeting (hello, hi), a thank you, a question about "what can you do", general help, or small talk, output: CHAT
    - If the query asks for information likely found in a document, asks to summarize, explain, or quiz about content, output: DOC
    
    Output ONLY the single word: CHAT or DOC. Do not output anything else.
    """
    
    try:
        response = _call_ollama(prompt, model=model)
        intent = response.upper()
        if "DOC" in intent:
            return "DOC"
        return "CHAT"
    except Exception:
        return "DOC" # Fallback to RAG

def chat_with_ollama(query: str, model: str = DEFAULT_OLLAMA_MODEL) -> str:
    """
    Handles general chat interactions without RAG retrieval.
    """
    system_prompt = """You are a helpful Document Assistant.
    Your capabilities:
    - Answering questions based on uploaded PDFs.
    - Summarizing documents.
    - Creating quizzes.
    
    If the user asks what you can do, explain these capabilities briefly.
    Be professional, polite, and concise. Do NOT hallucinate about document content if you haven't seen it (this mode is for general chat).
    """
    
    try:
        return _call_ollama(query, model=model, system=system_prompt)
    except Exception:
        return "I'm having trouble connecting to my language model. Please try again."
