"""Shared test setup: loads the gateway + mock service in-process (no Docker needed)."""
import importlib.util
import os
import sys

import httpx
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "gateway-service"))
os.environ["ROUTES_FILE"] = os.path.join(ROOT, "gateway-service", "config", "routes.yaml")

from app import main as gw_main            # noqa: E402
from app import pipeline                   # noqa: E402
from app.config import settings            # noqa: E402
from app.logger import reset_state         # noqa: E402
from app.ratelimit import RateLimiter      # noqa: E402

spec = importlib.util.spec_from_file_location(
    "mock_main", os.path.join(ROOT, "mock-records-service", "app", "main.py"))
mock_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mock_main)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_state():
    """Every test starts with an empty log buffer and a fresh rate limiter."""
    reset_state()
    pipeline.rate_limiter = RateLimiter(settings.rate_limit)
    yield


@pytest.fixture
async def client():
    gw_main.app.state.http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_main.app), timeout=5)
    transport = httpx.ASGITransport(app=gw_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as c:
        yield c
    await gw_main.app.state.http.aclose()
