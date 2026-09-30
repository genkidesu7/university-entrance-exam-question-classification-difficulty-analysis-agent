# EDU-C2-029 — Unit Tests: DomainClassifyNode

import json

import pytest
from framework.schemas.agent_status import AgentStatus
from framework.secrets.context import bound_secrets
from shared.secrets.inmemory_provider import InMemoryProvider

from src.nodes.domain_classify_node import DomainClassifyNode

QUESTIONS_JSON = json.dumps(
    [{"question_id": "Q001", "text": "What is the derivative of x^2?"}]
)

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


class TestDomainClassifyNode:
    """DOM-05..06, TC-11: MEXT curriculum KB vector classification."""

    def setup_method(self):
        self.node = DomainClassifyNode()

    def test_success_path(self, secrets):
        """DOM-05: valid validated_input produces classified_questions."""
        state = {**BASE_STATE, "validated_input": QUESTIONS_JSON}
        with bound_secrets(secrets):
            result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["classified_questions"][0]["domain"]
        assert result["curriculum_domain_kb_version"]

    def test_falls_back_to_user_input(self, secrets):
        """DOM-06/PB-7: inner-graph fallback — validated_input absent, user_input present."""
        state = {**BASE_STATE, "user_input": QUESTIONS_JSON}
        with bound_secrets(secrets):
            result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value

    def test_missing_input_errors(self, secrets):
        state = {"node_history": [], "error_log": []}
        with bound_secrets(secrets):
            result = self.node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value

    def test_emits_trace_event(self, secrets, monkeypatch):
        """TC-11: domain_classified trace event emitted."""
        events = []
        monkeypatch.setattr(
            "src.nodes.domain_classify_node.emit_trace_event",
            lambda event_type, payload, state: events.append(event_type),
        )
        state = {**BASE_STATE, "validated_input": QUESTIONS_JSON}
        with bound_secrets(secrets):
            self.node.execute(state)

        assert "domain_classified" in events

    def test_succeeds_with_no_secret_bound_in_mock_mode(self):
        """Regression test (implementation_rule.md rule #2): a fresh checkout
        has no env/agents/<ns>/<agent>/.env.<env> tree at all. Mock mode must
        not depend on a secret being resolvable — run with NO bound_secrets()
        context at all (current_secrets() falls back to NullProvider)."""
        state = {**BASE_STATE, "validated_input": QUESTIONS_JSON}
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
