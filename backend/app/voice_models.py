"""STT / TTS / VAD for the voice worker, all on Groq (one GROQ_API_KEY, no cloud project).
Swap any function to change provider (e.g. deepgram.STT(), cartesia.TTS())."""
from livekit.plugins import groq, silero

from .config import settings


def build_stt():
    return groq.STT(model="whisper-large-v3-turbo", language="en", api_key=settings.groq_api_key)


def build_tts():
    return groq.TTS(model="canopylabs/orpheus-v1-english", voice="autumn", api_key=settings.groq_api_key)


def build_vad():
    return silero.VAD.load()


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
