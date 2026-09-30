"""AgentCore Platform v1.0"""

# Shared mock-mode gate — feature flag, not a credential (os.environ read is OK).
# One helper, imported everywhere USE_MOCK is checked, so a future rename or
# alias addition only needs one edit. See implementation_rule.md rule #1.

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

_env: dict[str, str | None] = dotenv_values(Path(__file__).parent.parent.parent / ".env")


def _get_flag(key: str) -> str:
    """OS env takes precedence over .env file."""
    return os.environ.get(key) or _env.get(key) or ""


_TRUTHY = ("1", "true", "yes")


def mock_mode_enabled() -> bool:
    """True when mock mode is on, via either accepted alias.

    USE_MOCK is the canonical flag (what tests set). STG_MOCK_MODE is what the
    deploy-stg CI job and its local rehearsal (check-local.sh) actually set —
    it is otherwise a CI-script-only variable never exported to the uvicorn
    process, so a fresh STG deploy would silently run in real (non-mock) mode
    with no provisioned secrets and fail every classification call. Checking
    both here, once, means a future rename only needs one edit.
    """
    return _get_flag("USE_MOCK").lower() in _TRUTHY or _get_flag("STG_MOCK_MODE").lower() in _TRUTHY
