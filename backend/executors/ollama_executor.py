from __future__ import annotations

from typing import Any, Optional

import httpx

from backend.executors.base_executor import BaseExecutor
from backend.models.task_models import ExecutorResult, ValidationSummary


class OllamaExecutor(BaseExecutor):
    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get("base_url", "http://localhost:11434")
        self.model = self.config.get("model", "qwen3-coder")
        self.timeout = float(self.config.get("timeout", 90))
        self._vision_capable_cache: Optional[bool] = None

    async def execute(self, prompt: str, context: Optional[dict[str, Any]] = None) -> ExecutorResult:
        context = context or {}
        attachments = context.get("attachments") or []
        text_attachments = [a for a in attachments if str(a.get("type", "")).lower() == "text"]
        image_attachments = [a for a in attachments if str(a.get("type", "")).lower() == "image"]

        context_no_attachments = dict(context)
        context_no_attachments.pop("attachments", None)

        full_prompt = prompt
        if context_no_attachments:
            full_prompt = f"{prompt}\n\nExecution context:\n{context_no_attachments}"
        if text_attachments:
            full_prompt += "\n\nAttached text files:\n" + self._format_text_attachments(text_attachments)

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if image_attachments:
                    supports_vision = await self._supports_vision(client)
                    if supports_vision:
                        payload["images"] = [a.get("imageBase64", "") for a in image_attachments if a.get("imageBase64")]
                    else:
                        full_prompt += (
                            "\n\nNote: image attachments were provided but local model does not support vision. "
                            "Proceed without image analysis."
                        )
                        payload["prompt"] = full_prompt
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                return ExecutorResult(
                    result=data.get("response", "").strip(),
                    changedFiles=[],
                    validationSummary=ValidationSummary(passed=True, checksRun=["ollama_call"]),
                )
        except Exception as exc:  # noqa: BLE001
            return ExecutorResult(
                error=f"Ollama execution failed: {exc}",
                changedFiles=[],
                validationSummary=ValidationSummary(passed=False, checksRun=["ollama_call"], failedChecks=["ollama_call"]),
            )

    async def _supports_vision(self, client: httpx.AsyncClient) -> bool:
        if self._vision_capable_cache is not None:
            return self._vision_capable_cache

        if "supports_vision" in self.config:
            self._vision_capable_cache = bool(self.config.get("supports_vision"))
            return self._vision_capable_cache

        try:
            res = await client.post(f"{self.base_url}/api/show", json={"model": self.model})
            res.raise_for_status()
            data = res.json()
            caps = [str(c).lower() for c in data.get("capabilities", [])]
            self._vision_capable_cache = "vision" in caps
        except Exception:
            self._vision_capable_cache = False
        return self._vision_capable_cache

    async def supports_vision(self) -> bool:
        if self._vision_capable_cache is not None:
            return self._vision_capable_cache
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await self._supports_vision(client)
        except Exception:
            self._vision_capable_cache = False
            return False

    @staticmethod
    def _format_text_attachments(items: list[dict[str, Any]]) -> str:
        blocks = []
        for it in items:
            name = it.get("filename", "attachment.txt")
            text = it.get("text", "")
            blocks.append(f"--- {name} ---\n{text}")
        return "\n".join(blocks)
