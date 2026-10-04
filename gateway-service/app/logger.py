"""Structured JSON security-event logger. Expanded in Weeks 2-3 (severity, buffer, streaming)."""
import json
import logging
import os
import sys
from datetime import datetime, timezone

_logger = logging.getLogger("gateway.events")
if not _logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    _logger.propagate = False

# In-memory buffer so Week 3 can expose recent events to Team 5.
EVENT_BUFFER: list = []
BUFFER_MAX = 1000


def log_event(event_type: str, source_ip: str, action: str, reason: str = "",
              status_code: int = 0, **extra) -> dict:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "source_ip": source_ip,
        "action": action,          # "allowed" | "dropped"
        "reason": reason,
        "status_code": status_code,
        **extra,
    }
    EVENT_BUFFER.append(event)
    if len(EVENT_BUFFER) > BUFFER_MAX:
        del EVENT_BUFFER[0]
    _logger.info(json.dumps(event))
    return event
