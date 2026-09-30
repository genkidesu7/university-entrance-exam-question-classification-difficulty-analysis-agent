# PB-7: HITL Interrupt Propagation Verification
#
# EDU-C2-029 does not enable HITL (config/agent.yaml has no hitl.enabled key,
# and docs/02_design.md's Composition Pattern explicitly sets propagate_hitl:
# False — misclassification risk is handled via periodic audits per the
# proposal, not inline human review). This test still verifies the framework
# boundary itself, end-to-end through a real compiled graph:
#
# 1. Inside BaseNode.__call__(), interrupt() raises GraphInterrupt (a
#    GraphBubbleUp subclass), which must bubble up through the node's
#    `except GraphBubbleUp: raise` clause rather than being caught by the
#    generic `except Exception` below it and turned into status: "error".
# 2. LangGraph's compiled graph catches that GraphInterrupt internally and
#    returns {"__interrupt__": [...]} instead of raising it further.
# 3. AgentBaseGraph.invoke() sees that interrupt marker and — because this
#    graph has no checkpointer attached (no memory_enabled/hitl.enabled in
#    config, matching this project's actual config) — raises a clear
#    RuntimeError telling the caller HITL isn't configured, rather than
#    silently returning status: "error" as if the node had failed.
#
# Confirms the framework's HITL boundary fails loudly and correctly if this
# template ever adopts interrupt() without first enabling hitl.enabled/
# memory_enabled, rather than silently misreporting it as a node error.

from typing import Any, ClassVar

import pytest
from langgraph.graph import END, START
from langgraph.types import interrupt

from framework.graph.base_graph import BaseGraph
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel


class _InterruptingNode(FunctionNode):
    """Minimal node exercising the D6 interrupt() pattern for this test only."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict:
        feedback = interrupt({"draft": "low-confidence classification", "reason": "test"})
        return {"hitl_draft": "low-confidence classification", "hitl_feedback": feedback}


class _InterruptingGraph(BaseGraph):
    """Single-node graph wrapping _InterruptingNode, used only to drive
    interrupt() through a real compiled LangGraph runnable context —
    interrupt() raises RuntimeError("Called get_config outside of a runnable
    context") if invoked directly via node(state) with no graph around it."""

    @property
    def name(self) -> str:
        return "pb7_interrupt_test_graph"

    @property
    def state_schema(self) -> type:
        return AgentState

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        self._nodes["interrupting"] = _InterruptingNode()

    def add_edges(self) -> None:
        self._sg.add_edge(START, "interrupting")
        self._sg.add_edge("interrupting", END)

    def route(self, state: AgentState) -> str:
        return END

    def get_output(self, state: AgentState) -> dict:
        return {"status": state.get("status"), "node_history": state.get("node_history", [])}


class TestPB7HitlInterruptPropagation:
    def test_interrupt_without_checkpointer_fails_loudly_not_as_status_error(self):
        """No hitl.enabled/memory_enabled configured (matches this project's
        actual config/agent.yaml) — AgentBaseGraph.invoke() must raise
        RuntimeError telling the caller HITL isn't configured, and must NOT
        silently return status: "error" as if the node itself had failed."""
        graph = _InterruptingGraph(config={})
        graph.compile()

        with pytest.raises(RuntimeError, match="interrupt\\(\\) called but no checkpointer"):
            graph.invoke("trigger interrupt")

    def test_interrupt_is_not_swallowed_as_a_node_error_by_base_node_call(self):
        """Directly exercises BaseNode.__call__()'s except GraphBubbleUp: raise
        clause via LangGraph's own runnable context (a bare compiled
        single-node StateGraph, no checkpointer). GraphInterrupt propagates
        out of _InterruptingNode.__call__() and LangGraph's own runner catches
        it to produce {"__interrupt__": [...]} — the key assertion is that
        `status` is never overwritten to "error" along this path, which is
        what would happen if BaseNode.__call__()'s except GraphBubbleUp: raise
        clause were ever removed or narrowed to not cover GraphInterrupt."""
        from langgraph.graph import END, START, StateGraph

        from framework.schemas.agent_state import AgentState

        sg = StateGraph(AgentState)
        sg.add_node("interrupting", _InterruptingNode(), input_schema=AgentState)
        sg.add_edge(START, "interrupting")
        sg.add_edge("interrupting", END)
        compiled = sg.compile()

        initial_state = {
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
            "correlation_id": "pb7-test",
            "session_id": "pb7-test",
            "thread_id": "pb7-test",
            "trace_id": "",
            "caller_id": "",
            "hitl_allowed": True,
            "status": AgentStatus.PENDING.value,
            "retry_count": 0,
            "hitl_count": 0,
            "node_history": [],
            "error_log": [],
            "execution_time": {},
        }

        result = compiled.invoke(initial_state)

        assert result.get("__interrupt__"), (
            "expected LangGraph to report a pending interrupt via '__interrupt__'"
        )
        assert result.get("status") != AgentStatus.ERROR.value, (
            "interrupt() must propagate as a LangGraph interrupt, not be "
            "swallowed into status: error by BaseNode.__call__()'s exception handling"
        )
        assert result.get("error_log") in (None, []), (
            "an interrupting node must not populate error_log — that would "
            "indicate the exception was caught as a real error, not an interrupt"
        )
