"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict (see ADR-005 for the prohibited
# alternatives). LangGraph checkpoints use msgpack serialization, so only
# plain serializable fields are allowed. Do NOT add credentials or secrets.

from typing import Any

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state.

    All shared fields (user_input, status, session_id, node_history,
    error_log, hitl_*, etc.) are inherited from AgentState.
    """

    # Set by pre_process: JSON-encoded list of {question_id, text} segmented
    # from the ingested exam PDF.
    validated_input: str

    # Set by pre_process: number of questions segmented from the batch.
    segment_count: int

    # Set by main (inner graph): per-question
    # {question_id, domain, subdomain, bloom_level, difficulty_score}.
    classified_questions: list[dict[str, Any]]

    # Set by inner domain_classify node: KB version used, for audit/traceability.
    curriculum_domain_kb_version: str

    # Set by inner bloom_level node: taxonomy mapping version used.
    bloom_taxonomy_version: str

    # Set by post_process: {classification_json, distribution_report_md, gap_analysis_md}.
    result: dict[str, Any]
