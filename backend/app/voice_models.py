"""STT / TTS / VAD for the voice worker.

STT: Deepgram nova-3 — streaming WebSocket with built-in server-side VAD
     (vad_events=True, endpointing_ms=300).  No local ONNX inference needed,
     so Render's 0.5 vCPU is no longer saturated.
TTS: Groq Orpheus v1 — unchanged.
VAD: None — Deepgram handles end-of-turn detection internally.

Swap any function to change provider (e.g. cartesia.TTS()).
"""
import os

from livekit.plugins import deepgram, groq

from .config import settings


def build_stt():
    api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "DEEPGRAM_API_KEY is not set. "
            "Create a free account at https://console.deepgram.com and add the key to Render env vars."
        )
    return deepgram.STT(
        model="nova-3",
        language="en-US",
        interim_results=True,       # real-time partial transcripts
        smart_format=True,          # punctuation + formatting
        vad_events=True,            # server-side VAD; replaces Silero on CPU
        endpointing_ms=300,         # 300ms silence → end of utterance
        filler_words=False,
        api_key=api_key,
    )


def build_tts():
    return groq.TTS(model="canopylabs/orpheus-v1-english", voice="autumn", api_key=settings.groq_api_key)


def build_vad():
    """Deepgram handles VAD server-side; return None to skip local Silero inference."""
    return None


TERMS_URL = "https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english"


def tts_available() -> bool:
    """Probe Groq TTS once. The Orpheus model needs a one-time terms acceptance by the org admin; until then
    every synthesis fails with 400. When unavailable we skip server TTS and the browser reads replies aloud."""
    import logging

    import httpx
    try:
        r = httpx.post("https://api.groq.com/openai/v1/audio/speech", timeout=20,
                       headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                       json={"model": "canopylabs/orpheus-v1-english", "voice": "autumn", "input": "Hi.",
                             "response_format": "wav"})
    except httpx.HTTPError:
        return True                      # network blip: don't downgrade on a transient error
    if r.status_code == 400 and "terms" in r.text.lower():
        logging.getLogger("tara").warning("Groq TTS needs terms accepted -> %s . Using browser speech meanwhile.", TERMS_URL)
        return False
    return r.status_code < 400
