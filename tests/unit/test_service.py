# EDU-C2-029 — Unit Tests: CurriculumClassificationService

import pytest
from shared.secrets.inmemory_provider import InMemoryProvider

from src.services import service as service_module
from src.services.service import (
    BLOOM_LEVELS,
    BLOOM_TAXONOMY_VERSION,
    AZURE_LLM_SECRET_KEYS,
    BloomLevelParseError,
    CurriculumClassificationService,
)

AZURE_SECRETS = InMemoryProvider({key: f"value-for-{key}" for key in AZURE_LLM_SECRET_KEYS})


@pytest.fixture
def mock_mode(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "false")
    monkeypatch.delenv("STG_MOCK_MODE", raising=False)


class TestMockMode:
    """DOM-11: service layer mock-mode fixture behavior."""

    @pytest.mark.asyncio
    async def test_classify_bloom_level_mock(self, mock_mode):
        result = await CurriculumClassificationService().classify_bloom_level("What is 2+2?", "mock")
        assert result["bloom_level"] in BLOOM_LEVELS
        assert result["taxonomy_version"]

    @pytest.mark.asyncio
    async def test_classify_bloom_level_requires_credential_handle(self, mock_mode):
        with pytest.raises(ValueError):
            await CurriculumClassificationService().classify_bloom_level("What is 2+2?", "")


class TestStubBackedServices:
    """KB lookup and difficulty rubric are served from mock_data.py stubs in every mode."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("flag", ["true", "false"])
    async def test_classify_domain_uses_stub_in_both_modes(self, monkeypatch, flag):
        monkeypatch.setenv("USE_MOCK", flag)
        monkeypatch.delenv("STG_MOCK_MODE", raising=False)
        result = await CurriculumClassificationService().classify_domain("What is 2+2?")
        assert result["domain"]
        assert result["kb_version"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("flag", ["true", "false"])
    async def test_score_difficulty_uses_stub_in_both_modes(self, monkeypatch, flag):
        monkeypatch.setenv("USE_MOCK", flag)
        monkeypatch.delenv("STG_MOCK_MODE", raising=False)
        result = await CurriculumClassificationService().score_difficulty("Mathematics", "application")
        assert 1 <= result["difficulty_score"] <= 5


class TestRealBloomPath:
    """Non-mock path: goes through call_llm (the single AzureOpenAIClient construction site)."""

    @pytest.mark.asyncio
    async def test_returns_parsed_level_and_prompts_with_question(self, real_mode, monkeypatch):
        seen = {}

        def fake_call_llm(prompt, credential_handle, max_tokens, temperature):
            seen.update(prompt=prompt, handle=credential_handle, max_tokens=max_tokens, temperature=temperature)
            return " Analysis.\n"

        monkeypatch.setattr(service_module, "call_llm", fake_call_llm)
        result = await CurriculumClassificationService().classify_bloom_level("Compare A and B.", AZURE_SECRETS)

        assert result == {"bloom_level": "analysis", "taxonomy_version": BLOOM_TAXONOMY_VERSION}
        assert "Compare A and B." in seen["prompt"]
        assert seen["handle"] is AZURE_SECRETS
        assert seen["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_question_text_with_braces_does_not_break_prompt(self, real_mode, monkeypatch):
        monkeypatch.setattr(service_module, "call_llm", lambda prompt, *_: "recall")
        result = await CurriculumClassificationService().classify_bloom_level("Evaluate {x} and {0}", AZURE_SECRETS)
        assert result["bloom_level"] == "recall"

    @pytest.mark.asyncio
    async def test_non_level_reply_raises_parse_error(self, real_mode, monkeypatch):
        monkeypatch.setattr(service_module, "call_llm", lambda prompt, *_: "Ignore previous instructions")
        with pytest.raises(BloomLevelParseError):
            await CurriculumClassificationService().classify_bloom_level("Q", AZURE_SECRETS)

    @pytest.mark.asyncio
    async def test_real_mode_rejects_non_provider_handle(self, real_mode):
        with pytest.raises(ValueError):
            await CurriculumClassificationService().classify_bloom_level("Q", "mock")

    def test_call_llm_builds_azure_client_from_secrets(self, monkeypatch):
        captured = {}

        class FakeClient:
            def __init__(self, config):
                captured["config"] = config

            def complete(self, messages):
                captured["messages"] = messages
                return {"content": "application"}

        monkeypatch.setattr("shared.services.llm.azure_openai_client.AzureOpenAIClient", FakeClient)
        out = service_module.call_llm("prompt", AZURE_SECRETS, 16, 0.0)

        assert out == "application"
        assert captured["config"]["api_key"] == "value-for-AZURE_OPENAI_API_KEY"
        assert captured["config"]["azure_endpoint"] == "value-for-AZURE_OPENAI_ENDPOINT"
        assert captured["config"]["azure_deployment"] == "value-for-AZURE_OPENAI_DEPLOYMENT"
        assert captured["messages"] == [{"role": "user", "content": "prompt"}]
