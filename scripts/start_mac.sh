#!/usr/bin/env bash
# Start the FinAlly container. Pass --build to force an image rebuild.
set -euo pipefail

IMAGE=finally
CONTAINER=finally
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL=http://localhost:8000

if [[ "${1:-}" == "--build" ]] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build -t "$IMAGE" "$ROOT"
fi

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

ENV_ARGS=()
if [[ -f "$ROOT/.env" ]]; then
  ENV_ARGS=(--env-file "$ROOT/.env")
fi

docker run -d --name "$CONTAINER" \
  -v finally-data:/app/db \
  -p 8000:8000 \
  ${ENV_ARGS[@]+"${ENV_ARGS[@]}"} \
  "$IMAGE" >/dev/null

echo "FinAlly is running at $URL"

if command -v open >/dev/null 2>&1; then
  open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
fi
