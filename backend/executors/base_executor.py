from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from backend.models.task_models import ExecutorResult


class BaseExecutor(ABC):
    def __init__(self, config: Optional[dict[str, Any]] = None):
        self.config = config or {}
        self.provider = self.config.get("provider", "unknown")
        self.model = self.config.get("model", "unknown")

    @abstractmethod
    async def execute(self, prompt: str, context: Optional[dict[str, Any]] = None) -> ExecutorResult:
        raise NotImplementedError
