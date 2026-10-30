"""Configurable embeddings. OpenAI uses the shared client in llm_service (no second client)."""
import numpy as np
import config
from services.llm_service import guarded, has_api_key, LLMUnavailable, LLMError

_LOCAL = {}


class OpenAIEmbedder:
    def __init__(self, model: str):
        self.model = model

    def embed(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), 64):
            batch = texts[i:i + 64]
            r = guarded(lambda c: c.embeddings.create(model=self.model, input=batch))
            out.extend(d.embedding for d in r.data)
        if len(out) != len(texts):
            raise LLMError("The embedding service returned an unexpected result.")
        return np.asarray(out, dtype="float32")


class LocalEmbedder:
    def __init__(self, model: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise LLMUnavailable("Local embeddings need sentence-transformers (pip install sentence-transformers).") from e
        if model not in _LOCAL:
            _LOCAL[model] = SentenceTransformer(model)
        self.m = _LOCAL[model]

    def embed(self, texts: list[str]) -> np.ndarray:
        try:
            return np.asarray(self.m.encode(list(texts), normalize_embeddings=True), dtype="float32")
        except Exception as e:
            raise LLMError("Local embedding failed.") from e


def get_embedder():
    if config.EMBEDDING_PROVIDER == "local":
        return LocalEmbedder(config.EMBEDDING_MODEL or "all-MiniLM-L6-v2")
    if not has_api_key():
        raise LLMUnavailable("Enter an OpenAI API key in the sidebar, or set EMBEDDING_PROVIDER=local.")
    if not config.EMBEDDING_MODEL:
        raise LLMUnavailable("Set EMBEDDING_MODEL in .env, or set EMBEDDING_PROVIDER=local.")
    return OpenAIEmbedder(config.EMBEDDING_MODEL)
