"""Loads gateway configuration: routing table (routes.yaml) and firewall rules (firewall.yaml)."""
import os
from dataclasses import dataclass, field, fields
import yaml


@dataclass
class RateLimitConfig:
    enabled: bool = True
    capacity: int = 20
    refill_per_second: float = 5.0
    violations_before_ban: int = 10
    violation_window_seconds: float = 60
    ban_seconds: float = 60
    cleanup_interval_seconds: float = 60
    stale_after_seconds: float = 300


@dataclass
class SanityConfig:
    allowed_methods: list = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE"])
    max_body_bytes: int = 1_048_576
    max_path_length: int = 2048
    max_headers: int = 100
    max_header_value_length: int = 8192
    require_json_content_type: bool = True
    allowed_content_types: list = field(default_factory=lambda: ["application/json"])


@dataclass
class EnvelopeConfig:
    enforce: bool = False
    required_fields: list = field(
        default_factory=lambda: ["client_id", "iv", "payload", "auth_tag", "timestamp"])
    iv_hex_length: int = 24
    tag_hex_length: int = 32
    max_client_id_length: int = 128


@dataclass
class Settings:
    routes: dict = field(default_factory=dict)
    upstream_timeout: float = 10.0
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    sanity: SanityConfig = field(default_factory=SanityConfig)
    envelope: EnvelopeConfig = field(default_factory=EnvelopeConfig)

    def match_route(self, path: str):
        """Return (prefix, upstream_url) for the longest matching prefix, else None."""
        best = None
        for prefix, upstream in self.routes.items():
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                if best is None or len(prefix) > len(best[0]):
                    best = (prefix, upstream)
        return best


def _build(cls, data: dict):
    """Create a dataclass from a dict, ignoring unknown keys."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in names})


def _read_yaml(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings() -> Settings:
    routes_path = os.getenv("ROUTES_FILE", "config/routes.yaml")
    firewall_path = os.getenv(
        "FIREWALL_FILE", os.path.join(os.path.dirname(routes_path), "firewall.yaml"))
    routes_data = _read_yaml(routes_path)
    fw = _read_yaml(firewall_path)
    return Settings(
        routes=routes_data.get("routes", {}),
        upstream_timeout=float(routes_data.get("gateway", {}).get("upstream_timeout_seconds", 10)),
        rate_limit=_build(RateLimitConfig, fw.get("rate_limit")),
        sanity=_build(SanityConfig, fw.get("sanity")),
        envelope=_build(EnvelopeConfig, fw.get("envelope")),
    )


settings = load_settings()
