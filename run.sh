#!/bin/sh
# One command to run Blink X locally:  ./run.sh   then open http://localhost:8000
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8000}"
if command -v uv >/dev/null 2>&1; then
  exec uv run --python 3.12 --with-requirements requirements.txt uvicorn backend.main:app --port "$PORT"
fi
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
exec .venv/bin/uvicorn backend.main:app --port "$PORT"
