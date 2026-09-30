# Template Design Specification

Status: completed
Date: 2026-07-11
Reviewer: [TBD]

## Position in AgentCore Architecture

- **Agent Class**: `Graph` (outer, `src/graph/graph.py`) — `AgentBaseGraph` L1 direct
- **L1 Base**: AgentBaseGraph (Cat 2 — fixed multi-step workflow for one job-to-be-done, per `docs/01_proposal.md` Cat Self-Assessment)
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

This agent classifies past exam questions (PDF input) by MEXT 学習指導要領 curriculum domain, Bloom's taxonomy cognitive level, and difficulty (1–5), then assembles a distribution + gap-analysis report. Per the proposal's 6-step workflow (§4), the outer graph handles ingest/segmentation and report assembly directly in `pre_process`/`post_process`; the three classification steps that need per-question orchestration (domain classify → Bloom level → difficulty score) are delegated to an inner `DomainWorkflowGraph` wrapped by a `GraphNode` in the outer `main` slot. This follows the Cat 2 composition pattern (outer 5-node backbone + inner custom-topology subgraph) rather than cramming all 6 steps into a single `FunctionNode`, because each classification step is a distinct retrieval/LLM call with its own failure mode and needs independent node-level tracing (S-4) and retry semantics.

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | Framework default init | — | — | InitializeNode (default) |
| pre_process | PDF ingest + question segmentation | `user_input` (PDF path/base64), `input_context` | `validated_input` (segmented question list, JSON), `segment_count`, `status` | `PreProcessNode` |
| main | Domain classify → Bloom level → difficulty score (inner subgraph) | `validated_input` | `classified_questions`, `status` | `DomainWorkflowGraphNode` (GraphNode wrapping `DomainWorkflowGraph`) |
| post_process | Report assembly (distribution + gap analysis) | `classified_questions` | `result` (report package: JSON + markdown report), `status` | `PostProcessNode` |
| finalize | Framework default finalize | — | — | FinalizeNode (default) |

### Data Flow

```
START → initialize → pre_process → main → {route} → post_process → finalize → END
                                            ↓ (retry, max_retry=3)
                                          pre_process

Inside `main` (DomainWorkflowGraphNode → DomainWorkflowGraph, inner graph):
  START → domain_classify → bloom_level → difficulty_score → END
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `validated_input` | `str` (JSON-encoded list of `{question_id, text}`) | Segmented question set produced by `pre_process`, consumed by inner graph | Yes (set by pre_process) |
| `segment_count` | `int` | Number of questions segmented from the input PDF; used for batch-size validation against `max_questions_per_batch` | Yes (set by pre_process) |
| `classified_questions` | `list[dict]` | Per-question `{question_id, domain, subdomain, bloom_level, difficulty_score}` produced by the inner graph | Yes (set by main) |
| `curriculum_domain_kb_version` | `str` | Version tag of the MEXT 学習指導要領 KB used for this run (audit/traceability) | Yes (set by domain_classify inner node) |
| `bloom_taxonomy_version` | `str` | Version tag of the Bloom mapping table used (audit/traceability, per proposal §11 risk mitigation) | Yes (set by bloom_level inner node) |
| `result` | `dict` (`{classification_json, distribution_report_md, gap_analysis_md}`) | Final output package assembled by `post_process` | Yes (set by post_process) |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types) — `classified_questions` is `list[dict]` of primitives only, no nested Pydantic objects
- No JWT, API keys, credentials in State (checkpoint DB leakage) — the Azure OpenAI credentials are resolved via `ctx.secrets.require(...)` inside the node, never stored in state
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)
- No student-identifying data ever enters State (proposal §4 note) — PII strip happens at `pre_process` ingest time, before `validated_input` is set; enforced further via `_extra_security_gate_input()` on `PreProcessNode`

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle) — used to resolve vector DB and LLM credentials in the domain service layer
- [x] ConnectionPolicy (retry/timeout strategy) — applied to vector DB retrieval and LLM calls in `src/services/service.py`
- [ ] SecurityViolationError — not raised directly; framework's default S-2/S-3 gates handle standard violations
- [x] S-2: `_extra_security_gate_input()` on `PreProcessNode` — rejects non-PDF/executable content and PDFs >20MB (proposal §4 Step 1: "Parse exam PDF, max 20MB, reject non-PDF/executable content"); confirms no student-identifying fields present in segmented question text
- [x] S-3: `_extra_security_gate_output()` on `PostProcessNode` — re-scans the assembled report/JSON output for any residual student-identifying content before it leaves the graph
- [x] S-4: `emit_trace_event()` — domain events emitted per node:
  - `pre_process`: `"pdf_ingested"` (page_count, segment_count)
  - inner `domain_classify`: `"domain_classified"` (question_id, domain, subdomain, kb_version)
  - inner `bloom_level`: `"bloom_level_assigned"` (question_id, bloom_level, taxonomy_version)
  - inner `difficulty_score`: `"difficulty_scored"` (question_id, score, rubric_version)
  - `post_process`: `"report_assembled"` (question_count, domain_coverage_summary)

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass (`pre_process`, `post_process`, and inner `domain_classify`/`bloom_level`/`difficulty_score` nodes) → framework `@final` gate always runs automatically; extended via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` (outer `main` slot, `DomainWorkflowGraphNode`) → deliberate no-op; the inner graph's own `FunctionNode` gates already applied per inner node
> - No custom `BaseNode` subclass used in this design

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — outer `AgentBaseGraph` backbone with `main` slot wrapping inner `DomainWorkflowGraph`
- **Composition target**: `src/graph/domain_workflow_graph.py` — inherits `BaseGraph` directly (fully custom 3-node linear topology: `domain_classify → bloom_level → difficulty_score`, no `pre_process`/`main`/`post_process` slots needed at the inner level)
- **Error propagation strategy**: `propagate` (default) — a failure in domain classification, Bloom tagging, or difficulty scoring for a batch should fail the whole run rather than silently degrade, since the proposal's output is a structured report consumed by downstream curriculum tooling (partial/incorrect classification data is worse than a clear failure). `propagate_hitl`: `False` — no human-in-the-loop step in this pipeline; the proposal treats misclassification as an advisory risk mitigated by periodic audits (§11), not by inline human review per question.

