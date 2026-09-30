# EDU-C2-029 — Unit Tests: PostProcessNode

import pytest
from framework.errors import SecurityViolationError
from framework.schemas.agent_status import AgentStatus

from src.nodes.post_process_node import PostProcessNode

SCORED_QUESTIONS = [
    {
        "question_id": "Q001",
        "text": "What is the derivative of x^2?",
        "domain": "Mathematics",
        "subdomain": "Algebra",
        "bloom_level": "application",
        "difficulty_score": 3,
    }
]


class TestPostProcessNode:
    """DOM-09..10, TC-10, TC-11: report assembly and S-3 residual PII scan."""

    def setup_method(self):
        self.node = PostProcessNode()

    def test_success_path(self):
        """DOM-09: valid classified_questions produces a full result package."""
        state = {"classified_questions": SCORED_QUESTIONS, "node_history": [], "error_log": []}
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
        payload = result["result"]
        assert payload["classification_json"] == SCORED_QUESTIONS
        assert "Mathematics" in payload["distribution_report_md"]
        assert "Algebra" in payload["gap_analysis_md"]

    def test_missing_classified_questions_errors(self):
        state = {"node_history": [], "error_log": []}
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value

    def test_extra_security_gate_blocks_residual_pii(self):
        """DOM-10/TC-10: S-3 blocks output containing student-identifying text."""
        result = {
            "result": {
                "distribution_report_md": "student_id: 12345 scored highest",
                "gap_analysis_md": "",
            }
        }
        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_output(result)

    def test_extra_security_gate_returns_result_when_clean(self):
        """S-3 hook must return result, not None."""
        result = {
            "result": {
                "distribution_report_md": "# Report",
                "gap_analysis_md": "# Gaps",
            }
        }
        returned = self.node._extra_security_gate_output(result)
        assert returned is result

    def test_emits_trace_event(self, monkeypatch):
        """TC-11: report_assembled trace event emitted."""
        events = []
        monkeypatch.setattr(
            "src.nodes.post_process_node.emit_trace_event",
            lambda event_type, payload, state: events.append(event_type),
        )
        state = {"classified_questions": SCORED_QUESTIONS, "node_history": [], "error_log": []}
        self.node.execute(state)

        assert "report_assembled" in events
