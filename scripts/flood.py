"""Flood the gateway to demonstrate rate limiting and IP bans.

Usage (from project root):
    python scripts/flood.py                       # 200 requests, 20 threads
    python scripts/flood.py --url http://localhost:8080/api/records --count 300

After a flood the gateway may ban your IP for ~60 s. Wait, or restart the gateway
container, before running normal requests again.
"""
import argparse
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8080/api/records")
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--threads", type=int, default=20)
    args = ap.parse_args()

    def hit(_):
        try:
            return httpx.get(args.url, timeout=5).status_code
        except httpx.HTTPError:
            return "error"

    print(f"Sending {args.count} requests to {args.url} with {args.threads} threads...")
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        results = list(pool.map(hit, range(args.count)))
    took = time.time() - start

    counts = Counter(results)
    print(f"Finished in {took:.2f}s ({args.count / took:.0f} req/s)\n")
    for code, n in sorted(counts.items(), key=lambda x: str(x[0])):
        label = {200: "allowed", 429: "blocked (rate limit / ban)"}.get(code, "")
        print(f"  HTTP {code}: {n:4d}  {label}")
    print("\nNow check the gateway:")
    print("  http://localhost:8080/gateway/stats")
    print("  http://localhost:8080/gateway/logs")


if __name__ == "__main__":
    main()
