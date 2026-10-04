"""Forwards an approved request to the internal service and returns its response."""
import httpx

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


def _clean(headers: dict) -> dict:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


async def forward(client: httpx.AsyncClient, ctx, query: str) -> httpx.Response:
    url = ctx.upstream_url.rstrip("/") + ctx.path
    if query:
        url += "?" + query
    headers = _clean(ctx.headers)
    headers["X-Forwarded-For"] = ctx.client_ip
    headers["X-Request-ID"] = ctx.request_id
    return await client.request(ctx.method, url, headers=headers, content=ctx.body)
