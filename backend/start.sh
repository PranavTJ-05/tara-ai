#!/usr/bin/env bash
set -e

# Ensure we are inside the backend directory and it is on PYTHONPATH
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
export PYTHONPATH="$DIR:${PYTHONPATH:-}"

# Activate virtualenv if present
if [ -d "$DIR/.venv" ]; then
  source "$DIR/.venv/bin/activate"
elif [ -d "$DIR/../.venv" ]; then
  source "$DIR/../.venv/bin/activate"
fi

PORT="${PORT:-8000}"

# Run voice agent embedded in the FastAPI process on Render (saves memory and avoids OOM)
export TARA_EMBED_WORKER=1
export TARA_SERVER_TTS=1

echo "Starting FastAPI with embedded LiveKit voice agent on port $PORT..."
exec python -m uvicorn app.api:app --host 0.0.0.0 --port "$PORT"
