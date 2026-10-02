# 01 - Voice Pipeline Architecture (embeddable RAG voice widget)

Date: 2026-09-29. Method: web search only. Prices come mostly from third-party blogs and were not checked against vendor pricing pages. Re-verify before quoting to clients. Items marked (bg) are from background knowledge, not fetched.

## 1. Cascaded vs speech-to-speech (S2S)

| | Cascaded STT -> LLM -> TTS | S2S realtime (OpenAI Realtime, Gemini Live) |
|---|---|---|
| Latency | ~600-1200 ms voice-to-voice when tuned | ~300-600 ms |
| RAG control | Full. You see the transcript, control the prompt, can pre-fetch, and can cite. | Only through tool/function calls. The model decides when to call, and grounding is weaker. |
| Guardrails, logging, PII redaction | Easy, because text sits between every stage | Harder. Transcripts are a side-channel. |
| LLM choice | Any (Claude, GPT, Gemini Flash, Llama) | Locked to the vendor |
| Cost/min | ~$0.04-0.10 | gpt-realtime-2.1: ~$0.06-0.11 (mini: $0.02-0.05). Gemini 3.8 Live: ~$0.02-0.04 |

Key prices:
- OpenAI: gpt-realtime-2.1 costs $32/$64 per 1M audio tokens in/out. The mini costs $10/$20. Audio is 1 token per 100 ms of input and 1 token per 50 ms of output. Uncached long calls can reach $0.18-0.46/min, because the whole history is re-billed each turn. https://www.forasoft.com/blog/article/openai-realtime-api-pricing , https://hackernoon.com/openai-realtime-api-pricing-in-2026-real-world-data-from-4000-measured-sessions , https://developers.openai.com/api/docs/pricing
- Gemini Live: $3/M audio in and $12/M audio out, roughly $0.005 + $0.018 per minute, at 25 tokens/s. Sources disagree ($0.0368/min effective in one). https://ai.google.dev/gemini-api/docs/pricing

Verdict: use cascaded for a RAG-first widget. Accuracy, citations and auditability matter more than the last 300 ms for medical and legal clients. S2S is a good later "premium" mode (Gemini Live or gpt-realtime-mini, with retrieval as a tool).

## 2. Orchestration options

| Option | Fee | Notes |
|---|---|---|
| **LiveKit Agents** (OSS, Python/Node) + LiveKit Cloud | Cloud adds ~$0.01/min for agent sessions, plus WebRTC minutes | WebRTC transport with SFU. Built-in turn-detector model, VAD, interruptions. Strong JS client SDK. https://docs.livekit.io/agents/build/turns/ |
| **Pipecat** (OSS, Python) | Free. You host it. | Transport-agnostic (Daily WebRTC, SmallWebRTC, WebSocket). Smart Turn v3 is audio-based. Many STT/TTS plugins. |
| **Vapi** | $0.05/min platform fee. All-in $0.11-0.25/min. BYOK $0.23-0.33. | Fast to ship, but pricey and opaque. Fee stacks on top of every vendor. |
| **Retell** | $0.07/min platform. HIPAA included. | Predictable, telephony-oriented. |
| **Vocode** | OSS | Less active than Pipecat/LiveKit (bg). Skip. |
| Plain WebSocket | Free | Simplest server. You hand-build VAD, echo handling and reconnect. |

Sources: https://www.cekura.ai/blogs/livekit-vs-vapi , https://inworld.ai/resources/vapi-vs-pipecat-vs-livekit , https://particula.tech/blog/vapi-vs-retell-vs-livekit-vs-pipecat-voice-agent-platform , https://techpotions.com/compare/vapi-vs-retell

Vapi and Retell are built for phone calls. For an agency white-label web widget the margin stack is bad. Managed platforms are still the right call for the first demo.

## 3. STT / TTS vendors

STT:
- **Deepgram Nova-3** (streaming): ~$0.0043/min pay-as-you-go. **Flux** (Oct 2025) has turn detection built into the ASR: $0.0065/min English, $0.0078 multilingual, and ~200-600 ms lower latency than a separate endpointing stage. https://www.cekura.ai/blogs/deepgram-pricing , https://www.autointerviewai.com/blog/deepgram-flux-semantic-end-of-turn-stt-review-2026
- AssemblyAI streaming: similar tier (~$0.15/hr, bg). Has its own turn-detection blog: https://www.assemblyai.com/blog/turn-detection-endpointing-voice-agent
- OpenAI Whisper/gpt-4o-transcribe: not truly streaming in a cheap way. Self-hosted Whisper (faster-whisper) needs a GPU and is only worth it at volume or for data-residency reasons.

