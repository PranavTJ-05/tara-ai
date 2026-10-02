# 04 - Prompt-only (long-context) vs RAG vs Hybrid for the voice chatbot platform

Date: 2026-09-29. Angle: the plain "GPT wrapper" (system prompt + knowledge + workflow in context, no vector DB) compared to RAG.
Confidence notes: prices and doc claims are from primary docs fetched today; latency numbers are from third-party blog benchmarks (marked "3rd-party") and should be re-measured on our own stack.

## TL;DR
- If a client's knowledge is under about 30-50k tokens (roughly 20-40 pages), prompt-only with prompt caching is cheaper to build, faster to ship, and usually more accurate than RAG. Anthropic itself says: under 200k tokens (~500 pages) "just include the entire knowledge base in the prompt".
- For voice, the practical ceiling is lower than 200k because of context rot and time-to-first-token (TTFT). Treat ~50k tokens as the soft cap and ~100k as the hard cap.
- Workflows (booking, lead capture, identity checks) should not live only in the prompt. Use a small state machine (Pipecat Flows-style nodes) with tool calls; the prompt holds persona and policy.
- Recommended product design: one `knowledge_mode` flag per client (`prompt | hybrid | rag`) behind the same agent interface.

## 1. Structuring an effective system prompt (current vendor guidance)
Sources: [Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices), [OpenAI prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching).

Recommended layout (static content first, dynamic last, which also maximises cache hits):
1. Role / persona and business identity (one short paragraph).
2. Voice-channel rules: short sentences, no markdown/lists/URLs, spell out numbers and emails, one question per turn, filler-free.
3. Knowledge/context, wrapped in tags. Claude guidance: use XML tags (`<instructions>`, `<context>`, `<document><source>..</source><document_content>..</document_content></document>`) so instructions, data and inputs are not confused.
4. Rules and guardrails: scope ("only answer from <knowledge>"), what to do when unknown ("say you don't have that and offer a human handoff"), escalation triggers, forbidden topics, PII handling.
5. Workflow: brief description of goals and tools; the step logic itself belongs in a state machine (section 4).
6. Output format: for voice, plain speakable text; for structured turns, tool calls or structured outputs rather than prose parsing.
7. Few-shot examples: 3-5 short example exchanges, including at least one refusal and one handoff, tagged `<example>`.

Long-context specifics from Anthropic's guide: put long documents at the top and the query/instructions at the end ("queries at the end can improve response quality by up to 30 percent in tests"); tag documents with source metadata; for long-document tasks, ask the model to quote relevant passages first (this costs tokens and latency, so in voice use it only in an internal/hidden reasoning step or skip it for small KBs).

## 2. When prompt-only beats RAG

### Why it wins for small KBs
- No chunking, embedding, retrieval-miss failure modes. Anthropic's Contextual Retrieval post measured a top-20 retrieval failure rate of 5.7% for plain embeddings, 3.7% with contextual embeddings (-35%), 2.9% with contextual embeddings + BM25 (-49%), and a 67% reduction with reranking. That means even tuned RAG still misses ~2-3% of queries, and untuned RAG more. Prompt-only has 0% retrieval misses by construction. [Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)
- No extra hop: RAG adds an embedding call plus vector search (typically tens to a few hundred ms) before the LLM can start, which is the most latency-sensitive part of a voice pipeline.
- Whole-KB reasoning works (comparisons, "what's the cheapest plan that includes X").
- Zero infra per client: config is a text file.

