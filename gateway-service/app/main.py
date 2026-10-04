"""Team 4 - Inline Gateway entry point. Every request to internal services passes through here."""
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .config import load_settings
from .logger import EVENT_BUFFER, log_event
from .pipeline import Drop, RequestContext, run_pipeline
from .proxy import HOP_BY_HOP, forward

settings = load_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=settings.upstream_timeout)
    yield
    await app.state.http.aclose()


app = FastAPI(title="Team 4 Inline Gateway", lifespan=lifespan)


@app.get("/gateway/health")
async def health():
    return {"status": "ok", "service": "gateway-service", "routes": list(settings.routes)}


@app.get("/gateway/logs")
async def recent_logs(limit: int = 50):
    """Basic log view; becomes the streaming endpoint for Team 5 in Week 3."""
    return EVENT_BUFFER[-limit:]


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def gateway(full_path: str, request: Request):
    path = "/" + full_path
    client_ip = request.client.host if request.client else "unknown"
    ctx = RequestContext(
        method=request.method,
        path=path,
        headers=dict(request.headers),
        body=await request.body(),
        client_ip=client_ip,
        request_id=str(uuid.uuid4()),
    )

    # 1. Routing
    match = settings.match_route(path)
    if match is None:
        log_event("no_route", client_ip, "dropped", f"no route for {path}", 404,
                  request_id=ctx.request_id, method=ctx.method, path=path)
        return JSONResponse({"detail": "Not found"}, status_code=404)
    ctx.route_prefix, ctx.upstream_url = match

    # 2. Security pipeline (stubs in Week 1)
    try:
        await run_pipeline(ctx)
    except Drop as d:
        log_event(d.event_type, client_ip, "dropped", d.reason, d.status_code,
                  request_id=ctx.request_id, method=ctx.method, path=path)
        return JSONResponse({"detail": d.reason}, status_code=d.status_code)

    # 3. Forward to the internal service
    try:
        upstream = await forward(request.app.state.http, ctx, request.url.query)
    except httpx.HTTPError as exc:
        log_event("upstream_error", client_ip, "dropped", str(exc), 502,
                  request_id=ctx.request_id, method=ctx.method, path=path)
        return JSONResponse({"detail": "Bad gateway"}, status_code=502)

    # 4. Log + return
    log_event("request_allowed", client_ip, "allowed", "", upstream.status_code,
              request_id=ctx.request_id, method=ctx.method, path=path,
              payload_size=len(ctx.body), upstream=ctx.upstream_url)
    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_BY_HOP}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=resp_headers)
