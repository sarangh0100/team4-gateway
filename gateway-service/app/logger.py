"""Structured JSON security-event logger with severity levels, a ring buffer, and counters."""
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone

_logger = logging.getLogger("gateway.events")
if not _logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    _logger.propagate = False

# Severity per event type: info < low < medium < high < critical
SEVERITY = {
    "request_allowed": "info",
    "no_route": "low",
    "method_not_allowed": "low",
    "uri_too_long": "low",
    "bad_headers": "low",
    "unsupported_media_type": "low",
    "malformed_json": "low",
    "malformed_envelope": "medium",
    "payload_too_large": "medium",
    "rate_limited": "medium",
    "upstream_error": "medium",
    "path_traversal": "high",
    "ip_banned": "high",
    # Week 3 will add: invalid_certificate, tampering_detected, replay_detected,
    # invalid_token, access_denied
}

EVENT_BUFFER: list = []
BUFFER_MAX = 1000
STATS = {"total": 0, "allowed": 0, "dropped": 0, "by_event_type": Counter()}


def reset_state() -> None:
    """Clear buffer and counters (used by tests)."""
    EVENT_BUFFER.clear()
    STATS.update(total=0, allowed=0, dropped=0, by_event_type=Counter())


def get_stats() -> dict:
    return {
        "total": STATS["total"],
        "allowed": STATS["allowed"],
        "dropped": STATS["dropped"],
        "by_event_type": dict(STATS["by_event_type"]),
    }


def log_event(event_type: str, source_ip: str, action: str, reason: str = "",
              status_code: int = 0, *, request_id=None, client_id=None,
              method=None, path=None, payload_size: int = 0, **extra) -> dict:
    """Emit one JSON event. Every event has the same core fields so Team 5 can rely on them."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "severity": SEVERITY.get(event_type, "medium"),
        "source_ip": source_ip,
        "client_id": client_id,
        "action": action,                      # "allowed" | "dropped"
        "reason": reason,
        "status_code": status_code,
        "request_id": request_id,
        "method": method,
        "path": (path or "")[:200],
        "payload_size": payload_size,
        **extra,
    }
    EVENT_BUFFER.append(event)
    if len(EVENT_BUFFER) > BUFFER_MAX:
        del EVENT_BUFFER[0]
    STATS["total"] += 1
    STATS["allowed" if action == "allowed" else "dropped"] += 1
    STATS["by_event_type"][event_type] += 1
    _logger.info(json.dumps(event))
    return event
