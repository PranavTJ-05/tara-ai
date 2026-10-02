"""Guardrails. Domain-agnostic code: the *domain* comes from knowledge.md.

Layers (all enforced in code, never left to the model alone):
  input  : length cap -> prompt-injection screen -> emergency screen -> PII redaction
  model  : structured output carries `in_scope` / `injection_attempt`; see pipeline.py
  output : off-topic -> fixed refusal, system-prompt leak block, PII redaction
"""
import re
import unicodedata
from dataclasses import dataclass

from .config import settings
from .knowledge import Knowledge

# Planted in the system prompt. If it ever shows up in an answer, the prompt leaked.
CANARY = "TARA-CANARY-7f3a91"

INJECTION_REFUSAL = "I can't help with that one, but I'm happy to answer questions about my own subject."

_INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier|your) (instructions|rules|prompt|guidelines)",
    r"disregard (all |any |the )?(previous|prior|above|earlier|your) ",
    r"forget (all |everything |your )?(previous|prior|above|earlier|instructions|rules)",
    r"(reveal|show|print|repeat|display|tell me|leak|output) (me )?(your |the )?(system|initial|hidden|original|secret) (prompt|instructions|message|rules)",
    r"what (is|are|were) your (system |initial |original )?(prompt|instructions|rules)",
    r"you are now\b",
    r"\byou (must |should |will |can )?act as\b",
    r"pretend (to be|you are|you're)",
    r"\b(dan|jailbreak|developer|god|sudo|admin) mode\b",
    r"do anything now",
    r"(override|bypass|disable|turn off|remove) (your |the |all )?(safety|guardrails?|filters?|restrictions?|rules)",
    r"new (instructions|rules|persona|role)\s*:",
    r"(^|\n)\s*(system|assistant|developer)\s*:",
    r"<\s*/?\s*(system|instructions?|prompt)\s*>",
    r"\[\s*(inst|system)\s*\]",
    r"without (any )?(restrictions?|filters?|rules|limits)",
    r"hypothetically,? (if )?you (had|were|could)",
    r"for (educational|research) purposes only,? (ignore|bypass)",
]
_INJECTION_RE = [re.compile(p, re.I) for p in _INJECTION_PATTERNS]

# ── PII ──────────────────────────────────────────────────────────────────
_PII = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),            # Luhn-checked below
    ("AADHAAR", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3,4}[\s.-]\d{3,4}(?:[\s.-]\d{2,4})?(?!\w)")),
    ("DOB", re.compile(r"\b(?:dob|date of birth|born on)\s*[:\-]?\s*[\w/ ,.-]{6,20}", re.I)),
    ("MRN", re.compile(r"\b(?:mrn|medical record(?: number)?|patient id)\s*[:#-]?\s*[A-Z0-9-]{4,}", re.I)),
]


def _luhn(digits: str) -> bool:
    nums = [int(c) for c in digits][::-1]
    total = sum(n if i % 2 == 0 else (n * 2 - 9 if n * 2 > 9 else n * 2) for i, n in enumerate(nums))
    return total % 10 == 0


def redact_pii(text: str, allow: frozenset[str] = frozenset()) -> tuple[str, list[str]]:
    """Replace PII with [TYPE] placeholders. Returns (clean_text, types_found).
    `allow` = exact strings (the operator's own contact details) that may pass through."""
    found: list[str] = []

    def sub(label: str):
        def _repl(m: re.Match) -> str:
            raw = m.group(0)
            if raw.strip() in allow:
                return raw
            if label == "CARD":
                digits = re.sub(r"\D", "", raw)
                if not (13 <= len(digits) <= 19 and _luhn(digits)):
                    return raw
            if label == "PHONE" and len(re.sub(r"\D", "", raw)) < 10:
                return raw   # short digit runs are usually doses/ranges, not phone numbers
            found.append(label)
            return f"[{label}]"
        return _repl

    for label, rx in _PII:
        text = rx.sub(sub(label), text)
    return text, sorted(set(found))


def contact_details(*sources: str) -> frozenset[str]:
    """Emails/phones that appear in the operator's own knowledge. Only these two types are ever allowlisted;
    SSN, cards, DOB, MRN etc. are never allowed through."""
    found = set()
    for text in sources:
        for label, rx in _PII:
            if label in ("EMAIL", "PHONE"):
                found.update(m.group(0).strip() for m in rx.finditer(text)
                             if label == "EMAIL" or len(re.sub(r"\D", "", m.group(0))) >= 10)
    return frozenset(found)


def normalize(text: str) -> str:
    """NFKC + strip zero-width/control chars so 'i​gnore' can't dodge the regexes."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cf", "Cc") or ch in "\n\t")
    return re.sub(r"[ \t]+", " ", text).strip()


# ── input gate ───────────────────────────────────────────────────────────
@dataclass
class InputVerdict:
    allowed: bool
    text: str                    # cleaned + PII-redacted text safe to send to the model
    reason: str = "ok"           # ok | empty | too_long | injection | emergency
    reply: str = ""              # fixed reply when not allowed
    pii_found: list[str] = None


def check_input(raw: str, kb: Knowledge) -> InputVerdict:
    text = normalize(raw or "")
    if not text:
        return InputVerdict(False, "", "empty", "I didn't catch that. Could you say it again?", [])
    if len(text) > settings.max_input_chars:
        return InputVerdict(False, "", "too_long",
                            "That message is a bit long for me. Could you shorten it to the key question?", [])
    lowered = text.lower()
    if any(rx.search(lowered) for rx in _INJECTION_RE):
        return InputVerdict(False, "", "injection", INJECTION_REFUSAL, [])
    if kb.emergency_message and any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", lowered) for k in kb.emergency_keywords):
        return InputVerdict(False, "", "emergency", kb.emergency_message, [])
    clean, pii = redact_pii(text)
    return InputVerdict(True, clean, "ok", "", pii)


# ── output gate ──────────────────────────────────────────────────────────
def check_output(text: str, kb: Knowledge, allow: frozenset[str] = frozenset()) -> tuple[str, bool]:
    """Returns (safe_text, blocked). Blocks prompt leaks, redacts PII."""
    if CANARY.lower() in text.lower():
        return INJECTION_REFUSAL, True
    clean, _ = redact_pii(text, allow)
    return clean, False
