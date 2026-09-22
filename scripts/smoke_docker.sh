#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:-accessbell:ci}"
NAME="accessbell-smoke-$$"
PORT="${SMOKE_PORT:-18080}"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "starting $IMAGE as $NAME on port $PORT"
docker run -d --name "$NAME" -e PORT=8080 -p "${PORT}:8080" "$IMAGE" >/dev/null

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "http://127.0.0.1:${PORT}/health" | grep -q '"status":"ok"'
curl -fsS -X POST "http://127.0.0.1:${PORT}/api/simulate?fixture=doorbell_med" >/dev/null
sleep 1
curl -fsS "http://127.0.0.1:${PORT}/api/events?limit=1" | grep -q "MED_DELIVERY"
curl -fsS "http://127.0.0.1:${PORT}/.well-known/oauth-protected-resource" | grep -q "scopes_supported"
curl -fsS -X POST "http://127.0.0.1:${PORT}/mcp" -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | grep -q '"tools"'

echo "docker smoke OK"