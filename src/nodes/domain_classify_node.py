"""AgentCore Platform v1.0"""

# Inner-graph node (src/graph/domain_workflow_graph.py). Runs inside the Cat 2
# main slot's subgraph — see docs/02_design.md "Composition Pattern".

from __future__ import annotations

import asyncio
import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.services.events import emitter
from shared.services.events.types import EventType
from shared.utils.audit_logger import emit_trace_event

from src.services.service import CurriculumClassificationService


class DomainClassifyNode(FunctionNode):
    """Vector-search the MEXT 学習指導要領 curriculum KB per question."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Classifying questions by curriculum domain...",
            metadata={"stage": "domain_classify"},
        )
        # Inner-graph fallback rule (docs/02_design.md) — initial_state only
        # carries user_input, not the outer pre_process's validated_input.
        validated_input = state.get("validated_input", state.get("user_input", ""))
        if not validated_input:
            return {
                "status": AgentStatus.ERROR.value,
                "error": "DomainClassifyNode: validated_input/user_input missing",
                "error_log": ["DomainClassifyNode: validated_input/user_input missing"],
            }

        try:
            questions = json.loads(validated_input)
        except (TypeError, ValueError) as exc:
            return {
                "status": AgentStatus.ERROR.value,
                "error": f"DomainClassifyNode: invalid question payload: {exc}",
                "error_log": [f"DomainClassifyNode: invalid question payload: {exc}"],
            }

        service = CurriculumClassificationService()

        try:
            classified = asyncio.run(self._classify_all(service, questions))
        except TimeoutError as exc:
            return {
                "status": AgentStatus.RETRY.value,
                "error": str(exc),
                "error_log": [f"[RETRY] DomainClassifyNode: {exc}"],
            }
        except Exception as exc:  # noqa: BLE001 — surfaced as ERROR, not swallowed
            return {
                "status": AgentStatus.ERROR.value,
                "error": str(exc),
                "error_log": [f"[ERROR] DomainClassifyNode: {exc}"],
            }

        kb_version = classified[0]["kb_version"] if classified else ""
        emit_trace_event(
            "domain_classified",
            {"question_count": len(classified), "kb_version": kb_version},
            state,
        )

        return {
            "classified_questions": classified,
            "curriculum_domain_kb_version": kb_version,
            "status": AgentStatus.SUCCESS.value,
        }

    async def _classify_all(
        self,
        service: CurriculumClassificationService,
        questions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results = await asyncio.gather(*[service.classify_domain(q["text"]) for q in questions])
        return [
            {
                "question_id": q["question_id"],
                "text": q["text"],
                "domain": r["domain"],
                "subdomain": r["subdomain"],
                "kb_version": r["kb_version"],
            }
            for q, r in zip(questions, results, strict=True)
        ]
