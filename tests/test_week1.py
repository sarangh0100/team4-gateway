"""
Week 1 tests. Run from the project root:
    pip install -r tests/requirements.txt
    pytest -v
Uses in-process ASGI transport, so Docker is NOT needed.
"""
import os
import sys
import httpx
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "gateway-service"))
os.environ["ROUTES_FILE"] = os.path.join(ROOT, "gateway-service", "config", "routes.yaml")

from app import main as gw_main            # noqa: E402  (gateway app)
import importlib.util                      # noqa: E402

spec = importlib.util.spec_from_file_location(
    "mock_main", os.path.join(ROOT, "mock-records-service", "app", "main.py"))
mock_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mock_main)


@pytest.fixture
async def client():
    # Point the gateway's upstream client straight at the mock app (no network).
    gw_main.app.state.http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_main.app), timeout=5)
    transport = httpx.ASGITransport(app=gw_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as c:
        yield c
    await gw_main.app.state.http.aclose()


@pytest.mark.anyio
async def test_health(client):
    r = await client.get("/gateway/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.anyio
async def test_forward_get(client):
    r = await client.get("/api/records")
    assert r.status_code == 200 and len(r.json()) >= 2


@pytest.mark.anyio
async def test_forward_get_one_and_404(client):
    assert (await client.get("/api/records/1")).json()["patient"] == "Alice"
    assert (await client.get("/api/records/999")).status_code == 404


@pytest.mark.anyio
async def test_forward_post(client):
    r = await client.post("/api/records", json={"patient": "Eve", "diagnosis": "Cold"})
    assert r.status_code == 201 and r.json()["patient"] == "Eve"


@pytest.mark.anyio
async def test_unknown_route_dropped(client):
    r = await client.get("/secret/admin")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_events_logged(client):
    await client.get("/api/records")
    await client.get("/nope")
    types = [e["event_type"] for e in (await client.get("/gateway/logs")).json()]
    assert "request_allowed" in types and "no_route" in types


@pytest.fixture
def anyio_backend():
    return "asyncio"
