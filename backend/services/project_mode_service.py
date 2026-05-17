from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from backend.models.task_models import TaskCreateRequest, TaskRecord
from backend.services.task_execution_service import TaskExecutionService


@dataclass
class ProjectQuestion:
    key: str
    label: str
    placeholder: str


class ProjectModeService:
    """Codex-style project flow: questions -> plan -> task list -> optional execution."""

    def __init__(
        self,
        task_service: TaskExecutionService,
        ai_config: dict[str, Any] | None = None,
    ) -> None:
        self.task_service = task_service
        cfg = ai_config or {}
        self.ai_enabled = bool(cfg.get("enabled", True))
        self.ai_base_url = str(cfg.get("base_url", "http://localhost:11434"))
        self.ai_model = str(cfg.get("model", "qwen3-coder"))
        self.ai_timeout = float(cfg.get("timeout", 20))

    async def discover(self, goal: str) -> list[ProjectQuestion]:
        ai_questions = await self._ai_discover_questions(goal)
        if ai_questions:
            return ai_questions

        # Keep this stable and local-first: fixed high-signal questions for planning.
        return [
            ProjectQuestion("outcome", "Desired Outcome", "What should be working when this project is done?"),
            ProjectQuestion("scope", "Scope", "Must-have features and out-of-scope items"),
            ProjectQuestion("stack", "Tech Stack", "Frameworks, language versions, and runtime preferences"),
            ProjectQuestion("quality", "Quality Bar", "Tests, lint, security, performance expectations"),
            ProjectQuestion("constraints", "Constraints", "Deadlines, compatibility, architecture constraints"),
        ]

    async def build_plan(self, goal: str, answers: dict[str, str]) -> dict[str, Any]:
        ai_plan = await self._ai_build_plan(goal, answers)
        if ai_plan:
            return ai_plan

        features = self._extract_features(answers.get("scope", ""))
        if not features:
            features = [
                "Create the base project scaffold and development setup",
                "Implement core business/domain logic",
                "Implement interfaces (API/UI) and integrations",
                "Add tests, docs, and validation hardening",
            ]

        tasks: list[str] = []
        tasks.append(
            self._task_prompt(
                "Scaffold and setup",
                goal,
                answers,
                "Create/verify project structure, build tooling, and baseline run command.",
            )
        )
        for idx, feat in enumerate(features, start=1):
            tasks.append(
                self._task_prompt(
                    f"Feature {idx}",
                    goal,
                    answers,
                    f"Implement: {feat}",
                )
            )
        tasks.append(
            self._task_prompt(
                "Quality pass",
                goal,
                answers,
                "Add/adjust tests, fix regressions, and ensure stable run/build output.",
            )
        )

        plan_markdown = "\n".join(
            [
                f"# Project Plan",
                f"- Goal: {goal}",
                f"- Outcome: {answers.get('outcome', '').strip() or 'Not provided'}",
                f"- Stack: {answers.get('stack', '').strip() or 'Use existing repo stack'}",
                f"- Constraints: {answers.get('constraints', '').strip() or 'None specified'}",
                "",
                "## Execution Sequence",
            ]
            + [f"{i}. {self._title_from_prompt(t)}" for i, t in enumerate(tasks, start=1)]
        )
        return {"plan": plan_markdown, "tasks": tasks}

    async def execute(
        self,
        *,
        tasks: list[str],
        repo_path: str,
        mode: str,
        auto_execute: bool,
    ) -> list[TaskRecord]:
        created: list[TaskRecord] = []
        for task_prompt in tasks:
            req = TaskCreateRequest(prompt=task_prompt, repoPath=repo_path, mode=mode)
            if auto_execute:
                record = await self.task_service.create_and_execute(req)
            else:
                record = self.task_service.task_store.create_task(req)
            created.append(record)
        return created

    @staticmethod
    def _extract_features(scope: str) -> list[str]:
        lines = [x.strip(" -\t") for x in scope.replace(",", "\n").splitlines()]
        return [x for x in lines if x]

    @staticmethod
    def _title_from_prompt(prompt: str) -> str:
        first = prompt.splitlines()[0].strip()
        return first[:120]

    @staticmethod
    def _task_prompt(title: str, goal: str, answers: dict[str, str], ask: str) -> str:
        return (
            f"{title}: {ask}\n\n"
            f"Project goal: {goal}\n"
            f"Desired outcome: {answers.get('outcome', '')}\n"
            f"Scope details: {answers.get('scope', '')}\n"
            f"Stack constraints: {answers.get('stack', '')}\n"
            f"Quality requirements: {answers.get('quality', '')}\n"
            f"Hard constraints: {answers.get('constraints', '')}\n"
            "Use local-first execution and keep changes minimal, testable, and production-safe."
        )

    async def _ai_discover_questions(self, goal: str) -> list[ProjectQuestion]:
        if not self.ai_enabled:
            return []
        prompt = (
            "Return only strict JSON array of 4-6 clarification questions for software project scoping. "
            "Each item must have keys: key,label,placeholder. Keep keys lowercase snake_case.\n\n"
            f"Project goal: {goal}"
        )
        raw = await self._ai_generate(prompt)
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            questions: list[ProjectQuestion] = []
            for item in parsed:
                key = str(item.get("key", "")).strip().lower()
                label = str(item.get("label", "")).strip()
                placeholder = str(item.get("placeholder", "")).strip()
                if key and label:
                    questions.append(ProjectQuestion(key=key, label=label, placeholder=placeholder or label))
            return questions[:6]
        except Exception:
            return []

    async def _ai_build_plan(self, goal: str, answers: dict[str, str]) -> dict[str, Any] | None:
        if not self.ai_enabled:
            return None
        prompt = (
            "Create a software delivery plan and executable task prompts. Return only strict JSON object "
            "with keys: plan (markdown string), tasks (array of concrete coding task prompts).\n\n"
            f"Goal: {goal}\n"
            f"Answers: {json.dumps(answers, ensure_ascii=True)}\n"
            "Rules: local-first, minimal context per task, no repo-wide dumps."
        )
        raw = await self._ai_generate(prompt)
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            plan = str(parsed.get("plan", "")).strip()
            tasks = [str(x).strip() for x in parsed.get("tasks", []) if str(x).strip()]
            if not tasks:
                return None
            return {"plan": plan or "# Project Plan", "tasks": tasks}
        except Exception:
            return None

    async def _ai_generate(self, prompt: str) -> str | None:
        payload = {"model": self.ai_model, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
        try:
            async with httpx.AsyncClient(timeout=self.ai_timeout) as client:
                response = await client.post(f"{self.ai_base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
            return (data.get("response", "") or "").strip()
        except Exception:
            return None
