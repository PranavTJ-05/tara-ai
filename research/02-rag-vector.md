# 02 - RAG / Vector Search for a Reusable Voice RAG Chatbot

Date: 2026-09-29. Figures marked (V) were verified on the vendor page this session; (K) are from background knowledge and should be re-checked before commit.

## 1. Vector store options

| | Pinecone | Supabase (pgvector) | Qdrant | Turso/libSQL | sqlite-vec | LanceDB |
|---|---|---|---|---|---|---|
| Model | Serverless managed | Managed Postgres | Managed or self-host | Managed SQLite, native vectors | Embedded ext. | Embedded / cloud |
| Multi-tenancy | Namespace per tenant (Starter 100, Standard 100k) (V) | RLS + `tenant_id`, or project/schema per client | Payload filter / collection | DB per tenant (cheap) (K) | file per tenant | table/dir per tenant |
| Hybrid | Sparse+dense in one index, rerank API | tsvector + pgvector + RRF (SQL) | Native sparse+dense, fusion | FTS5 + vectors, manual | FTS5 + manual | Native FTS + vector |
| Cost | Free: 2GB, 1M reads/mo; Standard $50/mo min; $0.33/GB/mo, $16-18/M reads, $4-4.5/M writes (V) | Free 500MB (pauses after 1 wk idle); Pro from $25/mo, 8GB, Micro compute $10 (V) | Free 1GB RAM/4GB disk (V); usage-based | cheap (K) | free | free / usage |
| Fit | Fast to start, no SQL | Also gives auth, storage, relational data, chat logs | Best pure-vector perf | Interesting for per-client isolation | Needs a server host | Needs a server host |

Pinecone extras: integrated inference (llama-text-embed-v2 $0.16/M tokens, multilingual-e5-large $0.08/M, 5M tokens/mo free) and rerank $2/1k requests (V). Source: https://www.pinecone.io/pricing/

Supabase: HNSW index on `vector` (or `halfvec` to halve memory), hybrid via RRF `1/(k+rank)`, default k=50 (V). Sources: https://supabase.com/pricing , https://supabase.com/docs/guides/ai/hybrid-search

Scale reality: a client with 1,000 pages is roughly 3-5k chunks of ~500 tokens. At 1024 dims float32 that is about 20 MB of vectors. Every option handles this trivially; the choice is about ops and hybrid search, not scale. Even 50 clients fits inside one 8GB Supabase Pro.

## 2. Embeddings

| Model | Dims | $/1M tokens | Notes |
|---|---|---|---|
| OpenAI text-embedding-3-small | 1536 (truncatable) | $0.02 (V) | Solid default, Matryoshka |
| OpenAI text-embedding-3-large | 3072 (truncatable to 1024/256) | $0.13 (V) | Better quality |
| Voyage voyage-4-lite / 4 / 4-large | 256/512/1024/2048 | $0.02 / $0.06 / $0.12 (V), first 200M tokens free (V) | 32k context; voyage-law-2 (legal), voyage-finance-2; rerank-2.5 $0.05 (V) |
| Cohere embed v4 | up to 1536 (K) | ~$0.12 (K, API page not verified) | Multilingual, good with rerank |
| Open source (bge-m3, nomic-embed, voyage-4-nano) | 768-1024 | self-host | Needs GPU/CPU host; use only if data cannot leave |

Cost is negligible at this scale: 1M-token corpus is $0.02-$0.12 once. Query embedding is one short string per turn. Pick by latency and quality, not price. Voyage docs: https://docs.voyageai.com/docs/embeddings ; pricing https://docs.voyageai.com/docs/pricing ; OpenAI https://developers.openai.com/api/docs/pricing

Recommendation: Voyage `voyage-4-lite` or `voyage-4` at 1024 dims (free 200M tokens covers many clients) or OpenAI 3-small truncated to 1024 if you want one fewer vendor. Store the model name and dim per tenant; changing models means a full re-embed.

## 3. Retrieval quality

