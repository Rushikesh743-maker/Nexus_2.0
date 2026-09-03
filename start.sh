#!/usr/bin/env bash
#
# One-command setup and launch for NEXUS + the criminal-network-analysis
# backend. Safe to run again any time — each step is skipped once it's done.
#
#   ./start.sh          front end on :5173, API on :8000 (development)
#   ./start.sh prod     build the front end, then serve everything from :8000
#
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-dev}"
PORT="${PORT:-8000}"

# ── Python backend ───────────────────────────────────────────────────────────
if [ ! -d venv ]; then
  echo "==> Creating Python virtual environment"
  python3 -m venv venv
fi

echo "==> Installing Python dependencies"
./venv/bin/pip install -q -r backend/requirements.txt

if [ ! -f data/raw/firs.json ]; then
  echo "==> Generating the synthetic case corpus"
  ./venv/bin/python3 data/generator.py
fi

# Scanned FIRs are optional: they are only readable when tesseract is present,
# and the System view reports honestly when it is not.
if [ ! -d data/scans ] && ./venv/bin/python3 -c "import PIL" 2>/dev/null; then
  echo "==> Rendering the paper-only FIRs (optional)"
  ./venv/bin/python3 data/make_scans.py || echo "    skipped"
fi

# ── Node front end ───────────────────────────────────────────────────────────
if [ ! -d node_modules ]; then
  echo "==> Installing npm dependencies"
  npm install
fi

cleanup() {
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [ "$MODE" = "prod" ]; then
  echo "==> Building the front end"
  npm run build
  echo
  echo "    NEXUS + analysis backend on http://127.0.0.1:${PORT}"
  echo
  cd backend
  exec ../venv/bin/python3 run.py
fi

echo "==> Starting the analysis API on http://127.0.0.1:${PORT}"
(cd backend && ../venv/bin/python3 run.py) &
API_PID=$!

# Give uvicorn a moment so its banner does not interleave with Vite's.
sleep 2

echo
echo "    Front end   http://127.0.0.1:5173   (Vite proxies /cna-api to the API)"
echo "    Analysis API http://127.0.0.1:${PORT}/api"
echo "    Legacy console http://127.0.0.1:${PORT}/legacy"
echo
npm run dev