TTS (time to first audio):
- Cartesia Sonic: 40-85 ms, ~$0.03/min, best latency.
- ElevenLabs Flash v2.5: ~75 ms, best voice quality. List price $50-100 per 1M chars, so the priciest.
- Deepgram Aura-2: 90-115 ms, $0.000003/char (~$0.03-0.045/min at ~15 chars/s). Simple bundle with STT.
- OpenAI TTS: ~300 ms+ (bg). Cheap but slower.
Sources: https://deepgram.com/learn/best-text-to-speech-apis-2026 , https://voiceaibench.com/ , https://texttolab.com/blog/best-tts-for-voice-agents , https://burki.dev/blog/84-tts-comparison

Deepgram Voice Agent API (bundled STT+LLM+TTS) is ~$0.075-0.08/min standard, which is a viable single-vendor shortcut.

Rough per-minute cost of the cascaded stack, assuming ~50% talk time: STT $0.005-0.0065 + LLM (Gemini Flash / GPT-mini / Haiku class, with RAG context) $0.005-0.02 + TTS $0.02-0.04 = **~$0.03-0.07/min**. Add ~$0.01 for LiveKit Cloud or your own server.

## 4. Turn detection, VAD, barge-in

Layers:
1. VAD (Silero, runs in-browser or server) answers "is anyone speaking".
2. Endpointing decides when the turn is over. Options: silence timeout (500-800 ms, cheap but interrupts slow talkers), **semantic/model-based** (LiveKit turn-detector on transcript text; Pipecat Smart Turn v3 on audio prosody, which needs no transcript; Deepgram Flux built into the ASR).
3. Barge-in: keep VAD and turn detection running during agent playback. On user speech, cancel the LLM and TTS streams, flush the client audio buffer, and truncate the stored assistant message to what was actually spoken.

Web-specific: rely on browser echo cancellation (`getUserMedia({audio:{echoCancellation:true, noiseSuppression:true, autoGainControl:true}})`). Without it, speaker output is heard by the mic and the bot interrupts itself. WebRTC gives this reliably. A WebSocket + AudioWorklet path gets it too, but Safari behaviour varies (bg). Add a minimum-interruption-duration (~200-300 ms) and word-count threshold to ignore coughs and "uh-huh".

Sources: https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection , https://livekit.com/blog/turn-detection-and-interruption-handling , https://pypi.org/project/smart-turn-livekit/0.3.0/ , https://huggingface.co/livekit/turn-detector

## 5. Embedding in any website

- **Delivery**: one `<script src=...>` that registers a custom element (`<tara-voice-widget>`), Shadow DOM for CSS isolation, and a floating launcher button. Config via data-attributes plus a public site key, with allowed origins enforced server-side. Examples: https://github.com/Vocadesk/embed-sdk , https://www.mindstudio.ai/blog/embed-ai-voice-agent-widget-website-elevenlabs
- **iframe alternative**: stronger isolation (client CSS/JS cannot touch it), but the host page must set `allow="microphone"` on the iframe. Agencies often can't or don't, and Permissions-Policy on the host can block it. Recommendation: script tag + Shadow DOM by default, and an iframe mode as a fallback.
- **WebRTC vs WebSocket**:
  - WebRTC: Opus, native echo cancellation, jitter buffer, UDP so a lost packet does not stall the stream. Simpler client code. Needs TURN for corporate/hospital networks (bg). Needs an SFU or a server library (LiveKit, Daily, aiortc/SmallWebRTC).
  - WebSocket: trivial server and firewall-friendly, but you build capture (AudioWorklet, 16 kHz PCM), playback ring buffer, and interruption flush yourself. TCP head-of-line blocking gives audible stalls on poor mobile networks.
  - Sources: https://dev.to/aws-builders/switching-my-ai-voice-agent-from-websocket-to-webrtc-what-broke-and-what-i-learned , https://dev.to/programmingcentral/build-real-time-voice-chat-with-websockets-llms-and-web-audio-api-4mnj
- **Mic permission**: HTTPS required. Request only after a click on the launcher, with a pre-prompt explaining why. Handle denied, dismissed and "no device". Always ship a text-chat fallback.
- **iOS Safari gotchas**:
  - AudioContext and audio playback need a user gesture. Create and `resume()` the context, and play a silent buffer, inside the click handler. Mic permission generally satisfies WebRTC autoplay. https://webrtchacks.com/autoplay-restrictions-and-webrtc/
  - Audio output can reroute to the loud speaker or from headphones after getUserMedia starts. iOS does not expose output device selection. https://webrtchacks.com/guide-to-safari-webrtc/
  - Regressions occur across iOS versions (e.g. iOS 26.1 beta audio-input bug report, "No AVAudioSessionCaptureDevice"). Test on real devices. https://developer.apple.com/forums/thread/802555
  - Backgrounding or locking the phone suspends the session. In-app WKWebViews (Instagram/FB) often lack mic permission prompts. https://developer.apple.com/forums/thread/734363
  - Sample rate differs (48k vs 44.1k). Resample in a worklet. ScriptProcessorNode is deprecated. (bg)