- Chunking: 300-500 tokens, 10-15% overlap, split on headings/paragraphs first (structure-aware), keep the heading path and source URL/page in metadata. FAQ-style content: one Q&A per chunk. Avoid tiny (<100 tokens) chunks.
- Hybrid (BM25 + dense) with RRF matters for domain jargon, drug names, statute numbers, names.
- Contextual retrieval (Anthropic): prepend a 50-100 token LLM-generated context to each chunk before embedding and BM25. Top-20 failure rate 5.7% to 3.7% (-35%) with contextual embeddings, 2.9% (-49%) with contextual BM25 added, 1.9% (-67%) with reranking; one-time cost about $1.02 per million document tokens with prompt caching (V). Source: https://www.anthropic.com/news/contextual-retrieval . It is an ingestion-time cost only, so it adds zero query latency. Worth it.
- Reranking: retrieve 20-30, rerank to 3-5. Adds ~100-300 ms (K) so make it optional in voice; rely on hybrid+contextual first, add reranker only if eval shows gains.

## 4. Tuning for voice

Latency budget (target under ~1.0-1.5 s from end of user speech to first audio; K, typical of voice-agent guidance):
- STT endpointing/final: 200-300 ms
- Query embed: 30-100 ms
- Vector/hybrid search: 20-80 ms (same region as the app server!)
- Optional rerank: 100-300 ms
- LLM time-to-first-token: 300-500 ms (fast small model, stream)
- TTS first byte: 100-300 ms
Retrieval must fit in about 150-250 ms, so co-locate DB and server, skip rerank on the hot path or make it conditional, and stream the LLM into TTS sentence by sentence.

Answer style: system prompt forces 1-3 spoken sentences (~40-60 words), no lists, markdown, URLs or citations read aloud; offer "want more detail?". Put full sources in the text UI/transcript instead of speech.
Top-k: retrieve 8-10, pass 3-4 chunks (~1,500 tokens max) to the LLM; less context means faster TTFT.
Caching: (a) embedding cache keyed on normalized query; (b) semantic answer cache for top FAQs per tenant (Redis/Upstash or Postgres table, threshold ~0.95 cosine); (c) LLM prompt caching for the static system prompt; (d) pre-generated audio for greeting and the top ~20 FAQs. (e) Speculative retrieval: fire search on interim STT transcripts.
Query rewrite: for follow-ups ("what about the cost?"), use a cheap LLM call or fold last turn into the query; costs latency, so only when conversation history exists.

## 5. Multi-tenant, one codebase

- One tenant row = config: `tenant_id`, name, persona/system prompt, voice ID, domain rules (disclaimer text, abstain threshold, escalation phone), embedding model, allowed origins.
- Isolation: Pinecone namespace = tenant_id; or Supabase `tenant_id` column with RLS plus always-filter in the query function. For law/medical, RLS is defense in depth, and the server should use a tenant-scoped JWT or a `SECURITY DEFINER` function that takes tenant_id from the verified session, never from the client. Consider separate Supabase project per regulated client if the contract requires hard isolation.
- Ingestion with minimal code: URL, use Firecrawl or Jina Reader (`r.jina.ai/<url>`) to get markdown; PDF/docx, use Unstructured, LlamaParse, or `pymupdf4llm` + `mammoth`/`markitdown` (Microsoft) which converts PDF/docx/pptx/html to markdown in one library. Then: markdown-header split, (optional) contextualize, batch embed, upsert. One idempotent job per source keyed by `content_hash` so re-crawls only update changed docs. Run in a queue/cron (Supabase Edge Function or a small worker).
- Onboarding a client = insert tenant row + add sources + run ingest. No code changes.

## 6. Domain concerns (medical, legal)

- Citations: every chunk carries `source_title`, `url`, `page`, `section`, `last_updated`. The text UI shows sources; voice says "according to your clinic's visit policy" at most.
- Abstain: if best hybrid score below tuned threshold, or the LLM finds no supporting chunk, answer fixed fallback: "I do not have that information; I can connect you with the office at ...". Instruct the model to answer only from context and output a `grounded: true/false` flag (structured output) checked server side. Build an eval set of 30-50 in-scope and 20 out-of-scope questions per client and tune the threshold.
- Scope guardrails: no diagnosis, dosage, or legal advice; classifier or system-prompt rule routes urgent symptoms ("chest pain") to emergency instruction and human handoff; standing disclaimer at start.
- PII/PHI: do not ingest patient records; ingest only public/marketing/policy content. Redact PII in logs (regex or Presidio) before storing transcripts; short retention; encrypt at rest. If PHI can appear (voice callers state names/DOB), HIPAA needs BAAs with every processor (LLM, STT, TTS, DB host). Supabase offers HIPAA on Team plan+add-on (K, verify), Pinecone offers HIPAA on Enterprise (K, verify). Legal clients: attorney-client privilege, treat transcripts as confidential, no training on data. Recommend a "no PHI" scope for v1 to avoid this.
- Recording consent: some jurisdictions need announcing call recording (K).

