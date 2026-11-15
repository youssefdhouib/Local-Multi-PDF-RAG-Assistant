"""
One small helper for calling Ollama's /api/generate endpoint.

Every feature (chat, RAG answers, summaries, quizzes) uses this, so a
missing Ollama server or a model that was never pulled is reported the
same way everywhere: as an OllamaError that the API turns into HTTP 503.
"""
import os
from typing import Optional, Dict, Any

import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")


class OllamaError(RuntimeError):
    """Raised when Ollama cannot produce an answer (not running, model missing, timeout)."""


def generate(
    prompt: str,
    model: Optional[str] = None,
    system: Optional[str] = None,
    temperature: float = 0.2,
    timeout: int = 120,
    json_format: bool = False,
    extra_options: Optional[Dict[str, Any]] = None,
    ollama_url: Optional[str] = None,
) -> str:
    model = model or OLLAMA_MODEL
    base_url = (ollama_url or OLLAMA_URL).rstrip("/")
    url = base_url + "/api/generate"

    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, **(extra_options or {})},
    }
    if system:
        payload["system"] = system
    if json_format:
        payload["format"] = "json"

    try:
        r = requests.post(url, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError:
        raise OllamaError(
            f"Cannot reach Ollama at {base_url}. "
            "Start it with `ollama serve` and try again."
        )
    except requests.exceptions.Timeout:
        raise OllamaError(f"Ollama did not answer within {timeout} seconds. Try again or use a smaller model.")
    except requests.exceptions.RequestException as e:
        raise OllamaError(f"Ollama request failed: {e}")

    if r.status_code == 404:
        raise OllamaError(f"Model '{model}' is not available in Ollama. Run `ollama pull {model}`.")
    if not r.ok:
        raise OllamaError(f"Ollama returned HTTP {r.status_code}: {r.text[:200]}")

    return r.json().get("response", "").strip()
