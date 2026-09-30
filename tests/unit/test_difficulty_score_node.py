# EDU-C2-029 — Unit Tests: DifficultyScoreNode

import pytest
from framework.schemas.agent_status import AgentStatus
from framework.secrets.context import bound_secrets
from shared.secrets.inmemory_provider import InMemoryProvider

from src.nodes.difficulty_score_node import DifficultyScoreNode

CLASSIFIED_QUESTIONS = [
    {
        "question_id": "Q001",
        "text": "What is the derivative of x^2?",
        "domain": "Mathematics",
        "subdomain": "Algebra",
        "bloom_level": "application",
        "taxonomy_version": "bloom-revised-mock-v1",
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
    return InMemoryProvider({})


class TestDifficultyScoreNode:
    """DOM-08, TC-11: difficulty scoring 1-5."""

    def setup_method(self):
        self.node = DifficultyScoreNode()

    def test_success_path(self, secrets):
        state = {**BASE_STATE, "classified_questions": CLASSIFIED_QUESTIONS}
        with bound_secrets(secrets):
            result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
        score = result["classified_questions"][0]["difficulty_score"]
        assert 1 <= score <= 5

    def test_missing_classified_questions_errors(self, secrets):
        state = {"node_history": [], "error_log": []}
        with bound_secrets(secrets):
            result = self.node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value

    def test_emits_trace_event(self, secrets, monkeypatch):
        events = []
        monkeypatch.setattr(
            "src.nodes.difficulty_score_node.emit_trace_event",
            lambda event_type, payload, state: events.append(event_type),
        )
        state = {**BASE_STATE, "classified_questions": CLASSIFIED_QUESTIONS}
        with bound_secrets(secrets):
            self.node.execute(state)

        assert "difficulty_scored" in events
