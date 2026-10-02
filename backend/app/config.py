"""Environment-driven settings. Everything secret or deploy-specific lives in .env."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / "backend" / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    knowledge_file: Path = field(default_factory=lambda: Path(_env("KNOWLEDGE_FILE", str(ROOT / "knowledge" / "knowledge.md"))))
    docs_dir: Path = field(default_factory=lambda: Path(_env("DOCS_DIR", str(ROOT / "knowledge" / "docs"))))

    # Groq: LLM + speech-to-text + text-to-speech
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    llm_model: str = field(default_factory=lambda: _env("GROQ_MODEL", "openai/gpt-oss-120b"))
    llm_fallback_model: str = field(default_factory=lambda: _env("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b"))

    # Local embeddings (no API key). Changing the model/dim means re-running ingest and updating schema.sql.
    embed_model: str = field(default_factory=lambda: _env("EMBED_MODEL", "BAAI/bge-small-en-v1.5"))
    embed_dim: int = field(default_factory=lambda: int(_env("EMBED_DIM", "384")))

    supabase_url: str = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_key: str = field(default_factory=lambda: _env("SUPABASE_SERVICE_KEY"))

    livekit_url: str = field(default_factory=lambda: _env("LIVEKIT_URL"))
    livekit_api_key: str = field(default_factory=lambda: _env("LIVEKIT_API_KEY"))
    livekit_api_secret: str = field(default_factory=lambda: _env("LIVEKIT_API_SECRET"))

    allowed_origins: tuple = field(default_factory=lambda: tuple(o for o in _env("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o))

    local_db: Path = field(default_factory=lambda: Path(_env("LOCAL_DB", str(ROOT / "backend" / ".data" / "tara.db"))))

    top_k: int = 4
    min_similarity: float = 0.55   # cosine; bge-small scores ~0.8 for on-topic, ~0.4 for unrelated
    history_turns: int = 12        # previous messages replayed to the model
    max_input_chars: int = 1000


settings = Settings()
