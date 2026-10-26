#!/usr/bin/env bash
# Start the local API and dashboard together. Keep this terminal open; Ctrl+C stops both.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
python_bin="${CURATOR_PYTHON:-python3}"
api_port="${CURATOR_API_PORT:-8000}"
web_port="${CURATOR_WEB_PORT:-5173}"

if ! command -v "$python_bin" >/dev/null 2>&1 && [[ ! -x "$python_bin" ]]; then
  echo "Python not found: $python_bin. Set CURATOR_PYTHON to your project environment's python." >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "Node.js and npm are required in this Linux/WSL installation." >&2
  exit 1
fi
if ! "$python_bin" -c "import pipeline.server" >/dev/null 2>&1; then
  echo "The Python pipeline cannot start in this environment. Install the project dependencies first." >&2
  exit 1
fi
if [[ ! -d dashboard/node_modules ]]; then
  (cd dashboard && npm ci)
fi

api_pid=""
web_pid=""
cleanup() {
  trap - EXIT INT TERM
  [[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true
  [[ -z "$web_pid" ]] || kill "$web_pid" 2>/dev/null || true
  [[ -z "$api_pid" ]] || wait "$api_pid" 2>/dev/null || true
  [[ -z "$web_pid" ]] || wait "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$python_bin" -m pipeline.server --host 127.0.0.1 --port "$api_port" &
api_pid=$!
(cd dashboard && npm run dev -- --host 127.0.0.1 --port "$web_port" --strictPort) &
web_pid=$!

echo "Dashboard: http://localhost:$web_port"
echo "Choose Auto, CPU or GPU before a run. The standard mode is selected by default."
wait -n "$api_pid" "$web_pid"
