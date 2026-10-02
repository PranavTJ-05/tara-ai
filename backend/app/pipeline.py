"""One entry point for chat AND voice: guardrails -> retrieve -> generate -> self-check -> guardrails."""
import logging
from dataclasses import asdict, dataclass, field

from . import guardrails, llm, retriever
from .config import settings
from .knowledge import Knowledge, load
from .prompts import build_system_prompt
from .rag.store import get_store
from .schema import Answer

log = logging.getLogger("tara")

_kb: Knowledge | None = None


def get_knowledge(reload: bool = False) -> Knowledge:
    global _kb
    if _kb is None or reload:
        _kb = load(settings.knowledge_file)
    return _kb


@dataclass
class Reply:
    status: str                    # ok | refused | injection | emergency | no_knowledge | degraded | invalid
    spoken: str                    # what voice says / chat falls back to
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    disclaimer: str = ""
    pii_redacted: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _no_knowledge(kb: Knowledge) -> str:
    return (f"I don't have reliable information on that in my knowledge base. "
            f"Please check with a qualified {kb.domain} professional.")


def _search_query(text: str, history: list[dict]) -> str:
    """Short follow-ups ('what about the dosage?') borrow the previous user turn for retrieval."""
    if len(text.split()) < 8:
        prev = [m["content"] for m in history if m["role"] == "user"]
        if prev:
            return f"{prev[-1]} {text}"
    return text


def _fixed(status: str, text: str, kb: Knowledge, pii: list[str] | None = None) -> Reply:
    return Reply(status=status, spoken=text, summary=text, pii_redacted=pii or [])


def answer(session_id: str, user_text: str) -> Reply:
    kb = get_knowledge()
    store = get_store()

    verdict = guardrails.check_input(user_text, kb)
    if not verdict.allowed:
        status = {"injection": "injection", "emergency": "emergency"}.get(verdict.reason, "invalid")
        if verdict.reason in ("injection", "emergency"):
            log.warning("blocked input session=%s reason=%s", session_id, verdict.reason)
        return _fixed(status, verdict.reply, kb)

    try:
        history = store.history(session_id, settings.history_turns)
    except Exception as e:  # self-heal: lose memory, keep serving
        log.warning("history unavailable (%s); continuing without it", e)
        history = []

    hits = []
    degraded = False
    if kb.mode in ("rag", "hybrid"):
        try:
            hits = retriever.retrieve(_search_query(verdict.text, history))
        except Exception as e:  # self-heal: hybrid falls back to guidelines-only
            log.error("retrieval failed (%s)", e)
            degraded = True

    if kb.mode == "rag" and not hits:
        reply = _fixed("degraded" if degraded else "no_knowledge", _no_knowledge(kb), kb, verdict.pii_found)
        _remember(store, session_id, verdict.text, reply.spoken)
        return reply

    result: Answer | None = None
    for strict in (False, True):                       # self-check: one stricter retry if ungrounded
        try:
            provider, result = llm.generate(build_system_prompt(kb, hits, strict), history, verdict.text)
        except RuntimeError as e:
            log.error("all LLM providers failed: %s", e)
            return _fixed("degraded", "I'm having trouble right now. Please try again in a moment.", kb)
        if result.in_scope and not result.injection_attempt and result.grounded:
            break
        if not result.in_scope or result.injection_attempt:
            break
        log.info("ungrounded answer from %s; retrying strictly", provider)

    if result.injection_attempt:
        return _remember_and_return(store, session_id, verdict.text, _fixed("injection", guardrails.INJECTION_REFUSAL, kb))
    if not result.in_scope:
        return _remember_and_return(store, session_id, verdict.text, _fixed("refused", kb.refusal_message, kb, verdict.pii_found))
    if not result.grounded:
        return _remember_and_return(store, session_id, verdict.text, _fixed("no_knowledge", _no_knowledge(kb), kb, verdict.pii_found))

    # Output gate: leak block + PII redaction on every user-visible field.
    # The operator's own phone/email (from guidelines or retrieved docs) may be spoken; nothing else may.
    allow = guardrails.contact_details(kb.guidelines, *(h.content for h in hits))
    fields = {"spoken": result.spoken or result.summary, "summary": result.summary}
    for k, v in fields.items():
        fields[k], blocked = guardrails.check_output(v, kb, allow)
        if blocked:
            return _fixed("injection", guardrails.INJECTION_REFUSAL, kb)
    clean_list = lambda items: [guardrails.check_output(i, kb, allow)[0] for i in items[:4]]  # noqa: E731
    sources = [{"n": n, "source": hits[n - 1].source, "heading": hits[n - 1].heading}
               for n in dict.fromkeys(result.sources) if 1 <= n <= len(hits)]
    reply = Reply(status="ok", spoken=fields["spoken"], summary=fields["summary"],
                  key_points=clean_list(result.key_points), next_steps=clean_list(result.next_steps[:3]),
                  sources=sources, disclaimer=kb.disclaimer, pii_redacted=verdict.pii_found)
    return _remember_and_return(store, session_id, verdict.text, reply)


def _remember(store, session_id: str, user: str, bot: str) -> None:
    try:
        store.add_message(session_id, "user", user)
        store.add_message(session_id, "assistant", bot)
    except Exception as e:  # memory is best-effort
        log.warning("could not save conversation: %s", e)


def _remember_and_return(store, session_id: str, user: str, reply: Reply) -> Reply:
    # Only real answers go into memory; refusals/injection attempts would pollute future context.
    if reply.status == "ok":
        _remember(store, session_id, user, reply.summary)
    return reply
