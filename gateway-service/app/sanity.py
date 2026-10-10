"""Stateless payload sanity checks: method, path, headers, size, content type, JSON, envelope."""
import json
import re

from .pipeline_types import Drop

_HEX = re.compile(r"[0-9a-fA-F]+")
# Any of these in the raw or decoded path is treated as a traversal / smuggling attempt.
_BAD_PATH_PATTERNS = ("..", "%2e", "%00", "%5c", "\\", "\x00")


def validate_envelope(data, cfg) -> None:
    """Check the encrypted-envelope structure. Does NOT decrypt (that is Week 3)."""
    def bad(msg):
        raise Drop(400, f"Malformed envelope: {msg}", "malformed_envelope")

    if not isinstance(data, dict):
        bad("body must be a JSON object")
    missing = [f for f in cfg.required_fields if f not in data]
    if missing:
        bad("missing fields " + ", ".join(missing))

    cid = data["client_id"]
    if not isinstance(cid, str) or not cid or len(cid) > cfg.max_client_id_length:
        bad("invalid client_id")
    for name, length in (("iv", cfg.iv_hex_length), ("auth_tag", cfg.tag_hex_length)):
        v = data[name]
        if not isinstance(v, str) or len(v) != length or not _HEX.fullmatch(v):
            bad(f"{name} must be {length} hex characters")
    p = data["payload"]
    if not isinstance(p, str) or not p or len(p) % 2 or not _HEX.fullmatch(p):
        bad("payload must be non-empty even-length hex")
    ts = data["timestamp"]
    if isinstance(ts, bool) or not isinstance(ts, int) or ts <= 0:
        bad("timestamp must be a positive integer")


def check_request(ctx, san, env) -> None:
    # 1. Method whitelist
    if ctx.method.upper() not in {m.upper() for m in san.allowed_methods}:
        raise Drop(405, f"Method {ctx.method} not allowed", "method_not_allowed",
                   headers={"Allow": ", ".join(san.allowed_methods)})

    # 2. Path checks
    if len(ctx.path) > san.max_path_length:
        raise Drop(414, "URI too long", "uri_too_long")
    for candidate in (ctx.path.lower(), (ctx.raw_path or "").lower()):
        if any(p in candidate for p in _BAD_PATH_PATTERNS):
            raise Drop(400, "Illegal path", "path_traversal")

    # 3. Header sanity
    if len(ctx.headers) > san.max_headers:
        raise Drop(431, "Too many headers", "bad_headers")
    if any(len(v) > san.max_header_value_length for v in ctx.headers.values()):
        raise Drop(431, "Header value too large", "bad_headers")

    # 4. Body size (the body was read with a hard cap in main.py)
    if ctx.body_too_large:
        raise Drop(413, "Payload too large", "payload_too_large")

    # 5. Content-Type and JSON validity (only when there is a body)
    if ctx.body:
        if san.require_json_content_type:
            ctype = ctx.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype not in {c.lower() for c in san.allowed_content_types}:
                raise Drop(415, "Unsupported Content-Type", "unsupported_media_type")
        try:
            ctx.extra["json"] = json.loads(ctx.body)
        except (ValueError, RecursionError):
            raise Drop(400, "Malformed JSON", "malformed_json")

    # 6. Envelope structure (switched on in Week 3)
    if env.enforce and ctx.method.upper() in ("POST", "PUT"):
        if not ctx.body:
            raise Drop(400, "Malformed envelope: empty body", "malformed_envelope")
        validate_envelope(ctx.extra["json"], env)
