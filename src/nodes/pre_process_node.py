"""AgentCore Platform v1.0"""

# Node contract (agents_layer_design.md §1):
#  - Extend FunctionNode; implement execute(state) -> dict
#  - Return ONLY the fields this node changes (never full state)
#  - Return AgentStatus enum constants — never plain strings [A1]
#  - Read input_context via state.get("input_context", {}) — read-only [C1]
#  - Never import from mediator/, api/, or other agents

from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from framework.errors import SecurityViolationError
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.services.events import emitter
from shared.services.events.types import EventType
from shared.utils.audit_logger import emit_trace_event

# S-2: proposal §4 Step 1 — max 20MB, reject non-PDF/executable content.
MAX_PDF_BYTES = 20 * 1024 * 1024
PDF_MAGIC = b"%PDF-"
EXECUTABLE_MAGICS = (b"MZ", b"\x7fELF", b"\xca\xfe\xba\xbe")

# PDF input channel: reject
# embedded /JavaScript, /JS, or /OpenAction objects before text extraction —
# they can execute on open or survive into extracted text and reach an LLM prompt.
PDF_ACTIVE_CONTENT_MARKERS = (b"/JavaScript", b"/JS", b"/OpenAction")

# S-2: block obvious student-identifying fields from ever reaching validated_input
# (proposal §4 note — classification operates on question text only).
STUDENT_PII_KEYS = {"student_id", "student_name", "student_email"}


class PreProcessNode(FunctionNode):
    """Ingest exam PDF and segment it into individual questions."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, max_questions_per_batch: int = 100) -> None:
        super().__init__()
        self._max_questions_per_batch = max_questions_per_batch

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-2: reject non-PDF/executable/oversized input; strip student PII fields."""
        raw = state.get("user_input", "")
        raw_bytes = raw.encode("utf-8", errors="ignore") if isinstance(raw, str) else raw

        if not isinstance(raw_bytes, (bytes, bytearray)):
            raise SecurityViolationError("PreProcessNode: user_input must be str or bytes")
        if len(raw_bytes) > MAX_PDF_BYTES:
            raise SecurityViolationError("PreProcessNode: PDF exceeds 20MB limit")
        if any(raw_bytes.startswith(magic) for magic in EXECUTABLE_MAGICS):
            raise SecurityViolationError("PreProcessNode: executable content rejected")
        if raw_bytes and not raw_bytes.lstrip().startswith(PDF_MAGIC):
            raise SecurityViolationError("PreProcessNode: non-PDF content rejected")
        if any(marker in raw_bytes for marker in PDF_ACTIVE_CONTENT_MARKERS):
            raise SecurityViolationError(
                "PreProcessNode: PDF contains active content "
                "(/JavaScript, /JS, or /OpenAction) — rejected before text extraction"
            )

        input_context = state.get("input_context", {})
        if isinstance(input_context, dict) and STUDENT_PII_KEYS & input_context.keys():
            raise SecurityViolationError("PreProcessNode: student-identifying fields are not permitted")
        return state

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Ingesting exam PDF and segmenting questions...",
            metadata={"stage": "pre_process"},
        )
        user_input = state.get("user_input", "")

        if not user_input or not user_input.strip():
            return {
                "status": AgentStatus.ERROR.value,
                "error": "PreProcessNode: user_input is empty or missing",
                "error_log": ["PreProcessNode: user_input is empty or missing"],
            }

        try:
            questions = self._segment_questions(user_input)
        except ValueError as exc:
            return {
                "status": AgentStatus.RETRY.value,
                "error": str(exc),
                "error_log": [f"[RETRY] PreProcessNode: {exc}"],
            }

        if not questions:
            return {
                "status": AgentStatus.ERROR.value,
                "error": "PreProcessNode: no questions could be segmented from input",
                "error_log": ["PreProcessNode: no questions could be segmented from input"],
            }

        if len(questions) > self._max_questions_per_batch:
            return {
                "status": AgentStatus.ERROR.value,
                "error": (
                    f"PreProcessNode: batch of {len(questions)} questions exceeds "
                    f"max_questions_per_batch={self._max_questions_per_batch}"
                ),
                "error_log": [
                    f"PreProcessNode: batch of {len(questions)} exceeds "
                    f"max_questions_per_batch={self._max_questions_per_batch}"
                ],
            }

        emit_trace_event(
            "pdf_ingested",
            {"segment_count": len(questions)},
            state,
        )

        return {
            "validated_input": json.dumps(questions, ensure_ascii=False),
            "segment_count": len(questions),
            "status": AgentStatus.SUCCESS.value,
        }

    def _segment_questions(self, raw_text: str) -> list[dict[str, str]]:
        """Split ingested exam text into individual questions with sequential IDs.

        v1 is text-only (per proposal §4 scope note — no diagram/figure extraction).
        Splits on a leading question-number marker like "1." / "問1" at line start.
        Any preamble before the first marker (e.g. a PDF header line) is discarded.
        """
        pattern = re.compile(r"(?m)^(?:問\s*\d+|\d+\s*[\.\)])\s*")
        match = pattern.search(raw_text)
        if not match:
            return []
        body = raw_text[match.start() :]
        parts = [p.strip() for p in pattern.split(body) if p.strip()]
        return [{"question_id": f"Q{i + 1:03d}", "text": part} for i, part in enumerate(parts)]
