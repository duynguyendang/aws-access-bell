#!/usr/bin/env bash
set -euo pipefail

PROJECT="${1:?usage: deploy_cloudrun.sh <gcp-project-id> [region]}"
REGION="${2:-asia-southeast1}"
SERVICE="${SERVICE:-accessbell-demo}"
MCP_TOKEN="${MCP_TOKEN:-$(openssl rand -hex 16)}"
API_TOKEN="${API_TOKEN:-$(openssl rand -hex 16)}"
DB_URL="${DB_URL:-}"

gcloud run deploy "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --source . \
  --allow-unauthenticated \
  --min-instances 0 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --port 8080 \
  --set-env-vars "MOCK_MODE=true,LLM_PROVIDER=stub,RATE_LIMIT_PER_MINUTE=60,EVENT_TTL_DAYS=30,API_AUTH_DISABLED=false,API_TOKEN=${API_TOKEN},MCP_HTTP_TOKEN=${MCP_TOKEN}${DB_URL:+,DB_URL=${DB_URL}}"

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format='value(status.url)')"

echo
echo "API_TOKEN = ${API_TOKEN}   (REST/SSE; UI bootstrap: ${URL}/?token=${API_TOKEN})"
echo "MCP_HTTP_TOKEN = ${MCP_TOKEN}   (MCP clients; prefer OAuth for Alexa+)"
echo "UI:     ${URL}/?token=${API_TOKEN}"
echo "health: ${URL}/health"
echo "MCP:    curl -s ${URL}/mcp -H 'Content-Type: application/json' -H \"Authorization: Bearer ${MCP_TOKEN}\" -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}'"
echo
echo "Note: scale-to-zero is safe (escalation re-arms from the DB); set DB_URL=postgresql://... for durable,"
echo "multi-instance state. SSE is per-instance: pin one instance if multiple Fire TVs must see every alert."