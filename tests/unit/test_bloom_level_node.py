# EDU-C2-029 — Unit Tests: BloomLevelNode

import pytest
from framework.schemas.agent_status import AgentStatus
from framework.secrets.context import bound_secrets
from framework.secrets.base import MissingSecret
from shared.secrets.inmemory_provider import InMemoryProvider

from src.nodes.bloom_level_node import BloomLevelNode
from src.services import service as service_module

CLASSIFIED_QUESTIONS = [
    {
        "question_id": "Q001",
        "text": "What is the derivative of x^2?",
        "domain": "Mathematics",
        "subdomain": "Algebra",
        "kb_version": "mext-2022-revision-mock-v1",
    }
]

# InvocationContext.from_state() requires these fields.
BASE_STATE = {
    "correlation_id": "test-corr",
    "session_id": "test-session",
    "thread_id": "test-thread",
    "trace_id": "",
    "node_history": [],
    "error_log": [],
}


@pytest.fixture(autouse=True)
def use_mock_mode(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")


@pytest.fixture
def secrets():
    return InMemoryProvider(
        {
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_ENDPOINT": "https://example.invalid",
            "AZURE_OPENAI_DEPLOYMENT": "test-deployment",
        }
    )


class TestBloomLevelNode:
    """DOM-07, TC-11: Bloom's taxonomy cognitive-level classification."""

    def setup_method(self):
        self.node = BloomLevelNode()

    def test_success_path(self, secrets):
        state = {**BASE_STATE, "classified_questions": CLASSIFIED_QUESTIONS}
        with bound_secrets(secrets):
            result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["classified_questions"][0]["bloom_level"]
        assert result["bloom_taxonomy_version"]

    def test_missing_classified_questions_errors(self, secrets):
        state = {"node_history": [], "error_log": []}
        with bound_secrets(secrets):
            result = self.node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value

    def test_emits_trace_event(self, secrets, monkeypatch):
        events = []
        monkeypatch.setattr(
            "src.nodes.bloom_level_node.emit_trace_event",
            lambda event_type, payload, state: events.append(event_type),
        )
        state = {**BASE_STATE, "classified_questions": CLASSIFIED_QUESTIONS}
        with bound_secrets(secrets):
            self.node.execute(state)

        assert "bloom_level_assigned" in events

    def test_emits_progress_update_on_entry(self, secrets, monkeypatch):
        from shared.services.events.types import EventType

        events = []

        class Recorder:
            def emit_event(self, **kwargs):
                events.append(kwargs)

        monkeypatch.setattr("src.nodes.bloom_level_node.emitter", lambda: Recorder())
        state = {**BASE_STATE, "classified_questions": CLASSIFIED_QUESTIONS}
        with bound_secrets(secrets):
            self.node.execute(state)

        assert events[0]["event_type"] is EventType.PROGRESS_UPDATE
        assert events[0]["metadata"]["stage"] == "bloom_level"

    def test_real_mode_uses_llm_service(self, secrets, monkeypatch):
        """Non-mock path reaches call_llm with the invocation's SecretProvider."""
        monkeypatch.setenv("USE_MOCK", "false")
        monkeypatch.delenv("STG_MOCK_MODE", raising=False)
        monkeypatch.setattr(service_module, "call_llm", lambda prompt, *_: "synthesis")
        state = {**BASE_STATE, "classified_questions": CLASSIFIED_QUESTIONS}
        with bound_secrets(secrets):
            result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["classified_questions"][0]["bloom_level"] == "synthesis"

    def test_real_mode_without_secrets_fails_fast(self, monkeypatch):
        """PB-3: with every mock alias cleared, the real path must raise MissingSecret,
        not degrade to a placeholder credential."""
        monkeypatch.delenv("USE_MOCK", raising=False)
        monkeypatch.delenv("STG_MOCK_MODE", raising=False)
        state = {**BASE_STATE, "classified_questions": CLASSIFIED_QUESTIONS}
        with bound_secrets(InMemoryProvider({})), pytest.raises(MissingSecret):
            self.node.execute(state)
