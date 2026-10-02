"""Vector + conversation store. Supabase (pgvector) in production; in-memory when
SUPABASE_URL is unset, so the whole app runs and tests without any credentials."""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from ..config import settings
from ..resilience import retry


@dataclass
class Hit:
    id: str
    source: str
    heading: str
    content: str
    score: float


class Store(Protocol):
    def replace_source(self, source: str, digest: str, chunks: list, vectors: np.ndarray) -> None: ...
    def source_digest(self, source: str) -> str | None: ...
    def search(self, vector: np.ndarray, k: int) -> list[Hit]: ...
    def sources(self) -> list[dict]: ...
    def delete_source(self, source: str) -> None: ...
    def add_message(self, session_id: str, role: str, content: str) -> None: ...
    def history(self, session_id: str, limit: int) -> list[dict]: ...
    def ping(self) -> bool: ...


class LocalStore:
    """SQLite-backed store used when Supabase isn't configured. Shared safely between the API and the
    voice worker (separate processes), and survives restarts. Use ":memory:" in tests."""

    def __init__(self, path: str | Path):
        import sqlite3
        import threading
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.lock = threading.Lock()
        self._cache: tuple | None = None            # (version, matrix, rows)
        with self.lock, self.db:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript("""
              create table if not exists chunks (id integer primary key autoincrement, source text not null,
                digest text not null, chunk_index int not null, heading text, content text not null,
                vec blob not null, created_at text default current_timestamp);
              create index if not exists chunks_source on chunks(source);
              create table if not exists messages (id integer primary key autoincrement, session_id text not null,
                role text not null, content text not null);
              create index if not exists messages_session on messages(session_id, id);
            """)

    def replace_source(self, source, digest, chunks, vectors):
        rows = [(source, digest, c.index, c.heading, c.content, np.asarray(v, np.float32).tobytes())
                for c, v in zip(chunks, vectors)]
        with self.lock, self.db:
            self.db.execute("delete from chunks where source=?", (source,))
            self.db.executemany("insert into chunks(source,digest,chunk_index,heading,content,vec) values (?,?,?,?,?,?)", rows)

    def source_digest(self, source):
        with self.lock:
            r = self.db.execute("select digest from chunks where source=? limit 1", (source,)).fetchone()
        return r[0] if r else None

    def _matrix(self):
        with self.lock:
            version = self.db.execute("select count(*), coalesce(max(id),0) from chunks").fetchone()
            if self._cache and self._cache[0] == version:
                return self._cache
            rows = self.db.execute("select source,chunk_index,heading,content,vec from chunks order by id").fetchall()
        mat = np.vstack([np.frombuffer(r[4], np.float32) for r in rows]) if rows else np.zeros((0, 1), np.float32)
        self._cache = (version, mat, rows)
        return self._cache

    def search(self, vector, k):
        _, mat, rows = self._matrix()
        if not len(rows):
            return []
        scores = mat @ np.asarray(vector, np.float32)
        top = np.argsort(-scores)[:k]
        return [Hit(f"{rows[i][0]}#{rows[i][1]}", rows[i][0], rows[i][2] or "", rows[i][3], float(scores[i])) for i in top]

    def sources(self):
        with self.lock:
            rows = self.db.execute("select source, count(*), max(created_at) from chunks group by source order by source").fetchall()
        return [{"source": r[0], "chunks": r[1], "updated_at": r[2]} for r in rows]

    def delete_source(self, source):
        with self.lock, self.db:
            self.db.execute("delete from chunks where source=?", (source,))

    def add_message(self, session_id, role, content):
        with self.lock, self.db:
            self.db.execute("insert into messages(session_id,role,content) values (?,?,?)", (session_id, role, content))

    def history(self, session_id, limit):
        with self.lock:
            rows = self.db.execute("select role,content from messages where session_id=? order by id desc limit ?",
                                   (session_id, limit)).fetchall()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def ping(self):
        return True


class SupabaseStore:
    def __init__(self):
        from supabase import create_client
        self.db = create_client(settings.supabase_url, settings.supabase_key)

    @retry(attempts=3, base_delay=0.4)
    def replace_source(self, source, digest, chunks, vectors):
        self.db.table("chunks").delete().eq("source", source).execute()
        rows = [{"source": source, "digest": digest, "chunk_index": c.index, "heading": c.heading,
                 "content": c.content, "embedding": v.tolist()} for c, v in zip(chunks, vectors)]
        for i in range(0, len(rows), 100):
            self.db.table("chunks").insert(rows[i:i + 100]).execute()

    @retry(attempts=3, base_delay=0.4)
    def source_digest(self, source):
        r = self.db.table("chunks").select("digest").eq("source", source).limit(1).execute()
        return r.data[0]["digest"] if r.data else None

    @retry(attempts=3, base_delay=0.4)
    def search(self, vector, k):
        r = self.db.rpc("match_chunks", {"query_embedding": vector.tolist(), "match_count": k}).execute()
        return [Hit(str(x["id"]), x["source"], x["heading"] or "", x["content"], float(x["similarity"]))
                for x in r.data or []]

    @retry(attempts=3, base_delay=0.4)
    def sources(self):
        counts: dict[str, dict] = {}
        for start in range(0, 20000, 1000):
            page = self.db.table("chunks").select("source,created_at").range(start, start + 999).execute().data or []
            for r in page:
                c = counts.setdefault(r["source"], {"source": r["source"], "chunks": 0, "updated_at": r["created_at"]})
                c["chunks"] += 1
            if len(page) < 1000:
                break
        return sorted(counts.values(), key=lambda c: c["source"])

    @retry(attempts=3, base_delay=0.4)
    def delete_source(self, source):
        self.db.table("chunks").delete().eq("source", source).execute()

    @retry(attempts=3, base_delay=0.4)
    def add_message(self, session_id, role, content):
        self.db.table("messages").insert({"session_id": session_id, "role": role, "content": content}).execute()

    @retry(attempts=3, base_delay=0.4)
    def history(self, session_id, limit):
        r = (self.db.table("messages").select("role,content").eq("session_id", session_id)
             .order("created_at", desc=True).limit(limit).execute())
        return list(reversed(r.data or []))

    def ping(self):
        try:
            self.db.table("chunks").select("id").limit(1).execute()
            return True
        except Exception:
            return False


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = SupabaseStore() if settings.supabase_url and settings.supabase_key else LocalStore(settings.local_db)
    return _store
