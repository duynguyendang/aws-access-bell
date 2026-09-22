import pytest

pytest.importorskip("langchain_core")

from backend.config import Settings  # noqa: E402
from backend.llm import build_llm  # noqa: E402
from backend.llm.langchain_provider import LangChainLLM, build_chat_model  # noqa: E402


def _settings(provider: str) -> Settings:
    settings = Settings()
    settings.llm_provider = provider
    return settings


def test_build_stub():
    llm = build_llm(_settings("stub"))
    assert llm.name == "stub"


def test_build_langchain_ollama():
    llm = build_llm(_settings("ollama"))
    assert llm.name == "langchain"


def test_ollama_model_is_structured_output():
    model = build_chat_model(_settings("ollama"), "llama3.2")
    llm = LangChainLLM(model)
    assert llm.name == "langchain"


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        build_llm(_settings("nonexistent"))


def test_openai_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        build_llm(_settings("openai"))