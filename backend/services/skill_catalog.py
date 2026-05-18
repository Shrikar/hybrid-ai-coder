from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.models.task_models import TaskCreateRequest, TaskMode


class SkillCatalog:
    def __init__(self, path: str | None = None):
        default = Path(__file__).resolve().parents[2] / "config" / "skills.json"
        self.path = Path(path) if path else default

    def list_skills(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text())

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        for skill in self.list_skills():
            if skill.get("id") == skill_id:
                return skill
        return None

    def build_task_request(self, skill_id: str, repo_path: str, user_input: str = "") -> TaskCreateRequest:
        skill = self.get_skill(skill_id)
        if not skill:
            raise ValueError(f"Unknown skill: {skill_id}")

        allowed = ", ".join(skill.get("allowed_paths", []))
        base = skill.get("template", "").format(allowed_paths=allowed)
        prompt = base if not user_input else f"{base}\n\nAdditional user input:\n{user_input}"

        mode_str = (skill.get("preferred_mode") or "auto").lower()
        mode = TaskMode.auto
        if mode_str == "local":
            mode = TaskMode.local
        elif mode_str in {"gpt", "cloud"}:
            mode = TaskMode.cloud

        return TaskCreateRequest(prompt=prompt, repoPath=repo_path, mode=mode)
