from __future__ import annotations

import os
from typing import Any

import httpx


class StartupDiagnostics:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def run(self) -> dict[str, Any]:
        providers = self.config.get("providers", {})
        active = self.config.get("active", {})
        local_name = active.get("local_provider", "ollama")
        cloud_name = active.get("cloud_provider", "openai")

        local_cfg = providers.get(local_name, {})
        cloud_cfg = providers.get(cloud_name, {})

        checks: dict[str, Any] = {
            "local_provider": local_name,
            "cloud_provider": cloud_name,
            "ollama_reachable": None,
            "cloud_key_present": None,
            "warnings": [],
        }

        if local_name == "ollama":
            base_url = local_cfg.get("base_url", "http://localhost:11434")
            try:
                r = httpx.get(f"{base_url}/api/tags", timeout=3.0)
                checks["ollama_reachable"] = r.status_code == 200
                if r.status_code != 200:
                    checks["warnings"].append(f"Ollama tags check returned status {r.status_code}")
            except Exception:
                checks["ollama_reachable"] = False
                checks["warnings"].append("Ollama is not reachable")

        if cloud_name in {"openai", "azure_openai", "anthropic"}:
            key_env = cloud_cfg.get("api_key_env", "OPENAI_API_KEY")
            checks["cloud_key_present"] = bool(os.getenv(key_env))
            if not checks["cloud_key_present"]:
                checks["warnings"].append(f"Missing cloud API key env: {key_env}")

        checks["ready"] = not any(w for w in checks["warnings"] if "Missing" not in w)
        return checks
