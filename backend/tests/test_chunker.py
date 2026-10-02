from app.rag.chunker import semantic_chunks
from tests.conftest import fake_embed

TEXT = """# Fever
Fever is a raised body temperature. Fever often signals infection. Drink fluids during fever.

# Opening hours
The clinic opens at nine. The clinic closes at six. Sunday the clinic is closed.
"""


def test_splits_on_heading_and_keeps_heading():
    chunks = semantic_chunks(TEXT, fake_embed, min_chars=20)
    assert len(chunks) >= 2
    assert {c.heading for c in chunks} == {"Fever", "Opening hours"}


def test_respects_max_size():
    long = ". ".join(f"Sentence number {i} about nothing in particular" for i in range(60)) + "."
    assert all(len(c.content) < 400 for c in semantic_chunks(long, fake_embed, max_chars=300, min_chars=50))


def test_empty_and_single():
    assert semantic_chunks("", fake_embed) == []
    assert len(semantic_chunks("Just one sentence.", fake_embed)) == 1


def test_short_sections_are_never_merged_across_headings():
    text = "# A\nAlpha one is here. Alpha two follows.\n\n# B\nBeta one is here. Beta two follows.\n\n# C\nGamma one is here."
    chunks = semantic_chunks(text, fake_embed, min_chars=500)
    assert [c.heading for c in chunks] == ["A", "B", "C"]
