from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigLoader:
    def __init__(self, config_path: str | None = None) -> None:
        default_path = Path(__file__).resolve().parents[2] / "config" / "config.json"
        self.config_path = Path(config_path) if config_path else default_path

    def load(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        return json.loads(self.config_path.read_text())

    def resolve_active_models(self) -> dict[str, Any]:
        cfg = self.load()
        active = cfg.get("active", {})
        providers = cfg.get("providers", {})

        cloud_name = active.get("cloud_provider", "openai")
        local_name = active.get("local_provider", "ollama")

        cloud = providers.get(cloud_name, {})
        local = providers.get(local_name, {})
        routing = cfg.get("routing", {})

        return {
            "cloud": cloud,
            "local": local,
            "routing": routing,
            "cloud_name": cloud_name,
            "local_name": local_name,
        }