## 7. Leanest stack and schema

Recommended: Supabase (Postgres) + pgvector HNSW + tsvector, Voyage voyage-4-lite (1024d) or OpenAI 3-small, markitdown for parsing, Claude Haiku-class for contextualization at ingestion, optional Voyage rerank-2.5.

```sql
create extension if not exists vector;

create table tenants (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  name text not null,
  config jsonb not null default '{}',   -- persona, voice_id, abstain_threshold, fallback_text, disclaimer
  embed_model text not null default 'voyage-4-lite',
  embed_dim int not null default 1024
);

create table sources (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  kind text check (kind in ('url','pdf','docx','faq')),
  uri text, title text,
  content_hash text, status text default 'pending',
  updated_at timestamptz default now()
);

create table chunks (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references tenants(id) on delete cascade,
  source_id uuid not null references sources(id) on delete cascade,
  content text not null,            -- raw chunk shown as citation
  context text,                     -- contextual-retrieval prefix
  heading_path text, page int,
  embedding halfvec(1024),
  fts tsvector generated always as
    (to_tsvector('english', coalesce(context,'') || ' ' || content)) stored
);
create index on chunks using hnsw (embedding halfvec_cosine_ops);
create index on chunks using gin (fts);
create index on chunks (tenant_id);

alter table chunks enable row level security;   -- policy: tenant_id = (auth.jwt()->>'tenant_id')::uuid

-- query: hybrid_search(p_tenant uuid, q text, q_emb halfvec(1024), k int)
-- two CTEs (top 30 by cosine, top 30 by ts_rank_cd), both WHERE tenant_id = p_tenant,
-- fuse with RRF 1/(50+rank), return top k with content, source uri/title/page and both scores.
```

Caveat: with HNSW plus a `tenant_id` filter, pgvector can return fewer than k rows (post-filtering); enable `hnsw.iterative_scan = relaxed_order` (pgvector 0.8+, K) or use partitioning by tenant if tenants are large. At a few thousand chunks per tenant, even exact scan with tenant filter is fast enough (K).

Query flow: STT text, embed, `hybrid_search`, threshold check (abstain), top 3-4 chunks to LLM with spoken-style prompt, stream to TTS, log (redacted) with chunk IDs.

## Recommendation: Supabase, not Pinecone

For this use case choose Supabase pgvector. Reasons: (1) hybrid search with tsvector is first-class, and jargon-heavy medical/legal text benefits; (2) one system holds tenants, config, sources, chunks, auth, RLS, transcripts and eval logs, with less glue code, which matters for an agency reusing one codebase; (3) predictable cost: $25/mo Pro (+ $10 Micro compute credit included) shared across many small clients versus Pinecone's $50/mo minimum on Standard (Starter's 100 namespaces and 1M reads/mo is fine for a prototype); (4) scale is tiny, so pgvector performance is not a constraint. Choose Pinecone only if the team wants zero SQL, needs integrated inference/rerank in one bill, or a single client grows into many millions of vectors. Keep a thin `VectorStore` interface (`upsert`, `search(tenant, query, k)`) so swapping is a day of work.

## Open risks

- Supabase Free pauses after 1 week idle (V): use Pro for any client demo/production.
- Filtered HNSW recall with multi-tenant filter; test with your data.
- Latency: region colocation of DB, LLM, STT/TTS; measure P95 end to end, not per component. Budget numbers above are estimates (K).
- Embedding model lock-in: changing models requires re-embedding all tenants.
- Compliance (HIPAA BAAs, legal confidentiality, recording consent) is unverified here; I did not confirm vendor HIPAA offerings.
- Hallucination on medical/legal answers: needs per-client eval set and abstain threshold tuning; do not rely on prompt alone.
- Stale content: schedule re-crawl and show `last_updated`.
- Pricing and model names (Voyage-4, Cohere embed v4 API price, Pinecone tiers) change quickly; Cohere API per-token prices were not verified (page showed only Model Vault hosting).
