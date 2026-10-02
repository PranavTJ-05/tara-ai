"""HTTP API for the web UI: chat, LiveKit token, config, health."""
import logging
import re
import threading
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import ingest, pipeline
from .config import settings
from .rag.store import get_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
@asynccontextmanager
async def lifespan(_app):
    """Index anything dropped into knowledge/docs while the server was off (unchanged files are skipped)."""
    def work():
        try:
            ingest.run()
        except Exception as e:  # never block startup on indexing
            logging.getLogger("tara").warning("startup indexing skipped: %s", e)
    threading.Thread(target=work, daemon=True).start()
    yield


app = FastAPI(title="Tara assistant", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                   allow_methods=["GET", "POST"], allow_headers=["*"])


class ChatIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64, pattern=r"^[\w-]+$")
    message: str = Field(max_length=4000)


@app.get("/config")
def config():
    kb = pipeline.get_knowledge()
    return {"assistant_name": kb.assistant_name, "organization": kb.organization, "domain": kb.domain,
            "greeting": kb.greeting, "mode": kb.mode, "disclaimer": kb.disclaimer,
            "input_placeholder": kb.input_placeholder,
            "starter_questions": list(kb.extra.get("starter_questions", []))}


@app.post("/chat")
def chat(body: ChatIn):
    return pipeline.answer(body.session_id, body.message).to_dict()


@app.get("/token")
def token(session_id: str | None = None):
    """Mint a LiveKit access token. The room name doubles as the memory session id."""
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        raise HTTPException(503, "LiveKit is not configured")
    from livekit import api
    room = session_id or f"s-{uuid.uuid4().hex[:12]}"
    jwt = (api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
           .with_identity(f"user-{uuid.uuid4().hex[:8]}")
           .with_grants(api.VideoGrants(room_join=True, room=room))
           .to_jwt())
    return {"token": jwt, "url": settings.livekit_url, "room": room}


@app.post("/reload")
def reload_knowledge():
    """Re-read knowledge.md without restarting (docs still need `python -m app.ingest`)."""
    kb = pipeline.get_knowledge(reload=True)
    return {"domain": kb.domain, "mode": kb.mode}


@app.get("/health")
def health():
    checks = {
        "knowledge": True,
        "groq_key": bool(settings.groq_api_key),
        "store": get_store().ping(),
        "livekit": bool(settings.livekit_url and settings.livekit_api_key),
    }
    try:
        pipeline.get_knowledge()
    except Exception:
        checks["knowledge"] = False
    ok = checks["knowledge"] and checks["groq_key"] and checks["store"]
    return {"status": "ok" if ok else "degraded", **checks}


# ── documents (the RAG knowledge base) ───────────────────────────────────
MAX_UPLOAD = 10 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^\w.\- ]")


def _safe_name(name: str) -> str:
    name = _SAFE_NAME.sub("_", (name or "").replace("\\", "/").split("/")[-1]).strip(" .")
    if not name or name.lower() == "readme.md" or "." + name.rsplit(".", 1)[-1].lower() not in ingest.SUPPORTED:
        raise HTTPException(400, "Upload a .pdf, .md or .txt file")
    return name


@app.get("/documents")
def list_documents():
    indexed = {d["source"]: d for d in get_store().sources()}
    docs = []
    for path in sorted(settings.docs_dir.glob("*")):
        if path.suffix.lower() in ingest.SUPPORTED and path.name.lower() != "readme.md":
            d = indexed.get(path.name)
            docs.append({"name": path.name, "size": path.stat().st_size, "chunks": d["chunks"] if d else 0,
                         "status": "indexed" if d else "pending"})
    return {"documents": docs}


@app.post("/documents")
def upload_document(file: UploadFile = File(...)):
    name = _safe_name(file.filename)
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 10 MB")
    if not data:
        raise HTTPException(400, "File is empty")
    settings.docs_dir.mkdir(parents=True, exist_ok=True)
    path = settings.docs_dir / name
    path.write_bytes(data)
    try:
        chunks = ingest.ingest_file(path, force=True)
    except Exception as e:  # unreadable PDF, store down...
        path.unlink(missing_ok=True)
        logging.getLogger("tara").error("ingest failed for %s: %s", name, e)
        raise HTTPException(422, "Couldn't read that file. Try a text-based PDF, .md or .txt.")
    if chunks == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "No readable text found in that file")
    return {"name": name, "size": len(data), "chunks": chunks, "status": "indexed"}


@app.delete("/documents/{name}")
def delete_document(name: str):
    name = _safe_name(name)
    path = settings.docs_dir / name
    if not path.exists():
        raise HTTPException(404, "Document not found")
    ingest.remove(name)
    path.unlink()
    return {"deleted": name}
