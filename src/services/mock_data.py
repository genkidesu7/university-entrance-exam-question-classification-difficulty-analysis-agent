"""AgentCore Platform v1.0"""

# Mock stubs for CurriculumClassificationService, used only when USE_MOCK is set.
# No credentials, no network calls — deterministic fixture data for local/CI runs.

from __future__ import annotations

from typing import Any

_MOCK_KB_VERSION = "mext-2022-revision-mock-v1"
_MOCK_TAXONOMY_VERSION = "bloom-revised-mock-v1"
_MOCK_RUBRIC_VERSION = "difficulty-rubric-mock-v1"


async def stub_classify_domain(question_text: str) -> dict[str, Any]:
    """Deterministic mock domain classification (no real vector search)."""
    return {
        "domain": "Mathematics",
        "subdomain": "Algebra",
        "kb_version": _MOCK_KB_VERSION,
    }


async def stub_classify_bloom_level(question_text: str) -> dict[str, Any]:
    """Deterministic mock Bloom level classification (no real LLM call)."""
    return {
        "bloom_level": "application",
        "taxonomy_version": _MOCK_TAXONOMY_VERSION,
    }


async def stub_score_difficulty(domain: str, bloom_level: str) -> dict[str, Any]:
    """Deterministic mock difficulty score (no real pass-rate lookup)."""
    return {
        "difficulty_score": 3,
        "rubric_version": _MOCK_RUBRIC_VERSION,
    }
