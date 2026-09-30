"""AgentCore Platform v1.0"""

# Inner graph for the Cat 2 `main` slot (see src/graph/graph.py,
# DomainWorkflowGraphNode.get_subgraph()). Fully custom linear topology:
#   START -> domain_classify -> bloom_level -> difficulty_score -> END
# See docs/02_design.md "Composition Pattern" / "Design Decision Record".

from __future__ import annotations

from typing import Any
from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus

from src.nodes.bloom_level_node import BloomLevelNode
from src.nodes.difficulty_score_node import DifficultyScoreNode
from src.nodes.domain_classify_node import DomainClassifyNode
from src.schemas.state import State


class DomainWorkflowGraph(BaseGraph):
    """Inner graph: domain classify -> Bloom level -> difficulty score.

    Called by DomainWorkflowGraphNode.get_subgraph() in src/graph/graph.py.
    """

    @property
    def name(self) -> str:
        return "edu_c2_029_domain_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        """No mandatory config keys for this inner graph."""

    def register_nodes(self) -> None:
        """Register the 3 classification nodes. No super() — BaseGraph is abstract.

        initialize/finalize are outer-graph concerns and must not be registered here.
        """
        self._nodes["domain_classify"] = DomainClassifyNode()
        self._nodes["bloom_level"] = BloomLevelNode()
        self._nodes["difficulty_score"] = DifficultyScoreNode()

    def add_edges(self) -> None:
        """Linear pipeline: domain_classify -> bloom_level -> difficulty_score."""
        self._sg.add_edge(START, "domain_classify")
        self._sg.add_edge("domain_classify", "bloom_level")
        self._sg.add_edge("bloom_level", "difficulty_score")
        self._sg.add_edge("difficulty_score", END)

    def route(self, state: AgentState) -> str:
        """Required by BaseGraph ABC; unused (linear topology, no conditional edges)."""
        return END if state.get("status") == AgentStatus.ERROR.value else "difficulty_score"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        """Shape sub_result for DomainWorkflowGraphNode.merge_output() in graph.py."""
        return {
            "classified_questions": state.get("classified_questions", []),
            "curriculum_domain_kb_version": state.get("curriculum_domain_kb_version", ""),
            "bloom_taxonomy_version": state.get("bloom_taxonomy_version", ""),
            "status": state.get("status"),
        }
