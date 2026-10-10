"""Week 2 tests: rate limiter, sanity checks, envelope validation, logging.
Run from the project root:  python -m pytest -v"""
import pytest

from app import pipeline
from app.config import settings
from app.pipeline_types import Drop, RequestContext
from app.ratelimit import RateLimiter
from app.config import RateLimitConfig
from app.sanity import check_request, validate_envelope


# ---------------------------------------------------------------- helpers
class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def make_ctx(method="GET", path="/api/records", body=b"", headers=None, raw_path=None, too_large=False):
    return RequestContext(method=method, path=path, raw_path=raw_path if raw_path is not None else path,
                          headers=headers or {}, body=body, client_ip="1.2.3.4",
                          request_id="t", body_too_large=too_large)


def drop_of(ctx):
    with pytest.raises(Drop) as e:
        check_request(ctx, settings.sanity, settings.envelope)
    return e.value


GOOD_ENVELOPE = {"client_id": "alice", "iv": "a" * 24, "payload": "deadbeef",
                 "auth_tag": "b" * 32, "timestamp": 1720000000}


# ---------------------------------------------------------------- token bucket (unit)
def test_bucket_allows_burst_then_limits():
    clock = FakeClock()
    rl = RateLimiter(RateLimitConfig(capacity=3, refill_per_second=1, violations_before_ban=99), clock)
    assert [rl.check("ip").allowed for _ in range(3)] == [True, True, True]
    d = rl.check("ip")
    assert not d.allowed and d.kind == "limited" and d.retry_after > 0


def test_bucket_refills_over_time():
    clock = FakeClock()
    rl = RateLimiter(RateLimitConfig(capacity=2, refill_per_second=1, violations_before_ban=99), clock)
    rl.check("ip"); rl.check("ip")
    assert not rl.check("ip").allowed
    clock.advance(1.0)
    assert rl.check("ip").allowed
    assert not rl.check("ip").allowed


def test_buckets_are_per_ip():
    rl = RateLimiter(RateLimitConfig(capacity=1, refill_per_second=0.01, violations_before_ban=99), FakeClock())
    assert rl.check("a").allowed and not rl.check("a").allowed
    assert rl.check("b").allowed


def test_ban_after_repeated_violations_and_expiry():
    clock = FakeClock()
    rl = RateLimiter(RateLimitConfig(capacity=1, refill_per_second=0.01, violations_before_ban=3,
                                     ban_seconds=30), clock)
    rl.check("ip")                                   # uses the only token
    kinds = [rl.check("ip").kind for _ in range(3)]  # 3 violations
    assert kinds == ["limited", "limited", "banned"]
    assert rl.check("ip").kind == "banned"
    clock.advance(31)
    assert rl.check("ip").kind != "banned"


def test_cleanup_removes_stale_entries():
    clock = FakeClock()
    rl = RateLimiter(RateLimitConfig(cleanup_interval_seconds=10, stale_after_seconds=20), clock)
    rl.check("old")
    clock.advance(60)
    rl.check("new")          # triggers cleanup
    assert "old" not in rl.buckets and "new" in rl.buckets


# ---------------------------------------------------------------- rate limit (HTTP)
@pytest.mark.anyio
async def test_flood_returns_429_and_is_logged(client):
    pipeline.rate_limiter = RateLimiter(
        RateLimitConfig(capacity=5, refill_per_second=0.01, violations_before_ban=100))
    codes = [(await client.get("/api/records")).status_code for _ in range(8)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429] * 3
    r = await client.get("/api/records")
    assert r.headers["retry-after"].isdigit()
    events = (await client.get("/gateway/logs")).json()
    assert any(e["event_type"] == "rate_limited" and e["severity"] == "medium" for e in events)


@pytest.mark.anyio
async def test_ban_over_http(client):
    pipeline.rate_limiter = RateLimiter(
        RateLimitConfig(capacity=1, refill_per_second=0.01, violations_before_ban=2, ban_seconds=60))
    for _ in range(4):
        await client.get("/api/records")
    r = await client.get("/api/records")
    assert r.status_code == 429 and "banned" in r.json()["detail"]
    types = {e["event_type"] for e in (await client.get("/gateway/logs")).json()}
    assert "ip_banned" in types


@pytest.mark.anyio
async def test_unknown_paths_are_rate_limited_too(client):
    pipeline.rate_limiter = RateLimiter(
        RateLimitConfig(capacity=2, refill_per_second=0.01, violations_before_ban=100))
    codes = [(await client.get("/nothing-here")).status_code for _ in range(4)]
    assert codes == [404, 404, 429, 429]


# ---------------------------------------------------------------- sanity (HTTP)
@pytest.mark.anyio
@pytest.mark.parametrize("method", ["PATCH", "TRACE", "HEAD", "OPTIONS"])
async def test_disallowed_methods_405(client, method):
    r = await client.request(method, "/api/records")
    assert r.status_code == 405
    assert "GET" in r.headers["allow"]


