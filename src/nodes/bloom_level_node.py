"""AgentCore Platform v1.0"""

# Inner-graph node (src/graph/domain_workflow_graph.py). Runs after
# domain_classify inside the Cat 2 main slot's subgraph.

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.secrets import SecretProvider
from shared.services.events import emitter
from shared.services.events.types import EventType
from shared.utils.audit_logger import emit_trace_event

from src.services.mock_mode import mock_mode_enabled
from src.services.service import AZURE_LLM_SECRET_KEYS, CurriculumClassificationService


class BloomLevelNode(FunctionNode):
    """LLM-classify cognitive level per Bloom's revised taxonomy."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Classifying Bloom cognitive level with the LLM...",
            metadata={"stage": "bloom_level"},
        )
        # Inner-graph fallback rule — see DomainClassifyNode / docs/02_design.md.
        classified_questions = state.get("classified_questions") or []
        if not classified_questions:
            return {
                "status": AgentStatus.ERROR.value,
                "error": "BloomLevelNode: classified_questions missing or empty",
                "error_log": ["BloomLevelNode: classified_questions missing or empty"],
            }

        ctx = InvocationContext.from_state(state)
        # Mock mode's stub path never touches credential_handle — do not demand
        # a real secret to reach it (implementation_rule.md rule #2).
        credential_handle: SecretProvider | str = "mock"
        if not mock_mode_enabled():
            for key in AZURE_LLM_SECRET_KEYS:
                ctx.secrets.require(key)
            credential_handle = ctx.secrets
        service = CurriculumClassificationService()

        try:
            updated = asyncio.run(self._classify_all(service, classified_questions, credential_handle))
        except TimeoutError as exc:
            return {
                "status": AgentStatus.RETRY.value,
                "error": str(exc),
                "error_log": [f"[RETRY] BloomLevelNode: {exc}"],
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": AgentStatus.ERROR.value,
                "error": str(exc),
                "error_log": [f"[ERROR] BloomLevelNode: {exc}"],
            }

        taxonomy_version = updated[0]["taxonomy_version"] if updated else ""
        emit_trace_event(
            "bloom_level_assigned",
            {"question_count": len(updated), "taxonomy_version": taxonomy_version},
            state,
        )

        return {
            "classified_questions": updated,
            "bloom_taxonomy_version": taxonomy_version,
            "status": AgentStatus.SUCCESS.value,
        }

    async def _classify_all(
        self,
        service: CurriculumClassificationService,
        questions: list[dict[str, Any]],
        credential_handle: SecretProvider | str,
    ) -> list[dict[str, Any]]:
        results = await asyncio.gather(*[service.classify_bloom_level(q["text"], credential_handle) for q in questions])
        return [
            {
                **q,
                "bloom_level": r["bloom_level"],
                "taxonomy_version": r["taxonomy_version"],
            }
            for q, r in zip(questions, results, strict=True)
        ]
