from __future__ import annotations

import os
from typing import Any, Optional

import httpx


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _calc_cost_usd(prompt_tokens: int, completion_tokens: int, pricing: dict[str, Any]) -> float:
    in_1k = float(pricing.get("input_per_1k_usd", 0.0) or 0.0)
    out_1k = float(pricing.get("output_per_1k_usd", 0.0) or 0.0)
    cost = (prompt_tokens / 1000.0) * in_1k + (completion_tokens / 1000.0) * out_1k
    return round(cost, 6)


class CloudProviderAdapter:
    async def execute(self, prompt: str, context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        raise NotImplementedError


class OpenAIAdapter(CloudProviderAdapter):
    def __init__(self, config: dict[str, Any]):
        self.api_key = os.getenv(config.get("api_key_env", "OPENAI_API_KEY"), "")
        self.model = os.getenv("OPENAI_MODEL", config.get("model", "gpt-5.3-codex"))
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.timeout = float(config.get("timeout", 90))
        self.pricing = config.get(
            "pricing",
            {"input_per_1k_usd": 0.005, "output_per_1k_usd": 0.015},
        )

    async def execute(self, prompt: str, context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if not self.api_key:
            return {"error": "OPENAI_API_KEY is not set"}

        payload = {"model": self.model, "input": self._build_input(prompt, context)}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/responses", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage") or {}
            prompt_tokens = _to_int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
            completion = _to_int(usage.get("output_tokens", usage.get("completion_tokens", 0)))
            total = _to_int(usage.get("total_tokens", prompt_tokens + completion))
            cost = _calc_cost_usd(prompt_tokens, completion, self.pricing)
            return {
                "text": (data.get("output_text") or "").strip(),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion,
                "total_tokens": total,
                "cost_usd": cost,
            }

    @staticmethod
    def _build_input(prompt: str, context: Optional[dict[str, Any]]) -> Any:
        if not context:
            return prompt

        attachments = context.get("attachments") or []
        image_items = [a for a in attachments if str(a.get("type", "")).lower() == "image" and a.get("imageBase64")]

        ctx = dict(context)
        ctx.pop("attachments", None)
        input_text = f"{prompt}\n\nContext:\n{ctx}" if ctx else prompt
        if not image_items:
            return input_text

        content = [{"type": "input_text", "text": input_text}]
        for item in image_items[:5]:
            mime = item.get("contentType") or "image/png"
            b64 = item.get("imageBase64", "")
            content.append({"type": "input_image", "image_url": f"data:{mime};base64,{b64}"})
        return [{"role": "user", "content": content}]


class AzureOpenAIAdapter(CloudProviderAdapter):
    def __init__(self, config: dict[str, Any]):
        self.endpoint = os.getenv(config.get("endpoint_env", "AZURE_OPENAI_ENDPOINT"), "")
        self.api_key = os.getenv(config.get("api_key_env", "AZURE_OPENAI_API_KEY"), "")
        self.deployment = config.get("deployment", "")
        self.api_version = config.get("api_version", "2024-10-21")
        self.timeout = float(config.get("timeout", 90))
        self.pricing = config.get(
            "pricing",
            {"input_per_1k_usd": 0.005, "output_per_1k_usd": 0.015},
        )

    async def execute(self, prompt: str, context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if not self.endpoint or not self.api_key or not self.deployment:
            return {"error": "Azure OpenAI config is incomplete"}

        input_text = prompt if not context else f"{prompt}\n\nContext:\n{context}"
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/responses?api-version={self.api_version}"
        headers = {"api-key": self.api_key, "Content-Type": "application/json"}
        payload = {"input": input_text}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage") or {}
            prompt_tokens = _to_int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
            completion_tokens = _to_int(usage.get("output_tokens", usage.get("completion_tokens", 0)))
            total_tokens = _to_int(usage.get("total_tokens", prompt_tokens + completion_tokens))
            return {
                "text": (data.get("output_text") or "").strip(),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": _calc_cost_usd(prompt_tokens, completion_tokens, self.pricing),
            }


class AnthropicAdapter(CloudProviderAdapter):
    def __init__(self, config: dict[str, Any]):
        self.api_key = os.getenv(config.get("api_key_env", "ANTHROPIC_API_KEY"), "")
        self.model = config.get("model", "claude-3-7-sonnet-latest")
        self.base_url = config.get("base_url", "https://api.anthropic.com")
        self.timeout = float(config.get("timeout", 90))
        self.pricing = config.get(
            "pricing",
            {"input_per_1k_usd": 0.003, "output_per_1k_usd": 0.015},
        )

    async def execute(self, prompt: str, context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if not self.api_key:
            return {"error": "ANTHROPIC_API_KEY is not set"}

        input_text = prompt if not context else f"{prompt}\n\nContext:\n{context}"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {"model": self.model, "max_tokens": 2000, "messages": [{"role": "user", "content": input_text}]}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/v1/messages", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            text = ""
            for item in data.get("content", []):
                if item.get("type") == "text":
                    text += item.get("text", "")
            usage = data.get("usage") or {}
            prompt_tokens = _to_int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
            completion_tokens = _to_int(usage.get("output_tokens", usage.get("completion_tokens", 0)))
            total_tokens = _to_int(usage.get("total_tokens", prompt_tokens + completion_tokens))
            return {
                "text": text.strip(),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": _calc_cost_usd(prompt_tokens, completion_tokens, self.pricing),
            }


class GitHubCopilotAdapter(CloudProviderAdapter):
    async def execute(self, prompt: str, context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return {"error": "GitHub Copilot adapter is not available in local runtime yet"}


def build_cloud_adapter(config: dict[str, Any]) -> CloudProviderAdapter:
    provider = (config.get("provider") or "openai").lower()
    if provider == "azure_openai":
        return AzureOpenAIAdapter(config)
    if provider == "anthropic":
        return AnthropicAdapter(config)
    if provider == "github_copilot":
        return GitHubCopilotAdapter()
    return OpenAIAdapter(config)
