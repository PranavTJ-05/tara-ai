"""LiveKit voice worker. It owns only audio I/O: every reply comes from pipeline.answer(),
so voice gets exactly the same guardrails, RAG and memory as the chat UI.

    uv run python -m app.agent dev
"""
import asyncio
import json
import logging
import os

from livekit.agents import Agent, AgentSession, JobContext, JobExecutorType, StopResponse, WorkerOptions, cli, llm

from . import pipeline
from .config import settings
from .voice_models import build_stt, build_tts, build_vad, tts_available

log = logging.getLogger("tara")
AGENT_NAME = "tara"


class TaraAgent(Agent):
    def __init__(self, room, session_id: str, tts_ok: bool):
        super().__init__(instructions="Handled by the guardrail pipeline.")
        self._room = room
        self._session_id = session_id
        self._tts_ok = tts_ok          # False -> the browser speaks the reply instead

    async def _publish(self, payload: dict, topic: str) -> None:
        try:
            await self._room.local_participant.publish_data(json.dumps(payload).encode(), topic=topic, reliable=True)
        except Exception as e:  # UI updates are a bonus; speech must still happen
            log.warning("could not publish %s: %s", topic, e)

    async def on_user_turn_completed(self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage) -> None:
        text = new_message.text_content or ""
        # Immediately publish transcribed text so the frontend displays STT in real-time
        await self._publish({"type": "thinking", "text": text}, "state")
        # pipeline.answer is blocking (network); keep the audio loop responsive.
        reply = await asyncio.to_thread(pipeline.answer, self._session_id, text)
        await self._publish({"question": text, "tts": self._tts_ok, **reply.to_dict()}, "answer")
        if self._tts_ok:
            self.session.say(reply.spoken, add_to_chat_ctx=False)
        raise StopResponse()      # skip LiveKit's built-in LLM; our pipeline already answered


def _server_tts() -> bool:
    """Groq TTS + the terms probe are too heavy for Render's 512MB box. Opt in with TARA_SERVER_TTS=1."""
    flag = os.getenv("TARA_SERVER_TTS", "").strip().lower()
    if flag in ("0", "false", "no"):
        return False
    if flag in ("1", "true", "yes"):
        return tts_available()
    return os.getenv("TARA_EMBED_WORKER", "").strip().lower() not in ("1", "true", "yes") and tts_available()


def prewarm(proc) -> None:
    # Deepgram STT has built-in server-side VAD; no local ONNX model to prewarm.
    pass


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    tts_ok = await asyncio.to_thread(_server_tts)
    kwargs = {"tts": build_tts()} if tts_ok else {}
    # Explicitly pass vad=None so AgentSession does NOT fall back to local silero ONNX inference
    session = AgentSession(stt=build_stt(), vad=None, **kwargs)
    agent = TaraAgent(ctx.room, session_id=ctx.room.name, tts_ok=tts_ok)

    # Stream real-time user speech transcriptions directly to frontend data channel
    def on_transcription(ev):
        if ev.transcript:
            asyncio.create_task(
                agent._publish(
                    {"type": "transcript", "text": ev.transcript, "is_final": ev.is_final},
                    "transcript"
                )
            )

    session.on("user_input_transcribed", on_transcription)

    await session.start(agent=agent, room=ctx.room)
    greeting = pipeline.get_knowledge().greeting
    await agent._publish({"type": "ready", "tts": tts_ok, "greeting": greeting}, "state")
    if tts_ok:
        session.say(greeting, add_to_chat_ctx=False)


def worker_options() -> WorkerOptions:
    # THREAD executor: forking a child process on Render's 512MB plan OOMs as soon as a voice job starts.
    return WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
        ws_url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
        agent_name=AGENT_NAME,
        job_executor_type=JobExecutorType.THREAD,
        num_idle_processes=0,
        port=0,
        load_threshold=1.0,
    )


async def run_embedded_worker() -> None:
    """Share the FastAPI process so Render does not run two Python interpreters."""
    from livekit.agents.worker import AgentServer
    server = AgentServer.from_server_options(worker_options())
    log.info("starting in-process LiveKit worker name=%s", AGENT_NAME)
    await server.run(devmode=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli.run_app(worker_options())
