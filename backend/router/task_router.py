from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.executors.ai_router_executor import AIRouterExecutor
from backend.models.task_models import TaskMode


@dataclass
class BudgetPolicy:
    maxGptCalls: int = 2
    maxContextFiles: int = 12
    maxPromptTokens: int = 2500


@dataclass
class RouteDecision:
    model: str
    reason: str
    confidence: float
    complexityScore: int
    budgetPolicy: BudgetPolicy


class TaskRouter:
    HIGH_RISK_KEYWORDS = {
        "architecture",
        "security",
        "distributed",
        "concurrency",
        "migration",
        "kafka",
        "transaction",
        "lld",
        "hld",
    }
    LOCAL_HINTS = {
        "crud",
        "dto",
        "boilerplate",
        "create class",
        "create method",
        "rename",
        "add field",
        "unit test",
    }

    def __init__(
        self,
        complexity_threshold: int = 50,
        local_retry_limit: int = 2,
        ai_executor: Optional[AIRouterExecutor] = None,
        ai_confidence_threshold: float = 0.55,
    ):
        self.complexity_threshold = complexity_threshold
        self.local_retry_limit = local_retry_limit
        self.ai_executor = ai_executor
        self.ai_confidence_threshold = ai_confidence_threshold

    async def route(
        self,
        prompt: str,
        mode: TaskMode,
        riskHints: Optional[list[str]] = None,
        retryCount: int = 0,
        gptCallsUsed: int = 0,
    ) -> RouteDecision:
        budget = self.budget_policy()

        if mode == TaskMode.gpt:
            return RouteDecision("gpt", "explicit_mode_gpt", 1.0, 100, budget)
        if mode == TaskMode.local:
            return RouteDecision("local", "explicit_mode_local", 1.0, 0, budget)

        hints = riskHints or []
        score = self._complexity_score(prompt, hints)
        high_risk = self._is_high_risk(prompt, hints)

        if gptCallsUsed >= budget.maxGptCalls:
            return RouteDecision("local", "gpt_budget_exhausted", 1.0, score, budget)

        if retryCount >= self.local_retry_limit:
            return RouteDecision("gpt", "local_retry_limit_exceeded", 1.0, score, budget)

        ai_decision = await self._route_with_ai(prompt, mode, hints, retryCount, gptCallsUsed)
        if ai_decision is not None:
            if ai_decision.model == "gpt" and high_risk and score < self.complexity_threshold:
                # Keep local-first when risk-only mention is weak.
                return RouteDecision("local", "ai_low_complexity_local_guard", ai_decision.confidence, score, budget)
            return RouteDecision(
                ai_decision.model,
                f"ai_router:{ai_decision.reason}",
                ai_decision.confidence,
                ai_decision.complexity,
                budget,
            )

        if high_risk and score >= self.complexity_threshold:
            return RouteDecision("gpt", "high_risk_and_high_complexity", 0.75, score, budget)

        return RouteDecision("local", "local_first_default", 0.65, score, budget)

    def budget_policy(self) -> BudgetPolicy:
        return BudgetPolicy()

    def _complexity_score(self, prompt: str, risk_hints: list[str]) -> int:
        text = prompt.lower()
        score = min(len(text) // 20, 35)
        score += sum(10 for kw in self.HIGH_RISK_KEYWORDS if kw in text)
        score += sum(8 for hint in risk_hints if hint.lower() in self.HIGH_RISK_KEYWORDS)

        if any(kw in text for kw in self.LOCAL_HINTS):
            score -= 15

        return max(0, min(score, 100))

    def _is_high_risk(self, prompt: str, risk_hints: list[str]) -> bool:
        text = prompt.lower()
        return any(kw in text for kw in self.HIGH_RISK_KEYWORDS) or any(
            hint.lower() in self.HIGH_RISK_KEYWORDS for hint in risk_hints
        )

    async def _route_with_ai(
        self,
        prompt: str,
        mode: TaskMode,
        risk_hints: list[str],
        retry_count: int,
        gpt_calls_used: int,
    ):
        if self.ai_executor is None:
            return None
        try:
            decision = await self.ai_executor.decide(
                prompt=prompt,
                mode=mode.value,
                risk_hints=risk_hints,
                retry_count=retry_count,
                gpt_calls_used=gpt_calls_used,
            )
            if decision.confidence < self.ai_confidence_threshold:
                return None
            return decision
        except Exception:
            return None
