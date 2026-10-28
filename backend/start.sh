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

# 1. Start FastAPI in the background FIRST so Render immediately detects the HTTP port
echo "Starting FastAPI on port $PORT..."
python -m uvicorn app.api:app --host 0.0.0.0 --port "$PORT" &
API_PID=$!

# 2. Wait briefly to ensure FastAPI binds before anything else
sleep 2

# 3. Start LiveKit voice agent in background (if credentials exist)
if [ -n "$LIVEKIT_URL" ] && [ -n "$LIVEKIT_API_KEY" ] && [ -n "$LIVEKIT_API_SECRET" ]; then
  echo "Starting LiveKit voice agent worker..."
  python -m app.agent start &
  AGENT_PID=$!
else
  echo "LiveKit credentials not configured; voice agent worker skipped (chat API will still work)."
fi

# 4. Handle graceful shutdown
trap 'kill $API_PID ${AGENT_PID:-}' SIGTERM SIGINT

# 5. Keep running
wait $API_PID
