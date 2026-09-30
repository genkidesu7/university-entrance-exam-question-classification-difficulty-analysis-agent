"""AgentCore Platform v1.0"""

# Cat 2 — University Entrance Exam Question Classification & Difficulty
# Analysis Agent. Fixed 5-node outer backbone (identical to Cat 1); domain
# complexity (domain classify -> Bloom level -> difficulty score) is
# encapsulated inside DomainWorkflowGraphNode (`main` slot), which wraps the
# inner graph at src/graph/domain_workflow_graph.py. See docs/02_design.md.
#
# Pipeline:
#   START -> initialize -> pre_process -> main -> {route} -> post_process -> finalize -> END
#                                            ↓ (RETRY, max 3)
#                                         pre_process
#
#   Inside `main`: DomainWorkflowGraphNode.execute() calls
#   DomainWorkflowGraph.invoke() (domain_classify -> bloom_level -> difficulty_score).

from typing import Any, ClassVar

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState

from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State


class DomainWorkflowGraphNode(GraphNode):
    """Wraps the inner domain-classification workflow; assigned to the `main` slot."""

    # Fail fast: a partially-classified batch is not a safe report input
    # (docs/02_design.md Design Decision Record).
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def get_subgraph(self) -> Any:
        from src.graph.domain_workflow_graph import DomainWorkflowGraph

        return DomainWorkflowGraph(config=self._parent_config())

    def extract_input(self, state: AgentState) -> str:
        return str(state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "classified_questions": sub_result.get("classified_questions", []),
            "curriculum_domain_kb_version": sub_result.get("curriculum_domain_kb_version", ""),
            "bloom_taxonomy_version": sub_result.get("bloom_taxonomy_version", ""),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {}


class Graph(AgentBaseGraph):
    """University Entrance Exam Question Classification & Difficulty Analysis Agent."""

    @property
    def name(self) -> str:
        return "edu_c2_029_exam_question_classifier"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode

        max_questions_per_batch = self.config.get("max_questions_per_batch", 100)
        self._nodes["pre_process"] = PreProcessNode(max_questions_per_batch=max_questions_per_batch)
        self._nodes["main"] = DomainWorkflowGraphNode()
        self._nodes["post_process"] = PostProcessNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.
