# EDU-C2-029 — Integration Tests: /invoke over a real ASGI transport
#
# Regression test for implementation_rule.md #3: agent.invoke() is sync and
# its nodes call asyncio.run() internally. Calling it directly from an async
# route (without asyncio.to_thread) raises "asyncio.run() cannot be called
# from a running event loop" inside the node, which the node's exception
# handling silently turns into status: "error" — a 200 response with no
# visible crash. An in-process sync call to agent.invoke() (as in
# test_graph.py) never enters a running event loop, so it can't reproduce
# this — only a test that drives the ASGI app itself does.

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

VALID_PDF_TEXT = (
    "%PDF-1.7\n"
    "1. What is the derivative of x^2?\n"
    "2. Solve for x: 2x + 3 = 7\n"
)


@pytest.fixture(autouse=True)
def use_mock_mode(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")
    monkeypatch.setenv(
        "INVOKE_AUTH_TOKEN", "test-invoke-token-for-http-integration-test"
    )


@pytest_asyncio.fixture
async def app(monkeypatch):
    # src/api/server.py builds `agent` at import time, so USE_MOCK/INVOKE_AUTH_TOKEN
    # must be set before the module is imported. ASGITransport does not run FastAPI's
    # lifespan, so enter it by hand — otherwise the agent is never compiled.
    import importlib

    import src.api.server as server_module

    importlib.reload(server_module)
    async with server_module._lifespan(server_module.app):
        yield server_module.app


@pytest.mark.asyncio
async def test_invoke_endpoint_succeeds_over_http(app):
    """Drives the real ASGI app on a running event loop — the only way to
    reproduce the async-route/asyncio.run() boundary bug."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/invoke",
            json={"input": VALID_PDF_TEXT},
            headers={
                "Authorization": "Bearer test-invoke-token-for-http-integration-test"
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"


@pytest.mark.asyncio
async def test_invoke_endpoint_rejects_missing_token(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/invoke", json={"input": VALID_PDF_TEXT})

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_endpoint(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
