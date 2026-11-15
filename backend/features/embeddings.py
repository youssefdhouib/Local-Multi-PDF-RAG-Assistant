"""
Load the Sentence-Transformers model once per process.

Previously every chat question created a new SentenceTransformer, which
re-reads the model from disk on each request. Ingestion and retrieval
must also use the *same* model, otherwise query vectors and stored
vectors would not be comparable.
"""
from functools import lru_cache

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=2)
def get_embedder(model_name: str = EMBED_MODEL_NAME):
    # Imported here so modules that only need Chroma (and the tests) do not pay
    # the cost of importing torch.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)
