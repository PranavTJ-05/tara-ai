"""LLM calls on Groq with failover: primary model -> smaller fallback model, each with retries."""
import json

import httpx

from .config import settings
from .resilience import first_success, log, retry
from .schema import Answer

URL = "https://api.groq.com/openai/v1/chat/completions"


@retry(attempts=2, base_delay=0.4)
def _call(model: str, system: str, history: list[dict], user: str) -> Answer:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    schema_hint = "\n\nReply with ONLY a JSON object matching this schema:\n" + json.dumps(Answer.model_json_schema())
    messages = [{"role": "system", "content": system + schema_hint}]
    messages += [{"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user})
    body = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 1500,
            "response_format": {"type": "json_object"}}
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"          # these are reasoning models; low keeps voice latency down
    r = httpx.post(URL, timeout=30, headers={"Authorization": f"Bearer {settings.groq_api_key}"}, json=body)
    r.raise_for_status()
    return Answer.model_validate_json(r.json()["choices"][0]["message"]["content"])


def generate(system: str, history: list[dict], user: str) -> tuple[str, Answer]:
    """Returns (model_name, Answer). Raises RuntimeError only if every model fails."""
    models = [settings.llm_model]
    if settings.llm_fallback_model and settings.llm_fallback_model != settings.llm_model:
        models.append(settings.llm_fallback_model)
    name, answer = first_success([(m, lambda m=m: _call(m, system, history, user)) for m in models])
    if name != settings.llm_model:
        log.warning("served by fallback model %s", name)
    return name, answer
