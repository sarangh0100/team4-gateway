"""
Middleware pipeline.

Order:
  1. rate_limit           -> Week 2 (token bucket + bans). First, so floods of bad requests
                             also burn tokens and get banned.
  2. sanity_check         -> Week 2 (method, path, headers, size, content type, JSON, envelope)
  3. resolve_route        -> Week 2 (path prefix -> internal service, else 404)
  4. validate_certificate -> Week 3 (Team 1)
  5. decrypt_envelope     -> Week 3 (Team 2)
  6. replay_check         -> Week 3 (Team 2)
  7. authorize            -> Week 3 (Team 3: JWT + RBAC/Biba)
Then: forward -> log.

Each stage receives a RequestContext and either returns (allow) or raises Drop (block).
"""
import math

from .config import settings
from .pipeline_types import Drop, RequestContext  # noqa: F401  (re-exported for main.py)
from .ratelimit import RateLimiter
from .sanity import check_request

rate_limiter = RateLimiter(settings.rate_limit)


# ---- Week 2 stages -------------------------------------------------------------
async def rate_limit(ctx: RequestContext) -> None:
    decision = rate_limiter.check(ctx.client_ip)
    if decision.allowed:
        return
    retry = str(max(1, math.ceil(decision.retry_after)))
    if decision.kind == "banned":
        raise Drop(429, f"IP temporarily banned, retry in {retry}s", "ip_banned",
                   headers={"Retry-After": retry})
    raise Drop(429, "Too many requests", "rate_limited", headers={"Retry-After": retry})


async def sanity_check(ctx: RequestContext) -> None:
    check_request(ctx, settings.sanity, settings.envelope)


async def resolve_route(ctx: RequestContext) -> None:
    match = settings.match_route(ctx.path)
    if match is None:
        raise Drop(404, "Not found", "no_route")
    ctx.route_prefix, ctx.upstream_url = match


# ---- Week 3 stubs: pass-through for now ---------------------------------------
async def validate_certificate(ctx: RequestContext) -> None:
    return None  # Week 3: X.509 check against Team 1 Root CA + CRL


async def decrypt_envelope(ctx: RequestContext) -> None:
    return None  # Week 3: AES-256-GCM via Team 2 helpers; tag failure -> Drop(400, tampering)


async def replay_check(ctx: RequestContext) -> None:
    return None  # Week 3: timestamp window + IV/sequence tracking


async def authorize(ctx: RequestContext) -> None:
    return None  # Week 3: RS256 JWT verify + RBAC/Biba via Team 3


PIPELINE: list = [
    rate_limit,
    sanity_check,
    resolve_route,
    validate_certificate,
    decrypt_envelope,
    replay_check,
    authorize,
]


async def run_pipeline(ctx: RequestContext) -> None:
    for stage in PIPELINE:
        await stage(ctx)
