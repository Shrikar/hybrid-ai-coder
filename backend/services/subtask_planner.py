from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Subtask:
    title: str
    prompt: str
    preferred_model: str | None = None


class SubtaskPlanner:
    """Simple local-first planner that decomposes tasks into execution subtasks."""

    CLOUD_HINTS = {
        "vaadin",
        "ui wiring",
        "security design",
        "architecture",
        "distributed",
        "concurrency",
        "migration",
    }

    def plan(self, prompt: str) -> list[Subtask]:
        text = prompt.strip()
        low = text.lower()

        parts = [p.strip() for p in text.replace("\n", " ").split(" then ") if p.strip()]
        if len(parts) <= 1:
            parts = [text]

        subtasks: list[Subtask] = []
        for idx, part in enumerate(parts, start=1):
            preferred = "cloud" if self._needs_cloud(part.lower()) else "local"
            subtasks.append(
                Subtask(
                    title=f"subtask_{idx}",
                    prompt=part,
                    preferred_model=preferred,
                )
            )

        if not subtasks:
            subtasks.append(Subtask(title="subtask_1", prompt=text, preferred_model="local"))

        # Local-first default for generic prompts.
        if len(subtasks) == 1 and not self._needs_cloud(low):
            subtasks[0].preferred_model = "local"

        return subtasks

    def _needs_cloud(self, text: str) -> bool:
        return any(hint in text for hint in self.CLOUD_HINTS)
