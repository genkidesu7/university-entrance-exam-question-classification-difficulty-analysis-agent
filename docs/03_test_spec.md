# Test Specification

## Test Strategy
- Coverage target: 80%
- Test types: Unit / Proof-of-Boundary / Integration

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | Pass |
| TC-02 | SecurityViolationError fires on invalid input | Error raised | Pass |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations (S-5 is enforced in CI) | Pass |
| TC-04 | InvocationContext via configurable only | Direct access raises error | Pass |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start` / `node_complete` / `node_error` absent from `execute()` body | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused | Pass |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial when domain checks needed | Domain-specific input checks execute correctly (PDF size/type check, student-PII field rejection on `PreProcessNode`) | Hook body non-trivial |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial when domain checks needed | Domain-specific output checks execute correctly (residual student-PII scan on `PostProcessNode`) | Hook body non-trivial |
| TC-11 | S-4: at least one domain `emit_trace_event()` inside each `execute()` | Domain event emitted on every invocation path (`pdf_ingested`, `domain_classified`, `bloom_level_assigned`, `difficulty_scored`, `report_assembled`) | ≥1 per node |

**Location:** `tests/unit/test_*_node.py` (TC-01, 05, 08, 09, 10, 11 verified per-node), `tests/proof_of_boundary/test_state_safety.py` (TC-01, TC-03), `tests/proof_of_boundary/test_pb_invoke_order.py` (TC-05, TC-06, TC-07 implicitly via order + `@final` — see PB-6).

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | Pass |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | Pass |
| PB-3 | Level 2 → External service | Real external service connection | Data retrieved (mock-mode in CI; real KB/LLM/pass-rate service out of scope for this test suite — exercised via `USE_MOCK=true` service-layer tests instead) | Pass (mock) |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | Pass |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | Pass |
| PB-6 | Invoke execution order | `__call__()`: S-1 trust gate → S-4 `node_start` → S-2 `_security_gate_input` → `execute()` → S-3 `_security_gate_output` → S-4 `node_complete` | Order verified | Pass |
| PB-7 | Cat 2 inner-graph state boundary | Inner graph nodes read `validated_input` with `user_input` fallback | No false "missing input" errors when only `user_input` is present | Pass |

**Location:** `tests/proof_of_boundary/test_import_isolation.py` (PB-4), `test_state_safety.py` (PB-2, PB-5), `test_pb_invoke_order.py` (PB-1, PB-6), `test_pb_inner_graph_fallback.py` (PB-7). PB-3 covered indirectly via `tests/unit/test_service.py` mock-mode assertions.

## Domain Tests — Nodes & Service

| Test-ID | Component | Test | Expected Result | Result |
|---------|-----------|------|----------------|--------|
| DOM-01 | `PreProcessNode` | Valid PDF-shaped input segments into questions | `validated_input`/`segment_count` set, status success | Pass |
| DOM-02 | `PreProcessNode` | Empty `user_input` | status error, error_log populated | Pass |
| DOM-03 | `PreProcessNode` | Oversized/non-PDF/executable-magic input | `SecurityViolationError` from `_extra_security_gate_input` | Pass |
| DOM-04 | `PreProcessNode` | Batch exceeding `max_questions_per_batch` | status error, batch-size message | Pass |
| DOM-05 | `DomainClassifyNode` | Valid `validated_input` (JSON questions) | `classified_questions` with domain/subdomain, status success | Pass |
| DOM-06 | `DomainClassifyNode` | Falls back to `user_input` when `validated_input` absent (inner-graph boundary) | Does not error on missing `validated_input` | Pass |
| DOM-07 | `BloomLevelNode` | Valid `classified_questions` | Bloom level + taxonomy_version added | Pass |
| DOM-08 | `DifficultyScoreNode` | Valid `classified_questions` with domain+bloom | `difficulty_score` (1–5) added | Pass |
| DOM-09 | `PostProcessNode` | Valid `classified_questions` | `result` with classification_json/distribution_report_md/gap_analysis_md | Pass |
| DOM-10 | `PostProcessNode` | Residual student-PII pattern in report text | `SecurityViolationError` from `_extra_security_gate_output` | Pass |
| DOM-11 | `CurriculumClassificationService` | Mock mode (`USE_MOCK=true`) | Returns deterministic domain/bloom/difficulty fixture data | Pass |

**Location:** `tests/unit/test_pre_process_node.py`, `test_domain_classify_node.py`, `test_bloom_level_node.py`, `test_difficulty_score_node.py`, `test_post_process_node.py`, `test_service.py`.

## Integration Tests

| Test-ID | Test | Expected Result | Result |
|---------|------|----------------|--------|
| INT-01 | `DomainWorkflowGraph` compiles and runs standalone (domain_classify → bloom_level → difficulty_score) | Returns `classified_questions` via `get_output()` | Pass |
| INT-02 | Outer `Graph` compiles (`pre_process`/`main`/`post_process` all registered) | `compile()` succeeds, no `MissingNodeError` | Pass |
| INT-03 | Full pipeline: PDF-shaped input → classified report | `result.status == "success"`, `result` contains distribution report + gap analysis | Pass |
| INT-04 | Full pipeline: empty input | `status` in `("error", "cancelled")` | Pass |

**Location:** `tests/integration/test_domain_workflow_graph.py`, `tests/integration/test_graph.py`.

## Test Execution Summary
- Execution date: 2026-07-11
- Total tests: 40 (`pytest tests/ -v`)
- Pass: 40 / Fail: 0 / Skip: 0
- Coverage: 84% (`pytest --cov=src`, target 80%) — `src/api/server.py` is the only file at 0% (FastAPI adapter layer, not covered by unit/integration tests in this pass); all node/graph/service/schema files are 83–100%.
