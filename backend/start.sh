#!/usr/bin/env bash
set -e

# Pre-download LiveKit agent model files (VAD / Groq plugins)
python -m livekit.agents download-files 2>/dev/null || true

# Run initial ingestion to ensure knowledge/docs are indexed
python -m app.ingest || true

# Start LiveKit voice agent in background if credentials exist
if [ -n "$LIVEKIT_URL" ] && [ -n "$LIVEKIT_API_KEY" ] && [ -n "$LIVEKIT_API_SECRET" ]; then
  echo "Starting LiveKit voice agent worker in background..."
  python -m app.agent start &
else
  echo "LiveKit credentials not detected; voice agent worker skipped (chat API will still work)."
fi

# Start FastAPI server in foreground
echo "Starting FastAPI server on port ${PORT:-8000}..."
exec uvicorn app.api:app --host 0.0.0.0 --port "${PORT:-8000}"
