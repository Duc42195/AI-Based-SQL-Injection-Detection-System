#!/usr/bin/env bash
# Start the whole demo: FastAPI backend + Streamlit frontend, one command.
#
#   ./run.sh                 # backend on 8000, frontend on 8501
#   API_PORT=9000 ./run.sh   # override either port
#   UI_PORT=8600 ./run.sh
#
# Ctrl-C stops both. The backend is started first and the frontend only opens
# once it answers /health, so the UI never comes up pointing at a dead API.
set -euo pipefail

cd "$(dirname "$0")"

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-8501}"
API_HOST="127.0.0.1"
LOG_DIR=".run"
API_LOG="$LOG_DIR/backend.log"

mkdir -p "$LOG_DIR"

port_busy() { (exec 3<>"/dev/tcp/$API_HOST/$1") 2>/dev/null && exec 3>&- ; }

for port_name in "API_PORT:$API_PORT" "UI_PORT:$UI_PORT"; do
  name="${port_name%%:*}"; port="${port_name##*:}"
  if port_busy "$port"; then
    echo "✗ Port $port ($name) is already in use." >&2
    echo "  Stop what is using it, or run:  $name=<other-port> ./run.sh" >&2
    exit 1
  fi
done

BACKEND_PID=""
cleanup() {
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo
    echo "Stopping backend (pid $BACKEND_PID)…"
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "▶ Backend  → http://$API_HOST:$API_PORT  (docs at /docs)"
uv run uvicorn deploy.main:app --host "$API_HOST" --port "$API_PORT" \
  --log-level warning >"$API_LOG" 2>&1 &
BACKEND_PID=$!

printf "  waiting for models to load"
for _ in $(seq 1 120); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo
    echo "✗ Backend exited during startup. Last lines of $API_LOG:" >&2
    tail -20 "$API_LOG" >&2
    exit 1
  fi
  if curl -fsS -o /dev/null "http://$API_HOST:$API_PORT/health" 2>/dev/null; then
    echo " ready."
    break
  fi
  printf "."
  sleep 1
done

if ! curl -fsS -o /dev/null "http://$API_HOST:$API_PORT/health" 2>/dev/null; then
  echo
  echo "✗ Backend did not become healthy in time. See $API_LOG" >&2
  exit 1
fi

curl -fsS "http://$API_HOST:$API_PORT/health" \
  | python3 -c 'import json,sys; b=json.load(sys.stdin)["branches"]; print("  branches:", ", ".join(f"{k}={v}" for k,v in b.items()))' \
  2>/dev/null || true

echo "▶ Frontend → http://localhost:$UI_PORT"
echo "  (backend log: $API_LOG · Ctrl-C stops both)"
echo

# SQLIDS_API_URL points app/api_client.py at this backend, so a custom
# API_PORT works without editing config.
SQLIDS_API_URL="http://$API_HOST:$API_PORT" \
  uv run streamlit run app/streamlit_app.py \
  --server.port "$UI_PORT" \
  --server.headless true
