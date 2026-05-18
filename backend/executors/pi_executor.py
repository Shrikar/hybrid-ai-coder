from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, Optional

from backend.executors.base_executor import BaseExecutor
from backend.models.task_models import ExecutorResult, ValidationSummary


class PiExecutor(BaseExecutor):
    def __init__(self, config: Optional[dict[str, Any]] = None):
        super().__init__(config)
        self.command = str(self.config.get("command", "pi"))
        self.timeout = float(self.config.get("timeout", 120))
        self.provider = self.config.get("provider")
        self.model = self.config.get("model")
        self.allow_npx_fallback = bool(self.config.get("allow_npx_fallback", True))
        self.npm_package = str(self.config.get("npm_package", "@earendil-works/pi-coding-agent"))
        bridge_default = Path(__file__).resolve().parents[1] / "node_bridge" / "pi_bridge.mjs"
        bridge_cfg = self.config.get("bridge_script")
        self.bridge_script = str(bridge_cfg).strip() if bridge_cfg else str(bridge_default)
        self.prefer_embedded_bridge = bool(self.config.get("prefer_embedded_bridge", True))

    async def execute(self, prompt: str, context: Optional[dict[str, Any]] = None) -> ExecutorResult:
        full_prompt = prompt
        if context:
            full_prompt = f"{prompt}\n\nExecution context:\n{context}"
        try_bridge = self.prefer_embedded_bridge and shutil.which("node") is not None and Path(self.bridge_script).exists()
        if try_bridge:
            bridge_result = await self._run_bridge(full_prompt)
            if bridge_result is not None:
                return bridge_result

        cmd = self._build_command(full_prompt)
        if cmd is None:
            return ExecutorResult(
                error=(
                    f"Pi execution failed: command not found: {self.command}. "
                    "Install pi or enable npx fallback with Node.js/npm."
                ),
                validationSummary=ValidationSummary(passed=False, checksRun=["pi_call"], failedChecks=["pi_call"]),
            )

    async def _run_bridge(self, full_prompt: str) -> Optional[ExecutorResult]:
        req = {"prompt": full_prompt}
        if self.provider:
            req["provider"] = self.provider
        if self.model:
            req["model"] = self.model
        cmd = ["node", self.bridge_script]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            payload = json.dumps(req).encode("utf-8")
            out, err = await asyncio.wait_for(proc.communicate(input=payload), timeout=self.timeout)
            if proc.returncode != 0:
                # Return None to try other fallbacks (direct pi / npx).
                return None
            raw = out.decode("utf-8", errors="replace").strip()
            data = json.loads(raw) if raw else {}
            if not data.get("ok"):
                return None
            return ExecutorResult(
                result=str(data.get("text", "")).strip(),
                validationSummary=ValidationSummary(passed=True, checksRun=["pi_bridge_call"]),
            )
        except Exception:
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            if proc.returncode != 0:
                message = (err.decode("utf-8", errors="replace") or out.decode("utf-8", errors="replace")).strip()
                return ExecutorResult(
                    error=f"Pi execution failed: {message or f'exit code {proc.returncode}'}",
                    validationSummary=ValidationSummary(passed=False, checksRun=["pi_call"], failedChecks=["pi_call"]),
                )
            return ExecutorResult(
                result=out.decode("utf-8", errors="replace").strip(),
                validationSummary=ValidationSummary(passed=True, checksRun=["pi_call"]),
            )
        except asyncio.TimeoutError:
            return ExecutorResult(
                error="Pi execution failed: timeout",
                validationSummary=ValidationSummary(passed=False, checksRun=["pi_call"], failedChecks=["pi_call"]),
            )
        except Exception as exc:  # noqa: BLE001
            return ExecutorResult(
                error=f"Pi execution failed: {exc}",
                validationSummary=ValidationSummary(passed=False, checksRun=["pi_call"], failedChecks=["pi_call"]),
            )

    def _build_command(self, full_prompt: str) -> Optional[list[str]]:
        if shutil.which(self.command) is not None:
            cmd = [self.command, "-p", full_prompt]
        elif self.allow_npx_fallback and shutil.which("npx") is not None:
            # Zero-install path: download and execute pi package on demand.
            cmd = ["npx", "-y", self.npm_package, "-p", full_prompt]
        else:
            return None

        if self.provider:
            cmd.extend(["--provider", str(self.provider)])
        if self.model:
            cmd.extend(["--model", str(self.model)])
        return cmd
