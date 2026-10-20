#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${HOME}/.local/bin:${PATH}"

if [ -f "${REPO_ROOT}/aws.env" ] && [ -z "${SKIP_AWS_ENV:-}" ] && [ -z "${AWS_PROFILE:-}" ]; then
  echo "Loading AWS credentials from aws.env..."
  set -a
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/aws.env"
  set +a
  if [ -z "${AWS_SESSION_TOKEN:-}" ]; then
    unset AWS_SESSION_TOKEN
  fi
fi

REGION="${1:-${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}}"
STACK_NAME="${STACK_NAME:-AccessBellStack}"
LLM_PROVIDER="${LLM_PROVIDER:-bedrock}"
CDK_CONTEXT_ARGS=()

if [ "${LLM_PROVIDER}" = "bedrock" ]; then
  echo "=== Bedrock preflight (provider=bedrock) ==="
  PREFLIGHT_PY="python3"
  if [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
    PREFLIGHT_PY="${REPO_ROOT}/.venv/bin/python"
  fi
  if ! "${PREFLIGHT_PY}" "${REPO_ROOT}/scripts/check_bedrock_access.py" --provider bedrock --region "${REGION}"; then
    if [ "${ALLOW_BEDROCK_BLOCKED:-0}" = "1" ]; then
      echo "WARNING: continuing anyway (ALLOW_BEDROCK_BLOCKED=1); events will be stored as enrichment_failed."
    else
      echo "Error: this account cannot use Bedrock foundation models." >&2
      echo "       Re-run with ALLOW_BEDROCK_BLOCKED=1 to deploy anyway, or deploy with" >&2
      echo "       LLM_PROVIDER=stub for the deterministic triage provider." >&2
      exit 1
    fi
  fi
fi

if [ -n "${LLM_API_KEY:-}" ] && [ -z "${LLM_API_KEY_SECRET_NAME:-}" ]; then
  LLM_API_KEY_SECRET_NAME="AccessBellLlmApiKey"
  export LLM_API_KEY_SECRET_NAME
  aws secretsmanager describe-secret --secret-id "${LLM_API_KEY_SECRET_NAME}" --region "${REGION}" >/dev/null 2>&1 \
    || aws secretsmanager create-secret --name "${LLM_API_KEY_SECRET_NAME}" --secret-string "${LLM_API_KEY}" --region "${REGION}" >/dev/null
  aws secretsmanager put-secret-value --secret-id "${LLM_API_KEY_SECRET_NAME}" --secret-string "${LLM_API_KEY}" --region "${REGION}" >/dev/null
  echo "LLM API key stored in Secrets Manager: ${LLM_API_KEY_SECRET_NAME}"
fi

if [ -n "${CERTIFICATE_ARN:-}" ]; then
  CDK_CONTEXT_ARGS+=("-c" "certificate_arn=${CERTIFICATE_ARN}")
fi
if [ -n "${ALEXA_CALLBACK_URLS:-}" ]; then
  CDK_CONTEXT_ARGS+=("-c" "alexa_callback_urls=${ALEXA_CALLBACK_URLS}")
fi

echo "=== AccessBell AWS CDK Deployment ==="
echo "Target Region: ${REGION}"
if [ -n "${CERTIFICATE_ARN:-}" ]; then
  echo "HTTPS: ACM certificate ${CERTIFICATE_ARN}"
else
  echo "HTTPS: disabled (set CERTIFICATE_ARN for a Ring-compatible HTTPS callback)"
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "Error: AWS CLI ('aws') is not installed." >&2
  exit 1
fi

if ! command -v cdk >/dev/null 2>&1; then
  echo "Error: AWS CDK CLI ('cdk') is not installed. Install via: npm install -g aws-cdk" >&2
  exit 1
fi

echo "Verifying AWS credentials..."
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
echo "AWS Account: ${ACCOUNT_ID}"

export AWS_ACCOUNT_ID="${ACCOUNT_ID}"
export CDK_DEFAULT_ACCOUNT="${ACCOUNT_ID}"
export CDK_DEFAULT_REGION="${REGION}"
export AWS_REGION="${REGION}"
export AWS_DEFAULT_REGION="${REGION}"

if [ -S /var/run/docker.sock ] && [ ! -w /var/run/docker.sock ]; then
  wsl.exe -u root chmod 666 /var/run/docker.sock 2>/dev/null || true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INFRA_DIR="${REPO_ROOT}/infra"

cd "${INFRA_DIR}"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

echo "Bootstrapping CDK in region ${REGION} if needed..."
PROFILE_ARGS=()
if [ -n "${AWS_PROFILE:-}" ]; then
  PROFILE_ARGS+=("--profile" "${AWS_PROFILE}")
  echo "Using AWS profile: ${AWS_PROFILE}"
fi

cdk bootstrap "${PROFILE_ARGS[@]}" "aws://${ACCOUNT_ID}/${REGION}"

echo "Deploying ${STACK_NAME}..."
cdk deploy --require-approval never "${PROFILE_ARGS[@]}" "${CDK_CONTEXT_ARGS[@]}"

echo
echo "=== Deployment Complete ==="
echo "Inspect outputs above for ServiceUrl (ALB), UserPoolId, and CognitoClientId."
