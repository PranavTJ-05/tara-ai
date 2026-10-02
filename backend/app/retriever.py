"""Semantic retrieval: embed the query, top-k cosine search, drop weak matches."""
from .config import settings
from .rag.embeddings import embed_query
from .rag.store import Hit, get_store


def retrieve(query: str) -> list[Hit]:
    hits = get_store().search(embed_query(query), settings.top_k)
    return [h for h in hits if h.score >= settings.min_similarity]
