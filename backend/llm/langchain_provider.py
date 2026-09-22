import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from ..triage import TriageResult

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "triage.txt"

REQUIRED_KEYS = {
    "openai": ("OPENAI_API_KEY", "openai_api_key"),
    "anthropic": ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    "google": ("GOOGLE_API_KEY", "google_api_key"),
}


def _require_api_key(settings, provider: str):
    env_name, attr = REQUIRED_KEYS[provider]
    if not getattr(settings, attr):
        raise ValueError(f"{env_name} required for llm_provider={provider!r}")


def build_chat_model(settings, model_name: str):
    provider = settings.llm_provider
    if provider == "bedrock":
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(
            model=model_name,
            region_name=settings.aws_region,
            temperature=0.2,
            max_tokens=600,
            timeout=settings.llm_timeout_seconds,
        )
    if provider == "openai":
        _require_api_key(settings, provider)
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            temperature=0.2,
            max_tokens=600,
            timeout=settings.llm_timeout_seconds,
        )
    if provider == "anthropic":
        _require_api_key(settings, provider)
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_name,
            temperature=0.2,
            max_tokens=600,
            timeout=settings.llm_timeout_seconds,
        )
    if provider == "google":
        _require_api_key(settings, provider)
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.2,
            max_output_tokens=600,
            timeout=settings.llm_timeout_seconds,
        )
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model_name,
            base_url=settings.ollama_base_url,
            temperature=0.2,
            num_predict=600,
        )
    raise ValueError(f"unsupported llm_provider: {provider!r}")


class LangChainLLM:
    name = "langchain"

    def __init__(self, model, prompt_path=None):
        self._model = model
        prompt = Path(prompt_path) if prompt_path else DEFAULT_PROMPT_PATH
        self._prompt = prompt.read_text(encoding="utf-8")
        self._chain = model.with_structured_output(TriageResult)

    def triage(self, *, kind, device_id, occurred_at, raw, expected, labels=None, calendar=None):
        payload = json.dumps(
            {
                "kind": kind,
                "device_id": device_id,
                "occurred_at": occurred_at,
                "event": raw,
                "expected_context": expected,
                "prior_user_labels": labels or [],
                "calendar_events": calendar or [],
            },
            ensure_ascii=False,
        )
        result = self._chain.invoke([SystemMessage(content=self._prompt), HumanMessage(content=payload)])
        if isinstance(result, TriageResult):
            return result.model_dump()
        return TriageResult.model_validate(result).model_dump()