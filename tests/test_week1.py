"""Week 1 tests (proxy basics). Shared setup lives in conftest.py.
Run from the project root:  python -m pytest -v"""
import pytest


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
