#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PATH="${HOME}/.local/bin:${PATH}"

if [ -f "${REPO_ROOT}/aws.env" ]; then
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
CDK_CONTEXT_ARGS=()

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
cdk bootstrap "aws://${ACCOUNT_ID}/${REGION}"

echo "Deploying ${STACK_NAME}..."
cdk deploy --require-approval never "${CDK_CONTEXT_ARGS[@]}"

echo
echo "=== Deployment Complete ==="
echo "Inspect outputs above for ServiceUrl (ALB), UserPoolId, and CognitoClientId."
