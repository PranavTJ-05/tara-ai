"""LiveKit voice worker. It owns only audio I/O: every reply comes from pipeline.answer(),
so voice gets exactly the same guardrails, RAG and memory as the chat UI.

    uv run python -m app.agent dev
"""
import asyncio
import json
import logging

from livekit.agents import Agent, AgentSession, JobContext, StopResponse, WorkerOptions, cli, llm

from . import pipeline
from .voice_models import build_stt, build_tts, build_vad, tts_available

log = logging.getLogger("tara")


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
        await self._publish({"type": "thinking"}, "state")
        # pipeline.answer is blocking (network); keep the audio loop responsive.
        reply = await asyncio.to_thread(pipeline.answer, self._session_id, text)
        await self._publish({"question": text, "tts": self._tts_ok, **reply.to_dict()}, "answer")
        if self._tts_ok:
            self.session.say(reply.spoken, add_to_chat_ctx=False)
        raise StopResponse()      # skip LiveKit's built-in LLM; our pipeline already answered


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    tts_ok = await asyncio.to_thread(tts_available)
    kwargs = {"tts": build_tts()} if tts_ok else {}
    session = AgentSession(stt=build_stt(), vad=build_vad(), **kwargs)
    agent = TaraAgent(ctx.room, session_id=ctx.room.name, tts_ok=tts_ok)
    await session.start(agent=agent, room=ctx.room)
    greeting = pipeline.get_knowledge().greeting
    await agent._publish({"type": "ready", "tts": tts_ok, "greeting": greeting}, "state")
    if tts_ok:
        session.say(greeting, add_to_chat_ctx=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
