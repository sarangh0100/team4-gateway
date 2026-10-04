"""Loads gateway configuration (routing table + settings) from YAML."""
import os
from dataclasses import dataclass, field
import yaml


@dataclass
class Settings:
    routes: dict = field(default_factory=dict)
    upstream_timeout: float = 10.0

    def match_route(self, path: str):
        """Return (prefix, upstream_url) for the longest matching prefix, else None."""
        best = None
        for prefix, upstream in self.routes.items():
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                if best is None or len(prefix) > len(best[0]):
                    best = (prefix, upstream)
        return best


def load_settings() -> Settings:
    path = os.getenv("ROUTES_FILE", "config/routes.yaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Settings(
        routes=data.get("routes", {}),
        upstream_timeout=float(data.get("gateway", {}).get("upstream_timeout_seconds", 10)),
    )
