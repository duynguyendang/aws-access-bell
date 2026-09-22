import hashlib
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[1] / "policy.yaml"


def policy_bytes() -> bytes:
    try:
        return POLICY_PATH.read_bytes()
    except OSError:
        return b""


def policy_sha256() -> str:
    return hashlib.sha256(policy_bytes()).hexdigest()


def policy_version() -> str:
    try:
        text = POLICY_PATH.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    for line in text.splitlines():
        if line.strip().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return "unversioned"


def policy_ref() -> dict:
    digest = policy_sha256()
    return {"version": policy_version(), "sha256": digest, "short": digest[:12]}