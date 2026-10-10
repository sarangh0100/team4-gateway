"""Shared types for the pipeline (kept separate to avoid circular imports)."""
from dataclasses import dataclass, field
from typing import Optional


class Drop(Exception):
    """Raised by a stage to block the request."""

    def __init__(self, status_code: int, reason: str, event_type: str, headers: Optional[dict] = None):
        self.status_code = status_code
        self.reason = reason
        self.event_type = event_type
        self.headers = headers
        super().__init__(reason)


@dataclass
class RequestContext:
    method: str
    path: str
    headers: dict
    body: bytes
    client_ip: str
    request_id: str
    raw_path: str = ""
    body_too_large: bool = False
    route_prefix: Optional[str] = None
    upstream_url: Optional[str] = None
    client_id: Optional[str] = None      # filled by decrypt stage (Week 3)
    claims: Optional[dict] = None        # filled by authorize stage (Week 3)
    extra: dict = field(default_factory=dict)
