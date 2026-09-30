# EDU-C2-029 — Integration Tests: outer Graph (full pipeline)

import pytest
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from shared.secrets.inmemory_provider import InMemoryProvider

from src.graph.graph import Graph

VALID_PDF_TEXT = (
    "%PDF-1.7\n"
    "1. What is the derivative of x^2?\n"
    "2. Solve for x: 2x + 3 = 7\n"
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
def agent():
    a = Graph(config={"max_questions_per_batch": 100})
    a.compile()
    return a


class TestGraph:
    """INT-02..04: outer graph compilation and full pipeline behavior."""

    def test_compiles_with_all_required_slots(self, agent):
        """INT-02: pre_process/main/post_process all registered, compile() succeeds."""
        assert agent._nodes.get("pre_process") is not None
        assert agent._nodes.get("main") is not None
        assert agent._nodes.get("post_process") is not None

    def test_full_pipeline_success(self, agent, secrets):
        """INT-03: PDF-shaped input produces a classified distribution report."""
        # Nodes require VERIFIED_EXTERNAL (config/agent.yaml); a direct invoke()
        # with no ctx defaults to ANONYMOUS and the S-1 gate would deny every node.
        ctx = InvocationContext(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL)
        with bound_secrets(secrets):
            result = agent.invoke(VALID_PDF_TEXT, ctx=ctx)

        assert result["status"] == "success"
        assert result["output"] is not None

    def test_full_pipeline_error_on_empty_input(self, agent, secrets):
        """INT-04: empty input fails cleanly, no unhandled exception."""
        ctx = InvocationContext(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL)
        with bound_secrets(secrets):
            result = agent.invoke("", ctx=ctx)

        assert result["status"] in ("error", "cancelled")