@pytest.mark.anyio
async def test_oversized_body_413(client, monkeypatch):
    monkeypatch.setattr(settings.sanity, "max_body_bytes", 100)
    r = await client.post("/api/records", content=b'{"patient":"' + b"A" * 500 + b'"}',
                          headers={"content-type": "application/json"})
    assert r.status_code == 413
    events = (await client.get("/gateway/logs")).json()
    assert events[-1]["event_type"] == "payload_too_large" and events[-1]["severity"] == "medium"


@pytest.mark.anyio
async def test_wrong_content_type_415(client):
    r = await client.post("/api/records", content=b"patient=Eve", headers={"content-type": "text/plain"})
    assert r.status_code == 415


@pytest.mark.anyio
async def test_malformed_json_400(client):
    r = await client.post("/api/records", content=b'{"patient": ', headers={"content-type": "application/json"})
    assert r.status_code == 400 and "JSON" in r.json()["detail"]


@pytest.mark.anyio
async def test_deeply_nested_json_does_not_crash(client):
    r = await client.post("/api/records", content=b"[" * 100000,
                          headers={"content-type": "application/json"})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_valid_json_still_forwarded(client):
    r = await client.post("/api/records", json={"patient": "Zed", "diagnosis": "Ok"})
    assert r.status_code == 201


@pytest.mark.anyio
async def test_get_without_body_needs_no_content_type(client):
    assert (await client.get("/api/records")).status_code == 200


# ---------------------------------------------------------------- sanity (direct)
@pytest.mark.parametrize("path,raw", [
    ("/api/records/../secret", "/api/records/../secret"),
    ("/api/records/x", "/api/records/%2e%2e/x"),
    ("/api/records/x", "/api/records/%2E%2E%2Fx"),
    ("/api/records/%2e%2e/x", "/api/records/%252e%252e/x"),
    ("/api/records/x\\y", "/api/records/x%5cy"),
    ("/api/records/x%00", "/api/records/x%00"),
])
def test_path_traversal_blocked(path, raw):
    d = drop_of(make_ctx(path=path, raw_path=raw))
    assert d.status_code == 400 and d.event_type == "path_traversal"


def test_normal_path_ok():
    check_request(make_ctx(path="/api/records/12"), settings.sanity, settings.envelope)


def test_long_path_414():
    d = drop_of(make_ctx(path="/api/records/" + "a" * 3000))
    assert d.status_code == 414


def test_header_limits_431():
    assert drop_of(make_ctx(headers={f"h{i}": "x" for i in range(150)})).status_code == 431
    assert drop_of(make_ctx(headers={"x-big": "a" * 9000})).status_code == 431


# ---------------------------------------------------------------- envelope
def test_valid_envelope_passes():
    validate_envelope(GOOD_ENVELOPE, settings.envelope)


@pytest.mark.parametrize("field", ["client_id", "iv", "payload", "auth_tag", "timestamp"])
def test_missing_envelope_field(field):
    env = {k: v for k, v in GOOD_ENVELOPE.items() if k != field}
    with pytest.raises(Drop) as e:
        validate_envelope(env, settings.envelope)
    assert e.value.event_type == "malformed_envelope" and field in e.value.reason


@pytest.mark.parametrize("field,value", [
    ("iv", "abc"), ("iv", "z" * 24), ("auth_tag", "b" * 31), ("payload", "abc"),
    ("payload", ""), ("timestamp", "1720000000"), ("timestamp", True), ("timestamp", -5),
    ("client_id", ""), ("client_id", 123),
])
def test_bad_envelope_values(field, value):
    with pytest.raises(Drop):
        validate_envelope({**GOOD_ENVELOPE, field: value}, settings.envelope)


def test_envelope_must_be_object():
    with pytest.raises(Drop):
        validate_envelope([1, 2, 3], settings.envelope)


@pytest.mark.anyio
async def test_envelope_enforced_over_http(client, monkeypatch):
    monkeypatch.setattr(settings.envelope, "enforce", True)
    r = await client.post("/api/records", json={"patient": "Eve", "diagnosis": "Cold"})
    assert r.status_code == 400 and "envelope" in r.json()["detail"].lower()
    bad = {**GOOD_ENVELOPE, "iv": "xyz"}
    assert (await client.post("/api/records", json=bad)).status_code == 400


# ---------------------------------------------------------------- logging
@pytest.mark.anyio
async def test_log_schema_and_stats(client):
    await client.get("/api/records")
    await client.patch("/api/records")
    events = (await client.get("/gateway/logs")).json()
    required = {"timestamp", "event_type", "severity", "source_ip", "client_id", "action", "reason",
                "status_code", "request_id", "method", "path", "payload_size"}
    assert all(required <= set(e) for e in events)
    stats = (await client.get("/gateway/stats")).json()
    assert stats["total"] == 2 and stats["allowed"] == 1 and stats["dropped"] == 1
    assert stats["by_event_type"]["method_not_allowed"] == 1
