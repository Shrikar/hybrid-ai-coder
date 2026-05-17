from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from backend.models.task_models import ValidationSummary


@dataclass
class ValidationConfig:
    commands: list[str]
    timeout_seconds: int = 180
    profiles: Optional[list[dict[str, Any]]] = None
    stop_on_failure: bool = True


class RepoValidator:
    def __init__(self, config: ValidationConfig):
        self.config = config

    def validate(self, repo_path: str) -> ValidationSummary:
        commands = self._resolve_commands(repo_path)
        if not commands:
            return ValidationSummary(passed=True, checksRun=["no_validation_configured"], failedChecks=[])

        checks_run: list[str] = []
        failed: list[str] = []

        for check_name, cmd, timeout_seconds in commands:
            checks_run.append(check_name)
            try:
                result = subprocess.run(
                    cmd,
                    cwd=repo_path,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
                if result.returncode != 0:
                    failed.append(f"{check_name} (exit={result.returncode})")
                    if self.config.stop_on_failure:
                        break
            except subprocess.TimeoutExpired:
                failed.append(f"{check_name} (timeout)")
                if self.config.stop_on_failure:
                    break
            except Exception:
                failed.append(f"{check_name} (exception)")
                if self.config.stop_on_failure:
                    break

        return ValidationSummary(
            passed=len(failed) == 0,
            checksRun=checks_run,
            failedChecks=failed,
        )

    def _resolve_commands(self, repo_path: str) -> list[tuple[str, str, int]]:
        resolved: list[tuple[str, str, int]] = []
        default_timeout = int(self.config.timeout_seconds)
        for cmd in self.config.commands:
            resolved.append((f"default:{cmd}", cmd, default_timeout))

        for profile in self.config.profiles or []:
            if self._profile_matches(profile, repo_path):
                name = str(profile.get("name", "profile"))
                timeout = int(profile.get("timeout_seconds", default_timeout))
                for cmd in profile.get("commands", []):
                    resolved.append((f"{name}:{cmd}", str(cmd), timeout))
        return resolved

    @staticmethod
    def _profile_matches(profile: dict[str, Any], repo_path: str) -> bool:
        repo = Path(repo_path)
        exists_any = profile.get("exists_any", [])
        exists_all = profile.get("exists_all", [])

        if exists_any:
            any_match = any((repo / p).exists() for p in exists_any)
            if not any_match:
                return False
        if exists_all:
            all_match = all((repo / p).exists() for p in exists_all)
            if not all_match:
                return False
        return True
