"""Check that the configured LLM provider can actually answer before a deploy.

The Bedrock path is configured in the CDK stack, but a stack can deploy cleanly into an
account that is not allowed to use foundation models: InvokeModel then fails with
"Access to Bedrock models is not allowed for this account" and every event is stored as
enrichment_failed. This probe turns that into a clear, fast answer.

Usage: python scripts/check_bedrock_access.py [--provider bedrock] [--model MODEL] [--region R]

Exit codes: 0 reachable, 1 not reachable.
"""

import argparse
import json
import os
import sys

DEFAULT_MODEL = "us.amazon.nova-lite-v1:0"
PROBE_BODY = {
    "schemaVersion": "messages-v1",
    "messages": [{"role": "user", "content": [{"text": "ping"}]}],
    "inferenceConfig": {"maxTokens": 8},
}


def _invoke(region: str, model: str) -> tuple[bool, str]:
    try:
        import boto3
    except ImportError:
        return False, "boto3 is not installed (pip install -r requirements-bedrock.txt)"
    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        client.invoke_model(modelId=model, body=json.dumps(PROBE_BODY))
    except Exception as exc:
        detail = f"{type(exc).__name__}: {str(exc)[:400]}"
        if "MissingDependencyException" in detail or "botocore[crt]" in detail:
            detail += ' (the AWS login credential provider needs: pip install "botocore[crt]")'
        return False, detail
    return True, "invoke-model OK"


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Bedrock model access for this account.")
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "bedrock"))
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")))
    args = parser.parse_args()

    if args.provider != "bedrock":
        print(f"provider {args.provider!r} is not bedrock; nothing to probe")
        return 0

    ok, detail = _invoke(args.region, args.model)
    if ok:
        print(f"bedrock access OK: {args.model} in {args.region}")
        return 0
    print(f"bedrock access FAILED for {args.model} in {args.region}: {detail}")
    print(
        "This is an account-level restriction, not an application bug: the account is not allowed "
        "to use foundation models. It affects every principal of the account, including root, and "
        "the Bedrock model-access APIs answer 'Your account is not authorized to perform this "
        "action. Please create a support case'. Either open that support case, deploy with an "
        "account that has model access, or deploy with LLM_PROVIDER=stub for the deterministic "
        "triage provider."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
