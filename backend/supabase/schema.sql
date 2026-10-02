-- Run once in the Supabase SQL editor. Embedding size must match EMBED_DIM (default 384).
create extension if not exists vector;

create table if not exists chunks (
  id bigserial primary key,
  source text not null,
  digest text not null,
  chunk_index int not null,
  heading text,
  content text not null,
  embedding vector(384) not null,
  created_at timestamptz default now()
);
create index if not exists chunks_source_idx on chunks (source);
create index if not exists chunks_embedding_idx on chunks using hnsw (embedding vector_cosine_ops);

create table if not exists messages (
  id bigserial primary key,
  session_id text not null,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz default now()
);
create index if not exists messages_session_idx on messages (session_id, created_at desc);

create or replace function match_chunks(query_embedding vector(384), match_count int default 4)
returns table (id bigint, source text, heading text, content text, similarity float)
language sql stable as $$
  select id, source, heading, content, 1 - (embedding <=> query_embedding) as similarity
  from chunks order by embedding <=> query_embedding limit match_count;
$$;

-- Backend uses the service key (bypasses RLS). Lock the tables for everyone else.
alter table chunks enable row level security;
alter table messages enable row level security;