## 6. RAG inside the latency budget

Target: time from end of user speech to first audio under ~800 ms (a 2 s pause feels broken). Sources: https://futureagi.com/blog/how-to-build-rag-powered-voice-ai-agents-2026/

Approximate budget: endpointing 200-400 ms + retrieval 50-150 ms + LLM time-to-first-token 200-400 ms + TTS first byte 40-100 ms + network 50-100 ms.

Options:
1. **Always pre-fetch on the final transcript** (recommended for a chatbot whose job is answering from a knowledge base). Run embedding, vector search and optional rerank in parallel with the turn-end confirmation. Inject the top-k (3-5 short chunks) into the prompt. No extra LLM round trip. Adds ~50-150 ms with a warm local or regional vector DB.
2. **Speculative retrieval on partial transcripts** (StreamRAG / speculative tool calling): fire the query as words arrive and re-fire if the final transcript differs a lot. Saves ~100-300 ms. https://arxiv.org/pdf/2510.02044 , https://getstream.io/blog/speculative-tool-calling-voice/
3. **Tool call** (LLM decides): costs an extra LLM round trip (~+400-800 ms), but avoids retrieval on chit-chat. Use for secondary tools (booking, handoff), not the main KB.
4. **Semantic cache / predictive pre-fetch** (VoiceAgentRAG style): cache answers for FAQ-like queries. https://arxiv.org/html/2603.02206v1
- **Filler phrases**: only for slow tool turns. Trigger after ~800-1000 ms of dead air ("Let me check that for you"). They buy ~1.5-2 s of perceived responsiveness. Not needed on the pre-fetch path.
- **Streaming**: stream LLM tokens into TTS by sentence/clause boundary. Send the first sentence short. Keep answers to 1-3 spoken sentences with a "want more detail?" pattern.
- Keep the vector store small and close: per-tenant index in pgvector, Qdrant, or similar, in the same region as the agent. Embedding call is the hidden cost (~50-100 ms for OpenAI small model), so consider a local/small embedding model or cache query embeddings.
- Voice-specific answer prompt: no markdown, no URLs read aloud, spoken numbers and dates, and "say you don't know" plus offer a human handoff when retrieval score is low. Critical for medical and legal.

## 7. Recommended lean stack

**Build A (recommended, ~$0.04-0.08/min all-in):**
- Client: custom web component (Shadow DOM) using the LiveKit JS client (WebRTC), text fallback.
- Server: LiveKit Agents (Python or Node) on LiveKit Cloud to start, self-host LiveKit + agent worker later. Or Pipecat + SmallWebRTC on a single small VM to remove the SFU fee.
- STT: Deepgram Flux (built-in turn detection) or Nova-3 + LiveKit turn detector.
- LLM: fast small model (Gemini Flash-class / GPT-mini / Claude Haiku) with pre-fetched RAG context.
- TTS: Cartesia Sonic (latency, ~$0.03/min) or Deepgram Aura-2 (one vendor with STT). ElevenLabs as an optional "premium voice" tier.
- Retrieval: pre-fetch on final (or partial) transcript, top-3, per-tenant namespace.

Rough cost per minute: STT $0.006 + LLM $0.01 + TTS $0.03 + infra $0.01 = ~$0.06. A 3-minute average conversation is about $0.18.

**Build B (fastest to launch):** Deepgram Voice Agent API (~$0.08/min) or Vapi/Retell (~$0.11-0.25/min). Higher cost and less control; good for a pilot.

**Build C (later premium):** gpt-realtime-mini or Gemini Live with retrieval as a tool, ~$0.02-0.05/min, best naturalness, weaker RAG control.

## Open risks

- Pricing figures come from secondary blogs and shift monthly. Confirm on vendor pages and model real usage (silence and hold time billed on some plans).
- Compliance: medical and law clients need BAAs/DPAs (Deepgram, LiveKit, LLM vendor), call-recording consent, retention limits, and no PII in logs. Retell advertises HIPAA included. Others need enterprise agreements. Not verified here.
- Safety: hallucinated medical/legal advice. Needs grounded-only answers, refusal rules, a disclaimer, and human-handoff.
- Safari/iOS audio behaviour changes between releases. Budget real-device test time.
- Echo, noisy environments and speakerphone use cause false barge-ins.
- Abuse and cost: public widget with a mic means a bot or a scraper can burn minutes. Need per-origin keys, rate limits, session caps and a max call duration.
- TURN and corporate firewalls block WebRTC UDP. Need TURN over 443/TCP or a WebSocket fallback.
- Accent, multilingual and medical-term STT accuracy. Use custom vocabulary/keyterms and test with client-specific jargon.
- Vendor lock-in on Flux/Cartesia. Keep STT/TTS behind an interface.
