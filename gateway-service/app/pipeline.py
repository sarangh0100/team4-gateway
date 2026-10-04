"""
Middleware pipeline skeleton.

Order (fixed now, filled in during later weeks):
  1. sanity_check        -> Week 2
  2. rate_limit          -> Week 2
  3. validate_certificate-> Week 3 (Team 1)
  4. decrypt_envelope    -> Week 3 (Team 2)
  5. replay_check        -> Week 3 (Team 2)
  6. authorize           -> Week 3 (Team 3: JWT + RBAC/Biba)
Then: forward -> log.

Each stage receives a RequestContext and either returns normally (allow)
or raises Drop (block the request).
"""
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


class Drop(Exception):
    """Raised by a stage to block the request."""

    def __init__(self, status_code: int, reason: str, event_type: str):
        self.status_code = status_code
        self.reason = reason
        self.event_type = event_type
        super().__init__(reason)


@dataclass
class RequestContext:
    method: str
    path: str
    headers: dict
    body: bytes
    client_ip: str
    request_id: str
    route_prefix: Optional[str] = None
    upstream_url: Optional[str] = None
    client_id: Optional[str] = None      # filled by decrypt stage (Week 3)
    claims: Optional[dict] = None        # filled by authorize stage (Week 3)
    extra: dict = field(default_factory=dict)


Stage = Callable[[RequestContext], Awaitable[None]]


# ---- Stage stubs: pass-through for Week 1 -------------------------------------
async def sanity_check(ctx: RequestContext) -> None:
    return None  # Week 2: method whitelist, body size, JSON/envelope validation


async def rate_limit(ctx: RequestContext) -> None:
    return None  # Week 2: token bucket per IP


async def validate_certificate(ctx: RequestContext) -> None:
    return None  # Week 3: X.509 check against Team 1 Root CA + CRL


async def decrypt_envelope(ctx: RequestContext) -> None:
    return None  # Week 3: AES-256-GCM via Team 2 helpers; tag failure -> Drop(400, tampering)


async def replay_check(ctx: RequestContext) -> None:
    return None  # Week 3: timestamp window + IV/sequence tracking


async def authorize(ctx: RequestContext) -> None:
    return None  # Week 3: RS256 JWT verify + RBAC/Biba via Team 3


PIPELINE: list = [
    sanity_check,
    rate_limit,
    validate_certificate,
    decrypt_envelope,
    replay_check,
    authorize,
]


async def run_pipeline(ctx: RequestContext) -> None:
    for stage in PIPELINE:
        await stage(ctx)
