"""AgentCore Platform v1.0"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from framework.errors import SecurityViolationError
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.services.events import emitter
from shared.services.events.types import EventType
from shared.utils.audit_logger import emit_trace_event

# S-3: residual student-PII patterns that must never appear in the assembled report.
_STUDENT_PII_PATTERN = re.compile(r"student[_\s-]?(id|name|email)", re.IGNORECASE)


class PostProcessNode(FunctionNode):
    """Assemble the difficulty-distribution report and curriculum gap analysis."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Assembling difficulty report and gap analysis...",
            metadata={"stage": "post_process"},
        )
        classified_questions = state.get("classified_questions") or []
        if not classified_questions:
            return {
                "status": AgentStatus.ERROR.value,
                "error": "PostProcessNode: classified_questions missing or empty",
                "error_log": ["PostProcessNode: classified_questions missing or empty"],
            }

        distribution_report_md = self._build_distribution_report(classified_questions)
        gap_analysis_md = self._build_gap_analysis(classified_questions)

        emit_trace_event(
            "report_assembled",
            {"question_count": len(classified_questions)},
            state,
        )

        return {
            "result": {
                "classification_json": classified_questions,
                "distribution_report_md": distribution_report_md,
                "gap_analysis_md": gap_analysis_md,
            },
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        """S-3: re-scan the assembled report for residual student-identifying content."""
        payload = result.get("result", {})
        for field in ("distribution_report_md", "gap_analysis_md"):
            text = payload.get(field, "") if isinstance(payload, dict) else ""
            if isinstance(text, str) and _STUDENT_PII_PATTERN.search(text):
                raise SecurityViolationError(f"PostProcessNode: S-3 blocked — student-identifying content in {field}")
        return result

    def _build_distribution_report(self, questions: list[dict[str, Any]]) -> str:
        by_domain: dict[str, int] = {}
        by_difficulty: dict[int, int] = {}
        for q in questions:
            domain = q.get("domain", "Unknown")
            difficulty = q.get("difficulty_score", 0)
            by_domain[domain] = by_domain.get(domain, 0) + 1
            by_difficulty[difficulty] = by_difficulty.get(difficulty, 0) + 1

        lines = ["# Difficulty Distribution Report", "", f"Total questions: {len(questions)}", ""]
        lines.append("## By Domain")
        for domain, count in sorted(by_domain.items()):
            lines.append(f"- {domain}: {count}")
        lines.append("")
        lines.append("## By Difficulty Score")
        for score in sorted(by_difficulty):
            lines.append(f"- Score {score}: {by_difficulty[score]}")
        return "\n".join(lines)

    def _build_gap_analysis(self, questions: list[dict[str, Any]]) -> str:
        subdomains = {q.get("subdomain", "Unknown") for q in questions}
        lines = ["# Curriculum Gap Analysis", "", "## Subdomains Covered"]
        for subdomain in sorted(subdomains):
            lines.append(f"- {subdomain}")
        return "\n".join(lines)
