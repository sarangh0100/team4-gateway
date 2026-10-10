"""Team 4 - Inline Gateway entry point. Every request to internal services passes through here."""
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .config import settings
from .logger import EVENT_BUFFER, get_stats, log_event
from .pipeline import Drop, RequestContext, run_pipeline
from .proxy import HOP_BY_HOP, forward

ALL_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=settings.upstream_timeout)
    yield
    await app.state.http.aclose()


app = FastAPI(title="Team 4 Inline Gateway", lifespan=lifespan)


async def read_body_limited(request: Request, limit: int):
    """Read the body but never more than `limit` bytes. Returns (body, too_large)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        return b"", True
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return b"", True
        chunks.append(chunk)
    return b"".join(chunks), False


@app.get("/gateway/health")
async def health():
    return {"status": "ok", "service": "gateway-service", "routes": list(settings.routes)}


@app.get("/gateway/logs")
async def recent_logs(limit: int = 50):
    """Recent security events. Becomes the streaming endpoint for Team 5 in Week 3."""
    return EVENT_BUFFER[-limit:]


@app.get("/gateway/stats")
async def stats():
    """Counters for the dashboard: total / allowed / dropped, and per event type."""
    return get_stats()


@app.api_route("/{full_path:path}", methods=ALL_METHODS)
async def gateway(full_path: str, request: Request):
    path = "/" + full_path
    client_ip = request.client.host if request.client else "unknown"
    body, too_large = await read_body_limited(request, settings.sanity.max_body_bytes)
    ctx = RequestContext(
        method=request.method,
        path=path,
        raw_path=request.scope.get("raw_path", b"").decode("latin-1"),
        headers=dict(request.headers),
        body=body,
        body_too_large=too_large,
        client_ip=client_ip,
        request_id=str(uuid.uuid4()),
    )
    common = dict(request_id=ctx.request_id, method=ctx.method, path=path)

    # Security pipeline: rate limit -> sanity -> routing -> (Week 3 stages)
    try:
        await run_pipeline(ctx)
    except Drop as d:
        log_event(d.event_type, client_ip, "dropped", d.reason, d.status_code,
                  client_id=ctx.client_id, payload_size=len(ctx.body), **common)
        return JSONResponse({"detail": d.reason}, status_code=d.status_code, headers=d.headers)

    # Forward to the internal service
    try:
        upstream = await forward(request.app.state.http, ctx, request.url.query)
    except httpx.HTTPError as exc:
        log_event("upstream_error", client_ip, "dropped", str(exc), 502,
                  client_id=ctx.client_id, payload_size=len(ctx.body), **common)
        return JSONResponse({"detail": "Bad gateway"}, status_code=502)

    log_event("request_allowed", client_ip, "allowed", "", upstream.status_code,
              client_id=ctx.client_id, payload_size=len(ctx.body),
              upstream=ctx.upstream_url, **common)
    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=resp_headers)
