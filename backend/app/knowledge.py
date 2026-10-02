"""Loads knowledge.md: YAML front matter (domain config) + markdown body (guidelines)."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

MODES = ("prompt", "rag", "hybrid")


@dataclass(frozen=True)
class Knowledge:
    domain: str
    assistant_name: str
    organization: str
    greeting: str
    mode: str
    allowed_topics: list[str]
    refusal_message: str
    emergency_message: str
    emergency_keywords: list[str]
    disclaimer: str
    input_placeholder: str
    general_knowledge: bool              # may answer in-scope questions beyond the docs
    guidelines: str                      # markdown body
    extra: dict = field(default_factory=dict)


def parse(text: str) -> Knowledge:
    meta: dict = {}
    body = text
    if text.startswith("---"):
        _, front, body = text.split("---", 2)
        meta = yaml.safe_load(front) or {}
    domain = str(meta.get("domain", "")).strip()
    if not domain:
        raise ValueError("knowledge.md must declare `domain:` in its front matter")
    mode = str(meta.get("mode", "hybrid")).strip().lower()
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    refusal = str(meta.get("refusal_message") or
                  f"I'm sorry, I can only help with {domain} questions, so I don't have knowledge in that area.")
    return Knowledge(
        domain=domain,
        assistant_name=str(meta.get("assistant_name", "Assistant")),
        organization=str(meta.get("organization", "")),
        greeting=str(meta.get("greeting", f"Hi, how can I help with {domain} questions?")),
        mode=mode,
        allowed_topics=[str(t) for t in meta.get("allowed_topics", [])],
        refusal_message=refusal,
        emergency_message=str(meta.get("emergency_message", "")),
        emergency_keywords=[str(k).lower() for k in meta.get("emergency_keywords", [])],
        disclaimer=str(meta.get("disclaimer", "")),
        input_placeholder=str(meta.get("input_placeholder", "Type your question…")),
        general_knowledge=bool(meta.get("allow_general_knowledge", mode != "rag")),
        guidelines=body.strip(),
        extra={k: v for k, v in meta.items() if k not in Knowledge.__dataclass_fields__},
    )


def load(path: Path) -> Knowledge:
    return parse(Path(path).read_text(encoding="utf-8"))
