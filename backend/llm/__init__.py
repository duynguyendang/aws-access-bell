from .base import TriageLLM
from .stub import StubLLM

MODEL_DEFAULTS = {
    "bedrock": "us.amazon.nova-lite-v1:0",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "google": "gemini-2.0-flash",
    "ollama": "llama3.2",
}


def resolve_model_name(settings) -> str:
    return settings.llm_model or MODEL_DEFAULTS.get(settings.llm_provider, "")


def build_llm(settings):
    if settings.llm_provider == "stub":
        return StubLLM()
    from .langchain_provider import LangChainLLM, build_chat_model

    model = build_chat_model(settings, resolve_model_name(settings))
    return LangChainLLM(model)


__all__ = ["TriageLLM", "StubLLM", "build_llm"]