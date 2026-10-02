"""Local embeddings via fastembed (ONNX, CPU, no API key). First use downloads the model (~130MB).
Swap this file to change embedding provider; keep EMBED_DIM and supabase/schema.sql in sync."""
import numpy as np
from fastembed import TextEmbedding

from ..config import settings

_model = None
# bge models retrieve best when the *query* (not the documents) carries this prefix.
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(settings.embed_model)
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """Unit-length document embeddings, shape (n, dim)."""
    if not texts:
        return np.zeros((0, settings.embed_dim), np.float32)
    return np.array(list(_get_model().embed(texts)), dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    return embed([_QUERY_PREFIX + text])[0]
