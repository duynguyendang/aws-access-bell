"""Check that the configured LLM provider can actually answer before a deploy.

The Bedrock path is configured in the CDK stack, but a stack can deploy cleanly into an
account that is not allowed to use foundation models: InvokeModel then fails with
"Access to Bedrock models is not allowed for this account" and every event is stored as
enrichment_failed. This probe turns that into a clear, fast answer, and the Bedrock
per-model availability API says exactly which gate is closed (agreement, entitlement,
region, or authorization).

Usage: python scripts/check_bedrock_access.py [--provider bedrock] [--model MODEL] [--region R]

Exit codes: 0 reachable, 1 not reachable.
"""

import argparse
import json
import os
import sys

DEFAULT_MODEL = "us.amazon.nova-2-lite-v1:0"
PROBE_BODY = {
    "schemaVersion": "messages-v1",
    "messages": [{"role": "user", "content": [{"text": "ping"}]}],
    "inferenceConfig": {"maxTokens": 8},
}


def _client(service: str, region: str):
    import boto3

    return boto3.client(service, region_name=region)


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


def _base_model_id(model: str) -> str:
    """The availability API takes base model ids, not inference profile ids."""
    for prefix in ("us.", "global.", "eu.", "ap.", "apac.", "us-gov."):
        if model.startswith(prefix):
            return model[len(prefix):]
    return model


def availability(region: str, model: str) -> dict:
    """Per-model gates: EULA agreement, account entitlement, region, authorization."""
    client = _client("bedrock", region)
    for candidate in (model, _base_model_id(model)):
        try:
            data = client.get_foundation_model_availability(modelId=candidate)
        except Exception:
            continue
        return {
            "model": data.get("modelId", candidate),
            "agreement": (data.get("agreementAvailability") or {}).get("status"),
            "entitlement": data.get("entitlementAvailability"),
            "region": data.get("regionAvailability"),
            "authorization": data.get("authorizationStatus"),
        }
    return {}


def _format_availability(info: dict) -> str:
    if not info:
        return "  (availability API returned nothing for this model id)"
    lines = [
        f"  model           : {info.get('model')}",
        f"  agreement (EULA): {info.get('agreement')}",
        f"  entitlement     : {info.get('entitlement')}",
        f"  region          : {info.get('region')}",
        f"  authorization   : {info.get('authorization')}   <-- what InvokeModel checks",
    ]
    return "\n".join(lines)


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
    try:
        info = availability(args.region, args.model)
    except Exception as exc:
        info = {}
        print(f"  (availability API failed: {str(exc)[:160]})")
    print(_format_availability(info))
    if info.get("authorization") == "NOT_AUTHORIZED":
        print(
            "The model is offered in this region and the account has the entitlement, but the "
            "account is NOT_AUTHORIZED for the model. That gate belongs to the account, not to the "
            "IAM principal: root and admin users get the same answer, and "
            "PutUseCaseForModelAccess refuses self-service with 'Your account is not authorized to "
            "perform this action. Please create a support case'."
        )
    print(
        "Either open that support case, deploy with an account that has model access, or deploy "
        "with LLM_PROVIDER=stub for the deterministic triage provider."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
