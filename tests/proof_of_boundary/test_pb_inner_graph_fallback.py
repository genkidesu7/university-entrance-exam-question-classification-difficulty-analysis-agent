# PB-7: Cat 2 inner-graph state boundary
# Verifies every inner-graph node (src/graph/domain_workflow_graph.py) that
# consumes the primary input text falls back to user_input when
# validated_input is absent — the inner graph's initial_state only carries
# user_input (BaseGraph.invoke() does not copy the outer pre_process's
# validated_input in). See docs/02_design.md "Composition Pattern".

import ast
import os


def _get_source(filepath: str) -> str:
    with open(filepath, "r") as f:
        return f.read()


def _execute_body_reads_validated_input_with_fallback(source: str) -> bool:
    """Detect the state.get("validated_input", state.get("user_input", "")) pattern."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "validated_input"
                and len(node.args) > 1
            ):
                fallback = node.args[1]
                if (
                    isinstance(fallback, ast.Call)
                    and isinstance(fallback.func, ast.Attribute)
                    and fallback.func.attr == "get"
                    and fallback.args
                    and isinstance(fallback.args[0], ast.Constant)
                    and fallback.args[0].value == "user_input"
                ):
                    return True
    return False


class TestInnerGraphFallback:
    """PB-7: inner-graph nodes that read the primary input text must not read
    validated_input without a user_input fallback.

    Only domain_classify_node.py consumes the raw input text — bloom_level_node.py
    and difficulty_score_node.py read classified_questions (produced by the prior
    inner node), so they are not in scope for this boundary check.
    """

    INNER_GRAPH_NODE_FILES = [
        "src/nodes/domain_classify_node.py",
    ]

    def test_inner_nodes_have_validated_input_fallback(self):
        repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
        violations = []
        for rel_path in self.INNER_GRAPH_NODE_FILES:
            filepath = os.path.join(repo_root, rel_path)
            source = _get_source(filepath)
            if not _execute_body_reads_validated_input_with_fallback(source):
                violations.append(rel_path)

        assert violations == [], (
            "Inner-graph nodes missing the validated_input/user_input fallback "
            f"pattern: {violations}"
        )
