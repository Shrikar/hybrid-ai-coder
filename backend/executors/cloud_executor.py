from __future__ import annotations

from typing import Any, Optional

from dotenv import load_dotenv

from backend.executors.base_executor import BaseExecutor
from backend.executors.provider_adapters import build_cloud_adapter
from backend.models.task_models import ExecutorResult, TokenUsage, ValidationSummary


class CloudExecutor(BaseExecutor):
    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        load_dotenv()
        load_dotenv(".env")
        load_dotenv("../.env")
        self.adapter = build_cloud_adapter(self.config)

    async def execute(self, prompt: str, context: Optional[dict[str, Any]] = None) -> ExecutorResult:
        try:
            data = await self.adapter.execute(prompt=prompt, context=context)
            if data.get("error"):
                return ExecutorResult(
                    error=data["error"],
                    validationSummary=ValidationSummary(passed=False, checksRun=["cloud_call"], failedChecks=["cloud_call"]),
                )

            return ExecutorResult(
                result=(data.get("text") or "").strip(),
                changedFiles=[],
                tokenUsage=TokenUsage(
                    promptTokens=int(data.get("prompt_tokens", 0) or 0),
                    completionTokens=int(data.get("completion_tokens", 0) or 0),
                    totalTokens=int(data.get("total_tokens", 0) or 0),
                    costUsd=float(data.get("cost_usd", 0.0) or 0.0),
                ),
                validationSummary=ValidationSummary(passed=True, checksRun=["cloud_call"]),
            )
        except Exception as exc:  # noqa: BLE001
            return ExecutorResult(
                error=f"Cloud execution failed: {exc}",
                changedFiles=[],
                validationSummary=ValidationSummary(passed=False, checksRun=["cloud_call"], failedChecks=["cloud_call"]),
            )
