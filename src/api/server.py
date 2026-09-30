"""AgentCore Platform v1.0"""

# Standalone HTTP entry point for the agent.
# Entry points are adapters only — no business logic here.
# For platform-level routing, AgentGateway calls agent.invoke() directly.

import asyncio
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from framework.utils.config_loader import load_config
from shared.secrets import InMemoryProvider, SecretProvider
from shared.secrets import factory as secrets_factory
from shared.secrets.chained_provider import ChainedSecretProvider
from src.graph.graph import Graph
from src.services.service import AZURE_LLM_SECRET_KEYS

_NAMESPACE = "edu"
_AGENT_NAME = "edu-c2-029"

# Same config_dir / "config.yaml" convention as AgentRegistry._compile_and_cache()
# (mediator/registry/agent_registry.py) — absent config.yaml is tolerated, matching
# the registry's own `if exists() else {}` guard. Without this, the standalone
# adapter always ran with config={}, so hitl.enabled / memory_enabled / max_retry /
# max_questions_per_batch silently never reached Graph() on this path.
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
_config = load_config(str(_CONFIG_PATH)) if _CONFIG_PATH.exists() else {}


def _build_secrets_provider() -> SecretProvider:
    """Process env vars (Marketplace "User-defined Environment Variables", docker -e)
    first, then the env/agents/<ns>/<agent>/.env.<env> dotenv tree. A bare
    secrets_factory() only sees the dotenv files."""
    env_values = {key: os.environ[key] for key in AZURE_LLM_SECRET_KEYS if os.environ.get(key)}
    return ChainedSecretProvider(
        InMemoryProvider(env_values, namespace=_NAMESPACE, agent_name=_AGENT_NAME),
        secrets_factory(namespace=_NAMESPACE, agent_name=_AGENT_NAME),
        namespace=_NAMESPACE,
        agent_name=_AGENT_NAME,
    )


_secrets_provider = _build_secrets_provider()
agent = Graph(config=_config)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Compile and provision secrets once for the process lifetime — not at
    import time, so a bare `import src.api.server` (e.g. for a test) never
    has the side effect of compiling the graph."""
    # Mirror AgentRegistry._compile_and_cache()'s conditional checkpointer — hitl.enabled
    # or memory_enabled needs one, or interrupt()/memory silently no-ops on this path.
    # This process runs exactly one agent, so a private MemorySaver per process is the
    # standalone-path equivalent of the registry's shared checkpointer.
    hitl_enabled = agent.config.get("hitl", {}).get("enabled", False)
    needs_checkpointer = agent.config.get("memory_enabled") or hitl_enabled
    agent.compile(checkpointer=MemorySaver() if needs_checkpointer else None)
    agent.provision_secrets(_secrets_provider)
    yield


app = FastAPI(title="Agent", lifespan=_lifespan)


class InvokeRequest(BaseModel):
    input: str
    session_id: str = ""


def _bearer_matches(supplied: str, expected: str) -> bool:
    """Constant-time bearer comparison that is safe for non-ASCII header input."""
    return secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode())


def _resolve_standalone_trust(
    current: TrustLevel, authorization: str, invoke_auth_token: str | None, internal_runner_token: str | None
) -> TrustLevel:
    """Authenticate standalone callers without allowing external-token elevation.

    STG_INTERNAL_RUNNER_TOKEN is a distinct, CI-generated deployment credential.
    It is considered only for an anonymous caller and maps exactly to INTERNAL;
    INVOKE_AUTH_TOKEN remains VERIFIED_EXTERNAL. Middleware-established trust is
    never changed.
    """
    if current is not TrustLevel.ANONYMOUS:
        return current
    if internal_runner_token and _bearer_matches(authorization, internal_runner_token):
        return TrustLevel.INTERNAL
    if invoke_auth_token and _bearer_matches(authorization, invoke_auth_token):
        return TrustLevel.VERIFIED_EXTERNAL
    if internal_runner_token or invoke_auth_token:
        # Generic body on purpose — do not leak whether the token was absent,
        # malformed, or wrong.
        raise HTTPException(status_code=401, detail="Token is invalid or expired.")
    return TrustLevel.ANONYMOUS


@app.post("/invoke")
async def invoke(req: InvokeRequest, request: Request) -> dict[str, Any]:
    # Standalone/STG caller auth (deployment-level bearer tokens). This adapter
    # is the entry-point auth boundary (standalone equivalent of platform
    # AuthMiddleware). Both values are deployment-level caller credentials, not agent
    # secrets: no InvocationContext exists before this boundary, so ctx.secrets
    # cannot apply.
    trust = _resolve_standalone_trust(
        getattr(request.state, "trust_level", TrustLevel.ANONYMOUS),
        request.headers.get("authorization", ""),
        os.environ.get("INVOKE_AUTH_TOKEN"),
        os.environ.get("STG_INTERNAL_RUNNER_TOKEN"),
    )
    with bound_secrets(agent._secrets_provider):
        ctx = InvocationContext(
            session_id=req.session_id or str(uuid4()),
            caller_trust_level=trust,
            caller_id=getattr(request.state, "caller_id", ""),
        )
        # agent.invoke() is sync, and its nodes call asyncio.run() internally
        # (DomainClassifyNode/BloomLevelNode/DifficultyScoreNode). Calling it
        # directly here would raise "asyncio.run() cannot be called from a
        # running event loop" inside the node — silently swallowed into
        # status: "error" by the node's exception handling, a 200 response
        # with no visible crash. asyncio.to_thread offloads it to a worker
        # thread and propagates the current contextvars.Context automatically,
        # which bound_secrets() above relies on.
        return await asyncio.to_thread(agent.invoke, req.input, ctx=ctx)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": _AGENT_NAME}
