"""Ingest knowledge/docs (+ knowledge.md body in `rag` mode) into the vector store.

    uv run python -m app.ingest          # only changed files
    uv run python -m app.ingest --force  # everything
"""
import argparse
import hashlib
import logging
from pathlib import Path

from .config import settings
from .knowledge import load
from .rag.chunker import semantic_chunks
from .rag.embeddings import embed
from .rag.store import get_store

log = logging.getLogger("tara")
SUPPORTED = {".md", ".txt", ".pdf"}


def read_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def ingest_text(source: str, text: str, force: bool = False) -> int:
    store = get_store()
    digest = hashlib.sha256(text.encode()).hexdigest()
    if not force and store.source_digest(source) == digest:
        log.info("unchanged: %s", source)
        return 0
    chunks = semantic_chunks(text, embed)
    if not chunks:
        return 0
    store.replace_source(source, digest, chunks, embed([c.content for c in chunks]))
    log.info("ingested %s -> %d chunks", source, len(chunks))
    return len(chunks)


def ingest_file(path: Path, force: bool = False) -> int:
    return ingest_text(path.name, read_file(path), force)


def remove(name: str) -> None:
    get_store().delete_source(name)


def run(force: bool = False) -> int:
    kb = load(settings.knowledge_file)
    if kb.mode == "prompt":
        log.info("mode=prompt: knowledge.md is used directly in the prompt, nothing to ingest")
        return 0
    total = 0
    if kb.mode in ("rag",):                       # in `hybrid` the guidelines already live in the prompt
        total += ingest_text("knowledge.md", kb.guidelines, force)
    for path in sorted(settings.docs_dir.rglob("*")):
        if path.suffix.lower() in SUPPORTED and path.name.lower() != "readme.md":
            total += ingest_file(path, force)
    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    print(f"done: {run(ap.parse_args().force)} chunks written")
