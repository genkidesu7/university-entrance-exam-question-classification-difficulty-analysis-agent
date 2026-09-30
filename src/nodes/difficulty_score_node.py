"""AgentCore Platform v1.0"""

# Inner-graph node (src/graph/domain_workflow_graph.py). Final step of the
# Cat 2 main slot's subgraph — domain_classify -> bloom_level -> difficulty_score.

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.services.events import emitter
from shared.services.events.types import EventType
from shared.utils.audit_logger import emit_trace_event

from src.services.service import CurriculumClassificationService


class DifficultyScoreNode(FunctionNode):
    """Score difficulty 1-5 from domain + Bloom level + historical pass-rate data."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Scoring question difficulty...",
            metadata={"stage": "difficulty_score"},
        )
        # Inner-graph fallback rule — see DomainClassifyNode / docs/02_design.md.
        classified_questions = state.get("classified_questions") or []
        if not classified_questions:
            return {
                "status": AgentStatus.ERROR.value,
                "error": "DifficultyScoreNode: classified_questions missing or empty",
                "error_log": ["DifficultyScoreNode: classified_questions missing or empty"],
            }

        service = CurriculumClassificationService()

        try:
            scored = asyncio.run(self._score_all(service, classified_questions))
        except TimeoutError as exc:
            return {
                "status": AgentStatus.RETRY.value,
                "error": str(exc),
                "error_log": [f"[RETRY] DifficultyScoreNode: {exc}"],
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": AgentStatus.ERROR.value,
                "error": str(exc),
                "error_log": [f"[ERROR] DifficultyScoreNode: {exc}"],
            }

        emit_trace_event(
            "difficulty_scored",
            {"question_count": len(scored)},
            state,
        )

        return {
            "classified_questions": scored,
            "status": AgentStatus.SUCCESS.value,
        }

    async def _score_all(
        self,
        service: CurriculumClassificationService,
        questions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results = await asyncio.gather(*[service.score_difficulty(q["domain"], q["bloom_level"]) for q in questions])
        return [{**q, "difficulty_score": r["difficulty_score"]} for q, r in zip(questions, results, strict=True)]
