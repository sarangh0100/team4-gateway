"""Token-bucket rate limiter with temporary IP bans (anti-DoS)."""
import time
from collections import deque, namedtuple
from dataclasses import dataclass

Decision = namedtuple("Decision", ["allowed", "kind", "retry_after"])
# kind: "ok" | "limited" | "banned"


@dataclass
class Bucket:
    tokens: float
    last_refill: float
    last_seen: float


class RateLimiter:
    def __init__(self, cfg, clock=time.monotonic):
        self.cfg = cfg
        self.clock = clock
        self.buckets: dict = {}      # key -> Bucket
        self.violations: dict = {}   # key -> deque of violation timestamps
        self.bans: dict = {}         # key -> ban expiry time
        self._last_cleanup = clock()

    def check(self, key: str) -> Decision:
        if not self.cfg.enabled:
            return Decision(True, "ok", 0)
        now = self.clock()
        self._maybe_cleanup(now)

        # 1. Is the key currently banned?
        until = self.bans.get(key)
        if until is not None:
            if now < until:
                return Decision(False, "banned", until - now)
            del self.bans[key]

        # 2. Refill the bucket based on elapsed time
        b = self.buckets.get(key)
        if b is None:
            b = Bucket(tokens=float(self.cfg.capacity), last_refill=now, last_seen=now)
            self.buckets[key] = b
        elapsed = now - b.last_refill
        b.tokens = min(self.cfg.capacity, b.tokens + elapsed * self.cfg.refill_per_second)
        b.last_refill = now
        b.last_seen = now

        # 3. Spend a token
        if b.tokens >= 1:
            b.tokens -= 1
            return Decision(True, "ok", 0)

        # 4. Empty bucket: record the violation, maybe ban
        v = self.violations.setdefault(key, deque())
        v.append(now)
        while v and now - v[0] > self.cfg.violation_window_seconds:
            v.popleft()
        if len(v) >= self.cfg.violations_before_ban:
            self.bans[key] = now + self.cfg.ban_seconds
            v.clear()
            return Decision(False, "banned", self.cfg.ban_seconds)

        wait = (1 - b.tokens) / self.cfg.refill_per_second if self.cfg.refill_per_second > 0 else 60
        return Decision(False, "limited", wait)

    def _maybe_cleanup(self, now: float) -> None:
        if now - self._last_cleanup < self.cfg.cleanup_interval_seconds:
            return
        self._last_cleanup = now
        stale = [k for k, b in self.buckets.items() if now - b.last_seen > self.cfg.stale_after_seconds]
        for k in stale:
            del self.buckets[k]
        for k in [k for k, u in self.bans.items() if u <= now]:
            del self.bans[k]
        for k in [k for k, v in self.violations.items()
                  if not v or now - v[-1] > self.cfg.violation_window_seconds]:
            del self.violations[k]