**Inner graph node fallback rule (mandatory):** every inner-graph node (`domain_classify`, `bloom_level`, `difficulty_score`) must read the primary input as `state.get("validated_input", state.get("user_input", ""))`, since the inner graph receives fresh state on `invoke()` and does not inherit the outer `validated_input` field by any other path.

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | **AgentBaseGraph** | Proposal is explicit: fixed 6-step pipeline per batch, no self-directed termination or autonomous think→act→observe loop — Cat 2, not Cat 3 |
| Composition pattern | Single `FunctionNode` in `main` (all 3 classification steps inline) | `GraphNode` wrapping inner `DomainWorkflowGraph` (3 separate inner nodes) | **GraphNode + inner graph** | Domain classify (vector retrieval), Bloom level (LLM call), and difficulty score (heuristic combine) are distinct failure domains needing independent S-4 trace events and clean per-step responsibility; matches the Cat 2 sample pattern in `src/examples/graph_cat2_sample.py` |
| Inner graph parent | `BaseGraph` (fully custom topology) | `AgentBaseGraph` (5-node pipeline) | **BaseGraph** | Inner workflow is a fixed 3-step linear pipeline (no `pre_process`/`post_process` distinction needed at this level) — matches `src/examples/domain_workflow_graph_sample.py` guidance to use `BaseGraph` for custom topology |
| PDF ingest + segmentation location | Separate inner-graph step | Outer `pre_process` | **Outer `pre_process`** | Ingest/segmentation is input validation/enrichment (framework's intended purpose for `pre_process`), not domain classification logic; keeps the inner graph focused purely on the 3 classification steps |
| Report assembly location | Separate inner-graph step | Outer `post_process` | **Outer `post_process`** | Report assembly formats the already-classified batch into markdown output — an output-shaping concern, matching `post_process`'s framework role |
| `base_type` in `config/agent.yaml` | `RAGAgent` (L2 type) | `null` (no L2 type) | **`null`** | Proposal's Cat Self-Assessment explicitly confirms "Is L2 inheritance avoided? — no unnecessary intermediate inheritance"; `AgentBaseGraph` is used L1-direct, so no L2 `base_type` applies (see `config/agent.yaml`, updated in Stage 03) |
| `error_strategy` on `DomainWorkflowGraphNode` | `propagate` | `handle` | **`propagate`** | A partially-classified batch is not a safe degraded output for a curriculum-planning report; fail fast and let the caller retry/investigate rather than emit a report with silently-missing questions |
