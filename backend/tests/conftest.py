import numpy as np
import pytest

from app import pipeline
from app.knowledge import parse
from app.rag import store as store_mod

KB_TEXT = """---
domain: medical
assistant_name: Tara
mode: hybrid
allowed_topics: [symptoms]
refusal_message: "REFUSED-OFFTOPIC"
emergency_message: "CALL-EMERGENCY"
emergency_keywords: [chest pain, stroke]
disclaimer: "Not a diagnosis."
---
# Guidelines
Opening hours are 9 to 6. Call the clinic on 415-555-0100 or desk@clinic.org.
"""


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(pipeline, "_kb", parse(KB_TEXT))
    monkeypatch.setattr(store_mod, "_store", store_mod.LocalStore(":memory:"))
    yield


def fake_embed(texts):
    """Deterministic bag-of-letters embedding: similar text -> similar vector."""
    out = np.zeros((len(texts), 26), np.float32)
    for i, t in enumerate(texts):
        for ch in t.lower():
            if "a" <= ch <= "z":
                out[i, ord(ch) - 97] += 1
    return out / np.clip(np.linalg.norm(out, axis=1, keepdims=True), 1e-9, None)
