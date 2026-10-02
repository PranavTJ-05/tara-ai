# Documents for the RAG knowledge base

Drop your `.md`, `.txt` or `.pdf` files in this folder, then run:

```bash
cd backend && uv run python -m app.ingest
```

Each file is split with semantic chunking, embedded with Gemini and stored in Supabase.
Re-running replaces the chunks of any file that changed. This README is ignored.
