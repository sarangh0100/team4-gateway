"""Send malformed / hostile requests and show how the gateway reacts.

Usage (from project root):
    python scripts/bad_requests.py
    python scripts/bad_requests.py --host localhost --port 8080

Sends fewer than 20 requests, so it stays inside the default rate limit.
Each case prints the status code you EXPECT and the one you GOT.
"""
import argparse
import socket

import httpx


def raw_get(host, port, path):
    """Send a raw HTTP request so the client cannot 'clean up' the path for us."""
    with socket.create_connection((host, port), timeout=5) as s:
        s.sendall(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
        data = s.recv(4096).decode(errors="replace")
    return int(data.split(" ", 2)[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    base = f"http://{args.host}:{args.port}"
    json_h = {"content-type": "application/json"}

    cases = [
        ("Normal GET (control)", 200, lambda: httpx.get(f"{base}/api/records").status_code),
        ("Disallowed method PATCH", 405, lambda: httpx.request("PATCH", f"{base}/api/records").status_code),
        ("Disallowed method TRACE", 405, lambda: httpx.request("TRACE", f"{base}/api/records").status_code),
        ("Oversized body (2 MB)", 413,
         lambda: httpx.post(f"{base}/api/records", content=b'{"a":"' + b"A" * 2_000_000 + b'"}',
                            headers=json_h).status_code),
        ("Wrong Content-Type", 415,
         lambda: httpx.post(f"{base}/api/records", content=b"patient=Eve",
                            headers={"content-type": "text/plain"}).status_code),
        ("Malformed JSON", 400,
         lambda: httpx.post(f"{base}/api/records", content=b'{"patient": ', headers=json_h).status_code),
        ("Path traversal ../", 400, lambda: raw_get(args.host, args.port, "/api/records/../../etc/passwd")),
        ("Encoded traversal %2e%2e", 400, lambda: raw_get(args.host, args.port, "/api/records/%2e%2e/secret")),
        ("Unknown route", 404, lambda: httpx.get(f"{base}/admin").status_code),
    ]

    print(f"{'Test':32} {'Expected':>8} {'Got':>6}  Result")
    print("-" * 60)
    for name, expected, fn in cases:
        try:
            got = fn()
        except Exception as e:                       # noqa: BLE001
            got = type(e).__name__
        print(f"{name:32} {expected:>8} {str(got):>6}  {'OK' if got == expected else 'CHECK'}")
    print(f"\nSee the gateway's view: {base}/gateway/logs and {base}/gateway/stats")


if __name__ == "__main__":
    main()
