# EDU-C2-029 — Unit Tests: mock_mode_enabled()
#
# Tests the shared helper directly, once, so every caller (service + inner
# nodes) inherits the guarantee instead of re-deriving it. See
# implementation_rule.md rule #1 / test_rule.md rule #1.

from src.services.mock_mode import mock_mode_enabled


def test_mock_mode_enabled_via_use_mock(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")
    monkeypatch.delenv("STG_MOCK_MODE", raising=False)
    assert mock_mode_enabled() is True


def test_mock_mode_enabled_via_stg_mock_mode_alias(monkeypatch):
    """Regression test: deploy-stg (and its local rehearsal in
    .claude/common-scripts/check-local.sh) sets STG_MOCK_MODE, never USE_MOCK."""
    monkeypatch.delenv("USE_MOCK", raising=False)
    monkeypatch.setenv("STG_MOCK_MODE", "true")
    assert mock_mode_enabled() is True


def test_mock_mode_disabled_when_neither_set(monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    monkeypatch.delenv("STG_MOCK_MODE", raising=False)
    assert mock_mode_enabled() is False


def test_mock_mode_disabled_for_falsy_value(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "false")
    monkeypatch.delenv("STG_MOCK_MODE", raising=False)
    assert mock_mode_enabled() is False
