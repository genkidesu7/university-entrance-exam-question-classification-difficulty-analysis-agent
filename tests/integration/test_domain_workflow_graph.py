# EDU-C2-029 — Integration Tests: DomainWorkflowGraph (inner graph)

import json

import pytest
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from shared.secrets.inmemory_provider import InMemoryProvider

from src.graph.domain_workflow_graph import DomainWorkflowGraph

QUESTIONS_JSON = json.dumps(
    [{"question_id": "Q001", "text": "What is the derivative of x^2?"}]
)


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


@pytest.fixture
def graph():
    g = DomainWorkflowGraph(config={})
    g.compile()
    return g


class TestDomainWorkflowGraph:
    """INT-01: domain_classify -> bloom_level -> difficulty_score end-to-end."""

    def test_full_inner_pipeline_success(self, graph, secrets):
        # Nodes require VERIFIED_EXTERNAL (config/agent.yaml); a direct invoke()
        # with no ctx defaults to ANONYMOUS and the S-1 gate would deny every node.
        ctx = InvocationContext(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL)
        with bound_secrets(secrets):
            result = graph.invoke(QUESTIONS_JSON, ctx=ctx)

        assert result["status"] == "success"
        classified = result["classified_questions"]
        assert classified[0]["domain"]
        assert classified[0]["bloom_level"]
        assert 1 <= classified[0]["difficulty_score"] <= 5
