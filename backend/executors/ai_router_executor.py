from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class RouterDecision:
    model: str
    confidence: float
    reason: str
    complexity: int


class AIRouterExecutor:
    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        cfg = config or {}
        self.base_url = cfg.get("base_url", "http://localhost:11434")
        self.model = cfg.get("model", "qwen3-coder")
        self.timeout = float(cfg.get("timeout", 30))
        self.enabled = bool(cfg.get("enabled", True))

    async def decide(
        self,
        prompt: str,
        mode: str,
        risk_hints: list[str],
        retry_count: int,
        gpt_calls_used: int,
    ) -> RouterDecision:
        if not self.enabled:
            raise RuntimeError("ai_router_disabled")

        system = (
            "You are a task router. Decide if a coding task should use local or gpt model. "
            "Return only strict JSON with keys: model, confidence, reason, complexity. "
            "model must be local or gpt. confidence is 0..1, complexity is 0..100."
        )
        user = {
            "prompt": prompt,
            "mode": mode,
            "riskHints": risk_hints,
            "retryCount": retry_count,
            "gptCallsUsed": gpt_calls_used,
            "policy": "Prefer local unless task is clearly high-complexity/high-risk.",
        }
        payload = {
            "model": self.model,
            "prompt": f"{system}\n\nInput:\n{json.dumps(user, ensure_ascii=True)}",
            "stream": False,
            "options": {"temperature": 0},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
        raw = (data.get("response", "") or "").strip()
        parsed = json.loads(raw)
        model = str(parsed.get("model", "local")).strip().lower()
        if model not in {"local", "gpt"}:
            model = "local"
        confidence = float(parsed.get("confidence", 0.5))
        confidence = min(1.0, max(0.0, confidence))
        reason = str(parsed.get("reason", "ai_router_decision")).strip() or "ai_router_decision"
        complexity = int(parsed.get("complexity", 50))
        complexity = min(100, max(0, complexity))
        return RouterDecision(model=model, confidence=confidence, reason=reason, complexity=complexity)
