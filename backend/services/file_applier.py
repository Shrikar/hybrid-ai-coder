from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ApplyPolicy:
    max_files_per_apply: int = 25
    max_file_size_bytes: int = 200_000
    blocked_path_fragments: tuple[str, ...] = (
        ".git/",
        ".env",
        "id_rsa",
        "id_ed25519",
    )


class FileApplier:
    """Applies model-generated file blocks safely under a target repo path."""

    FILE_BLOCK_RE = re.compile(
        r"FILE:\s*(?P<path>[^\n]+)\n```[a-zA-Z0-9_-]*\n(?P<content>.*?)\n```",
        re.DOTALL,
    )

    def __init__(self, policy: Optional[ApplyPolicy] = None):
        self.policy = policy or ApplyPolicy()

    def parse_blocks(self, model_output: str) -> list[tuple[str, str]]:
        if not model_output:
            return []
        blocks = []
        for match in self.FILE_BLOCK_RE.finditer(model_output):
            rel_path = match.group("path").strip()
            content = match.group("content")
            if rel_path:
                blocks.append((rel_path, content))
        return blocks[: self.policy.max_files_per_apply]

    def apply(self, model_output: str, repo_path: str) -> list[str]:
        return self.apply_blocks(self.parse_blocks(model_output), repo_path)

    def apply_blocks(self, blocks: list[tuple[str, str]], repo_path: str) -> list[str]:
        if not blocks or not repo_path:
            return []

        root = Path(repo_path).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)

        changed: list[str] = []
        for rel_path, content in blocks[: self.policy.max_files_per_apply]:
            if self._is_blocked(rel_path):
                continue
            if len(content.encode("utf-8")) > self.policy.max_file_size_bytes:
                continue

            target = (root / rel_path).resolve()
            if not self._is_within(root, target):
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            changed.append(str(target))

        return changed

    def _is_blocked(self, rel_path: str) -> bool:
        low = rel_path.lower()
        return any(fragment.lower() in low for fragment in self.policy.blocked_path_fragments)

    @staticmethod
    def _is_within(root: Path, target: Path) -> bool:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False