### Cost with prompt caching (verified prices, per million tokens)
| Provider / model | Base input | Cached read | Cache write | Source |
|---|---|---|---|---|
| Claude Haiku 4.5 | $1 | $0.10 | $1.25 (5m) / $2 (1h) | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| Claude Sonnet 5.5 | $2 | $0.20 | $2.50 (5m) / $4 (1h) | same |
| Gemini 3.8 Flash | $0.75 (intro through 2026-12-31, then $1.50) | $0.075 (then $0.15) | storage $0.50/M-token/hr (explicit) | [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| OpenAI GPT-5.6+ | model-specific | 0.1x | 1.25x, 30-min retention | [OpenAI caching](https://developers.openai.com/api/docs/guides/prompt-caching) |

Worked example (my arithmetic): a 50k-token knowledge prompt, one LLM call per turn, 10 turns per call:
- Haiku 4.5 uncached: 50k x $1/M = $0.05 per turn, $0.50 per call. Cached: $0.005 per turn, about $0.06 per call including one 1.25x write.
- Sonnet 5.5 cached: $0.01 per turn.
- Gemini 3.8 Flash cached: about $0.004 per turn (intro price).
A 100-call/day client on Haiku is roughly $6/day for the knowledge tokens (before output tokens). Small RAG stacks (a vector DB, embeddings, rerank) run cheaper per token but add fixed monthly cost and engineering per client.

Caching caveats:
- Anthropic cache TTL is 5 min by default (1 h optional at 2x write). A live voice call refreshes it every turn, but the first call after idle pays the write. Low-traffic clients should use the 1-hour TTL or accept the write cost. Cache hits need an identical prefix, so no timestamps or per-caller data before the knowledge block.
- OpenAI needs at least 1,024 tokens and holds 30 min after last use (GPT-5.6+ per the doc); Gemini implicit caching needs 2,048 (2.5 models) to 4,096 (3.x Flash) minimum tokens. Gemini and OpenAI docs I fetched did not quantify the latency gain; Anthropic reports up to 85% latency reduction for long prompts (100k-token example 11.5 s to 2.4 s, [Anthropic announcement](https://www.anthropic.com/news/prompt-caching); 2024 figure, model-dependent). Measure TTFT with a warm cache on our target model.
- Claude 4.7+ tokenizers produce roughly 30% more tokens for the same text; budget for that when sizing a KB.

### Accuracy degradation in long context
- Lost in the middle (Liu et al., TACL 2024): accuracy drops 30%+ when the relevant fact is in the middle of the context vs. the start/end.
- Context rot ([Chroma 2025](https://www.trychroma.com/research/context-rot)): tested 18 models (GPT-4.1, Claude 4, Gemini 2.5, Qwen3); all degrade as input grows, even on simple tasks; degradation is worse when question and answer are semantically dissimilar (typical for real customers, who do not use the KB's wording) and with distractors (near-duplicate policies, e.g. two price lists). On LongMemEval, focused ~300-token prompts beat full ~113k-token prompts across all model families. Claude models hallucinated least on distractors, GPT models produced more confident wrong answers (per Chroma).
- Implication: prompt-only quality is a curve, not a cliff. Under ~20-30k tokens of clean, non-duplicated content the effect is small; above ~100k expect measurable misses on paraphrased questions. Confirm with our own eval set per client (section 6).

### Rule-of-thumb thresholds (my synthesis, to validate)
| KB size (tokens) | Recommended |
|---|---|
| < 20k (FAQ, hours, services, pricing) | Prompt-only |
| 20k-60k | Prompt-only if content is structured and the eval passes; else hybrid |
| 60k-200k | Hybrid: core in prompt, rest via retrieval |
| > 200k, frequently updated, or many docs | RAG (with core policy still pinned in prompt) |
Also route to RAG or hybrid when: content changes hourly (catalog/inventory: use a tool instead), per-caller data is needed (use tool calls to CRM), or per-client access control is required inside a shared KB.

## 3. Hybrid pattern
- Cached system prompt (stable prefix): persona, rules, workflow summary, top FAQs/policies/pricing (the ~20% of content that answers ~80% of questions, drawn from real call transcripts).
- Retrieval as a tool, not automatic pre-retrieval: expose `search_knowledge(query)` and let the model call it when the pinned content does not contain the answer. This avoids the RAG latency on most turns, at the cost of a tool round trip (an extra LLM call, roughly +0.5-1.5 s) on the long tail. Mitigations: a spoken filler ("let me check that") emitted before the tool call, and parallel speculative retrieval on the final transcript for hybrid-mode clients.
- Retrieved chunks go after the cached prefix (in the user turn or tool result) so cache hits are unaffected.
- Use Contextual Retrieval (chunk-context prefix + BM25 + embeddings, optionally rerank) for the long-tail index; Anthropic reports the 49% / 67% failure reductions above.
- Prompt instruction: "If the answer is not in <knowledge> and search returns nothing, say so and offer a callback."

## 4. Workflows: prompt vs function calling vs state machine
| Approach | Reliability | Latency/cost | Use for |
|---|---|---|---|
| Steps written in the prompt | Fine for 2-4 simple steps; degrades with more steps, longer calls, and context rot | Cheapest | Greeting, FAQ, simple lead capture |
| Prompt + tools (LLM decides when to call) | Good for atomic actions (book, lookup, transfer); wrong-call and skipped-step risk grows with tool count | +1 LLM round trip per tool | Booking, CRM lookup, handoff |
| State machine / graph (Pipecat Flows, LangGraph) | Highest: each node has a narrow prompt, only the tools valid in that state, explicit transitions | Smaller per-node prompts, so lower TTFT; more dev effort | Identity verification, multi-step intake, payments, regulated flows |

Evidence: Pipecat's docs and Daily's write-up state monolithic prompts with many tools "lead to hallucinations and lower accuracy," and Flows models the agent as nodes with their own context, functions and transitions, restricting tools until conditions (e.g. identity verification) are met. [Pipecat Flows intro](https://docs.pipecat.ai/guides/features/pipecat-flows), [Daily blog](https://www.daily.co/blog/beyond-the-context-window-why-your-voice-agent-needs-structure-with-pipecat-flows/). As of pipecat-ai 1.5.0 Flows ships inside the core package (`pipecat.flows`), per search results; verify against the installed version. Caveat: these are vendor claims without published benchmark numbers; validate via our own task-completion evals.

Voice-specific concerns:
- Every extra LLM call (tool round trip, node transition) is felt as dead air; pre-speak a filler before slow tools.
- Interruptions (barge-in): context must record only what was actually spoken; state machines make it easier to resume the same node.
- ASR errors: names, emails and phone numbers need read-back confirmation as an explicit node, not a prompt hope.
- Keep tool schemas small; tool definitions cost tokens too (Haiku 4.5 adds ~496 system tokens when tools are present, per Anthropic pricing page).
- Node-scoped prompts change the prefix; keep the large knowledge block in the shared, cached prefix and vary only the tail per node.

## 5. Model choice for voice latency
Voice budget: target ~800 ms median voice-to-voice (Kwindla Hultman Kramer, Pipecat co-creator, 1,500 ms tolerable for POC), split roughly 200 ms each for transport, STT+endpointing, LLM TTFT, TTS ([Pipecat latency summaries via search](https://modal.com/blog/low-latency-voice-bot), [Chanl](https://www.channel.tel/blog/voice-ai-pipeline-stt-tts-latency-budget); 3rd-party).

TTFT numbers, all 3rd-party and dated, on 10k-token prompts ([kunalganglani benchmark](https://www.kunalganglani.com/blog/llm-api-latency-benchmarks-2026), [dev.to test](https://dev.to/kunal_d6a8fea2309e1571ee7/5-llm-apis-tested-for-latency-real-data-2026-3e4o)):
- Gemini 2.5 Flash about 0.6 s median; Claude Haiku 4.5 about 0.8 s (another source cites ~0.2 s streaming best-case); GPT-5.4 mini on Azure about 0.9 s; GPT-4o-mini 0.7-1.5 s in Pipecat-community reports; small-tier models are 2-3x faster than frontier.
- Real-world median around 1 s is treated as the practical LLM-stage limit; these numbers exceed the 200 ms ideal, so choose the fastest tier and keep prompts cached.
Guidance: default to Haiku 4.5 / Gemini Flash / mini-class; escalate to Sonnet-class only for reasoning-heavy clients. Disable extended thinking in the voice path (adds latency). Longer context increases TTFT even with cache hits (cache skips compute, but attention over 50k+ tokens still costs), so re-benchmark TTFT at each client's real KB size with a warm cache. Also consider speech-to-speech/realtime models as a separate track (not covered here).

## 6. Evaluation and guardrails
Hallucination control:
- "Answer only from <knowledge>; if not present, say you don't know and offer handoff." Plus few-shot refusal examples.
- Quote-then-answer (hidden reasoning step) for larger KBs; Chroma found Claude abstained better than GPT on distractors, so measure per model.
- Post-hoc check for high-risk facts (prices, hours, legal/medical): have a tool return the canonical value rather than trusting memory of the prompt.
- Restrict claims about actions: the bot must not say "booked" unless the booking tool returned success.

Prompt injection: callers can say "ignore your instructions". Mitigate with: instruction hierarchy in system prompt, no secrets or internal URLs in the prompt (assume the prompt is extractable), least-privilege tools with server-side validation of every argument, confirmation for side effects, rate limits, and never letting retrieved documents or tool output be treated as instructions (wrap in tags, label as data). Especially important in RAG mode with client-editable documents.

Eval sets (build before prompt tuning):
- 50-200 real or synthetic caller utterances per client, including paraphrases (Chroma shows low question-answer similarity hurts most), out-of-scope questions, adversarial/injection attempts, and multi-turn workflow scripts.
- Metrics: answer correctness (LLM-judge with human-labelled gold), refusal correctness, workflow completion rate, tool-call accuracy, TTFT p50/p95, cost per call.
- Run the same eval on `prompt`, `hybrid`, `rag` modes; pick the cheapest mode that meets the threshold; rerun on every prompt/model/KB change (CI gate). Placement A/B: knowledge position and query-at-end.

## 7. Decision matrix and mode flag
| Client type | Typical KB | Mode | Notes |
|---|---|---|---|
| Local service business (salon, clinic front desk, restaurant): hours, services, pricing, booking | 2-15k tokens | prompt | Booking via tool/state machine; live availability from API |
| Small SaaS/agency with FAQ + pricing + policies | 15-50k | prompt, else hybrid | Gate on eval |
| E-commerce with catalogue/orders | Large, volatile | hybrid or tool-based (product search API) | Order status via tools, policies pinned |
| Real estate/car listings | Volatile inventory | tools/RAG over listings + prompt for policy | Freshness beats caching |
| Enterprise/support with manuals, many docs | 200k+ | rag (+ pinned core) | Contextual Retrieval + rerank |
| Regulated (healthcare, finance) | any | Prompt or hybrid + state machine + verbatim-quote answers | Compliance, audit logs |
| Low call volume (< ~20 calls/day) | any | prompt with 1h cache TTL, or hybrid | Cache may go cold; RAG has no cold-cache penalty |

One-flag design (per-client config):
```yaml
knowledge:
  mode: prompt | hybrid | rag        # default chosen by token count at ingest
  pinned_docs: [faq.md, pricing.md]  # rendered into the cached system prefix (prompt/hybrid)
  index: kb_client_123               # vector index, used for hybrid/rag
  max_pinned_tokens: 40000
  cache_ttl: 5m | 1h
model: { voice: haiku-4.5, fallback: sonnet-5.5 }
workflow: flows/booking.yaml         # state machine, independent of mode
```
Implementation: an `assemble_context(client, turn)` function builds the prefix (persona + rules + pinned docs), and registers the `search_knowledge` tool only when mode is hybrid/rag; in `rag` mode with no pinned docs, optionally do pre-retrieval per turn. At ingest, count tokens and suggest a mode; refuse `prompt` above `max_pinned_tokens`. Everything else (workflow, guardrails, evals) is mode-agnostic, so the same eval suite can compare modes.

## Recommendation
1. Ship prompt-only as the default for clients with < ~40k tokens of knowledge; use cached Haiku 4.5 or Gemini Flash-class models.
2. Build the workflow layer as a state machine with tool calls from day one (Pipecat Flows if Pipecat is the runtime); keep prompts for persona, policy and knowledge.
3. Add hybrid (`search_knowledge` tool) when the eval shows misses or KB exceeds ~50k; keep full RAG for large/volatile corpora.
4. Gate every client launch and every change on an eval set; track TTFT p95 and cost/call per client.

## Open risks
- Latency numbers here are 3rd-party and vary by region/load; measure our own TTFT at 10k/50k/100k tokens with warm cache on each candidate model before fixing thresholds.
- The 20/50/200k thresholds are heuristics; context rot is model- and content-dependent (duplicated policies hurt most).
- Cache economics for low-traffic clients (5-min TTL, write premium) and provider pricing changes (Gemini 3.8 Flash intro price doubles 2027-01-01; Sonnet 5 introductory pricing was made permanent).
- Model versions move fast (docs list Claude 5.x, GPT-5.6, Gemini 3.x); pin versions and re-run evals on upgrades.
- Prompt injection and prompt extraction remain unsolved; rely on tool-side authorization, not prompt rules.
- Data residency/PII: putting client data in prompts sends it to the LLM provider on every call; check DPAs and per-region pricing (Anthropic US-only inference is a 1.1x multiplier).
- Vendor claims about state machines vs monolithic prompts lack published numbers; we should measure workflow completion ourselves.
- Not covered: speech-to-speech models, and fine-tuning as an alternative to prompting.
