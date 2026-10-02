import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import api, ingest
from app.config import settings
from app.rag.chunker import Chunk
from app.rag.store import LocalStore
from tests.conftest import fake_embed


@pytest.fixture
def client(tmp_path, monkeypatch):
    original = settings.docs_dir
    object.__setattr__(settings, "docs_dir", tmp_path)          # Settings is frozen; restore afterwards
    monkeypatch.setattr(ingest, "embed", fake_embed)
    monkeypatch.setattr(api.ingest, "embed", fake_embed)
    yield TestClient(api.app)
    object.__setattr__(settings, "docs_dir", original)


def up(client, name, data=b"# Fever\nFever is a raised temperature. Rest and drink fluids.\n"):
    return client.post("/documents", files={"file": (name, data)})


def test_upload_list_delete_roundtrip(client, tmp_path):
    r = up(client, "fever.md")
    assert r.status_code == 200 and r.json()["status"] == "indexed" and r.json()["chunks"] >= 1
    docs = client.get("/documents").json()["documents"]
    assert [d["name"] for d in docs] == ["fever.md"] and docs[0]["status"] == "indexed"
    assert client.delete("/documents/fever.md").status_code == 200
    assert client.get("/documents").json()["documents"] == [] and not (tmp_path / "fever.md").exists()


@pytest.mark.parametrize("name", ["evil.exe", "script.py", "noext", "README.md"])
def test_rejects_bad_types(client, name):
    assert up(client, name).status_code == 400


def test_path_traversal_is_flattened(client, tmp_path):
    r = up(client, "../../etc/passwd.md")
    assert r.status_code == 200 and r.json()["name"] == "passwd.md"
    assert (tmp_path / "passwd.md").exists() and not (tmp_path.parent / "etc").exists()


def test_empty_and_unreadable_files_are_rejected_and_not_kept(client, tmp_path):
    assert up(client, "empty.md", b"").status_code == 400
    assert up(client, "blank.md", b"   \n\n  ").status_code == 422
    assert up(client, "broken.pdf", b"not really a pdf").status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_oversize_rejected(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD", 100)
    assert up(client, "big.md", b"x" * 500).status_code == 413


def test_reupload_replaces_instead_of_duplicating(client):
    up(client, "a.md", b"# A\nAlpha text is here.\n")
    up(client, "a.md", b"# A\nBeta text is here, completely different.\n")
    assert len(client.get("/documents").json()["documents"]) == 1


def test_localstore_persists_and_searches(tmp_path):
    path = tmp_path / "t.db"
    s = LocalStore(path)
    vecs = fake_embed(["alpha apple", "zulu zebra"])
    s.replace_source("x.md", "d1", [Chunk("alpha apple", "H", 0), Chunk("zulu zebra", "H", 1)], vecs)
    again = LocalStore(path)                                      # a second process / restart sees the data
    hit = again.search(fake_embed(["apple alpha"])[0], 1)[0]
    assert hit.content == "alpha apple" and again.source_digest("x.md") == "d1"
    assert again.sources()[0]["chunks"] == 2
    again.delete_source("x.md")
    assert s.search(fake_embed(["apple"])[0], 3) == []


def test_localstore_history_order_and_limit():
    s = LocalStore(":memory:")
    for i in range(5):
        s.add_message("s1", "user", f"m{i}")
    assert [m["content"] for m in s.history("s1", 3)] == ["m2", "m3", "m4"] and s.history("s2", 3) == []
