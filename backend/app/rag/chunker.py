"""Semantic chunking.

1. Split text into sentences, remembering the markdown heading each one sits under.
2. Embed every sentence (with one neighbour of context on each side).
3. Start a new chunk where similarity between adjacent sentences drops into the
   lowest `breakpoint_percentile` of all gaps, i.e. where the topic shifts.
4. Enforce a max chunk size so no chunk is too big for voice-length context.
"""
import re
from dataclasses import dataclass
from typing import Callable

import numpy as np

Embedder = Callable[[list[str]], np.ndarray]

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])|\n{2,}|\n(?=[-*#\d])")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    content: str
    heading: str
    index: int


def _sentences(text: str) -> list[tuple[str, str]]:
    """[(sentence, heading)] with heading tracking."""
    out, heading = [], ""
    for block in re.split(r"\n{2,}", text):
        lines = block.strip().splitlines()
        if not lines:
            continue
        m = _HEADING.match(lines[0])
        if m:
            heading = m.group(2).strip()
            lines = lines[1:]
            if not lines:
                continue
        for s in _SENT.split("\n".join(lines)):
            s = s.strip()
            if len(s) > 1:
                out.append((s, heading))
    return out


def semantic_chunks(text: str, embedder: Embedder, *, breakpoint_percentile: int = 25,
                    max_chars: int = 1200, min_chars: int = 200) -> list[Chunk]:
    sents = _sentences(text)
    if not sents:
        return []
    if len(sents) == 1:
        return [Chunk(sents[0][0], sents[0][1], 0)]

    # Context windows (prev + cur + next) make short sentences embed more stably.
    windows = [" ".join(s for s, _ in sents[max(0, i - 1): i + 2]) for i in range(len(sents))]
    vecs = embedder(windows)
    sims = np.sum(vecs[:-1] * vecs[1:], axis=1)              # cosine (unit vectors)
    threshold = np.percentile(sims, breakpoint_percentile)

    groups, cur, cur_len = [], [0], len(sents[0][0])
    for i in range(1, len(sents)):
        topic_shift = sims[i - 1] <= threshold and cur_len >= min_chars
        heading_change = sents[i][1] != sents[i - 1][1]      # a new heading is always a new topic
        too_big = cur_len + len(sents[i][0]) > max_chars
        if topic_shift or heading_change or too_big:
            groups.append(cur)
            cur, cur_len = [], 0
        cur.append(i)
        cur_len += len(sents[i][0]) + 1
    groups.append(cur)

    chunks = []
    for n, idxs in enumerate(groups):
        heading = sents[idxs[0]][1]
        body = " ".join(sents[i][0] for i in idxs)
        chunks.append(Chunk(f"{heading}\n{body}" if heading else body, heading, n))
    return chunks
