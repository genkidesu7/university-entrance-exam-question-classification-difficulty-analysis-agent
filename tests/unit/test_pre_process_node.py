# EDU-C2-029 — Unit Tests: PreProcessNode

import json

import pytest
from framework.errors import SecurityViolationError
from framework.schemas.agent_status import AgentStatus

from src.nodes.pre_process_node import PreProcessNode

VALID_PDF_TEXT = (
    "%PDF-1.7\n"
    "1. What is the derivative of x^2?\n"
    "2. Solve for x: 2x + 3 = 7\n"
)


class TestPreProcessNode:
    """DOM-01..04, TC-09, TC-11: PDF ingest and question segmentation."""

    def setup_method(self):
        self.node = PreProcessNode(max_questions_per_batch=100)

    def test_success_path_segments_questions(self):
        """DOM-01: valid PDF-shaped input segments into questions."""
        state = {"user_input": VALID_PDF_TEXT, "node_history": [], "error_log": []}
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["segment_count"] == 2
        questions = json.loads(result["validated_input"])
        assert questions[0]["question_id"] == "Q001"
        assert "derivative" in questions[0]["text"]

    def test_empty_input(self):
        """DOM-02: empty user_input returns error."""
        state = {"user_input": "", "node_history": [], "error_log": []}
        result = self.node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value
        assert len(result["error_log"]) > 0

    def test_extra_security_gate_rejects_oversized_pdf(self):
        """DOM-03/TC-09: S-2 rejects PDFs over the 20MB limit."""
        oversized = "%PDF-1.7\n" + ("x" * (20 * 1024 * 1024 + 1))
        state = {"user_input": oversized}

        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_input(state)

    def test_extra_security_gate_rejects_non_pdf(self):
        """DOM-03/TC-09: S-2 rejects non-PDF content."""
        state = {"user_input": "just plain text, not a pdf"}

        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_input(state)

    def test_extra_security_gate_rejects_executable_magic(self):
        """DOM-03/TC-09: S-2 rejects executable content masquerading as input."""
        state = {"user_input": "MZ\x90\x00\x03"}

        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_input(state)

    def test_extra_security_gate_rejects_pdf_javascript(self):
        """PDF input channel: reject embedded /JavaScript."""
        malicious = "%PDF-1.7\n/JavaScript (app.alert('x'))\n1. What is 2+2?\n"
        state = {"user_input": malicious}

        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_input(state)

    def test_extra_security_gate_rejects_pdf_openaction(self):
        """PDF input channel: reject embedded /OpenAction."""
        malicious = "%PDF-1.7\n/OpenAction 5 0 R\n1. What is 2+2?\n"
        state = {"user_input": malicious}

        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_input(state)

    def test_extra_security_gate_rejects_student_pii_context(self):
        """DOM-03/TC-09: S-2 rejects student-identifying input_context fields."""
        state = {"user_input": VALID_PDF_TEXT, "input_context": {"student_id": "12345"}}

        with pytest.raises(SecurityViolationError):
            self.node._extra_security_gate_input(state)

    def test_extra_security_gate_returns_state(self):
        """S-2 hook must return state, not None (framework crashes on None)."""
        state = {"user_input": VALID_PDF_TEXT}
        returned = self.node._extra_security_gate_input(state)
        assert returned is state

    def test_batch_size_guard(self):
        """DOM-04: batch exceeding max_questions_per_batch errors out."""
        node = PreProcessNode(max_questions_per_batch=1)
        state = {"user_input": VALID_PDF_TEXT, "node_history": [], "error_log": []}
        result = node.execute(state)

        assert result["status"] == AgentStatus.ERROR.value
        assert "max_questions_per_batch" in result["error"]

    def test_emits_trace_event(self, monkeypatch):
        """TC-11: pdf_ingested trace event emitted on success."""
        events = []
        monkeypatch.setattr(
            "src.nodes.pre_process_node.emit_trace_event",
            lambda event_type, payload, state: events.append(event_type),
        )
        state = {"user_input": VALID_PDF_TEXT, "node_history": [], "error_log": []}
        self.node.execute(state)

        assert "pdf_ingested" in events
