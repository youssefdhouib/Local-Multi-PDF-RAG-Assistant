import logging

from features import ollama_client

DEFAULT_OLLAMA_URL = ollama_client.OLLAMA_URL
DEFAULT_OLLAMA_MODEL = ollama_client.OLLAMA_MODEL

logger = logging.getLogger(__name__)


def _call_ollama(prompt: str, model: str = DEFAULT_OLLAMA_MODEL, system: str = None) -> str:
    # Raises ollama_client.OllamaError when Ollama is unreachable or the model is missing.
    return ollama_client.generate(prompt, model=model, system=system, temperature=0.1, timeout=60)
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
    except ollama_client.OllamaError as e:
        # Safe default: try the documents. If Ollama is really down, the RAG
        # step will raise the same error and the API reports it as 503.
        logger.warning("Intent classification failed (%s); defaulting to DOC", e)
        return "DOC"

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
    
    # OllamaError propagates so the API can return a clear 503 instead of
    # pretending this error text is a normal answer.
    return _call_ollama(query, model=model, system=system_prompt)
