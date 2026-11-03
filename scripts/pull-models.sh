#!/usr/bin/env bash
# Pull the bake-off models, or only the ones named as arguments.
# Safe to stop and re-run: Ollama keeps partial files and continues where it left off.
#   bash scripts/pull-models.sh                # every model in evals/bakeoff_models.txt
#   bash scripts/pull-models.sh qwen3:8b       # only these
set -uo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

# --max-time matters: with WSL mirrored networking, a localhost port with no listener
# can hang instead of refusing the connection.
up() { curl -s --max-time 3 localhost:11434/api/version >/dev/null; }
if ! up; then
  nohup ollama serve > "$HOME/.ollama-serve.log" 2>&1 &
  for _ in $(seq 30); do up && break; sleep 1; done
fi

if [ $# -gt 0 ]; then
  models=("$@")
else
  mapfile -t models < <(grep -v '^#' evals/bakeoff_models.txt | sed '/^[[:space:]]*$/d')
fi

failed=()
for m in "${models[@]}"; do
  if ollama list | awk 'NR > 1 {print $1}' | grep -qx "$m"; then
    echo "$m: already downloaded"
    continue
  fi
  for attempt in 1 2 3 4 5 6; do
    echo "$m: attempt $attempt ($(date +%H:%M))"
    if ollama pull "$m"; then
      echo "$m: done ($(date +%H:%M))"
      break
    fi
    if [ "$attempt" -eq 6 ]; then
      failed+=("$m")
      break
    fi
    sleep $((attempt * 60))  # connection drops are often brief; wait longer each time
  done
done

ollama list
if [ ${#failed[@]} -gt 0 ]; then
  echo "Still missing: ${failed[*]}. Re-run this script to resume."
  exit 1
fi
