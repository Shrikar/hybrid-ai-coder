from __future__ import annotations

from typing import Any, Optional


class ContextBuilder:
    def build_escalation_context(
        self,
        prompt: str,
        repo_path: str,
        allowed_files: Optional[list[str]] = None,
        failing_log: Optional[str] = None,
        diff_text: Optional[str] = None,
    ) -> dict[str, Any]:
        task = prompt.strip().split("\n")[0].strip()
        if not task.endswith((".", "!", "?")):
            task += "."

        safe_allowed = allowed_files or []
        failing_log_summary = self.summarize_log(failing_log or "")
        unified_diff_snippet = self._truncate_text(diff_text or "", 2000)

        return {
            "task": task,
            "repoPath": repo_path,
            "allowedFiles": safe_allowed,
            "failingLogSummary": failing_log_summary,
            "unifiedDiffSnippet": unified_diff_snippet,
        }

    def summarize_log(self, log_text: str, max_chars: int = 1200) -> str:
        if not log_text:
            return ""

        if len(log_text) <= max_chars:
            return log_text

        lines = log_text.split("\n")
        keys = ("error", "exception", "fail", "fatal")
        summary_lines: list[str] = []

        for idx, line in enumerate(lines):
            if any(k in line.lower() for k in keys):
                start = max(0, idx - 2)
                end = min(len(lines), idx + 3)
                summary_lines.extend(lines[start:end])

        if not summary_lines:
            summary_lines = lines[:5] + lines[-5:]

        return self._truncate_text("\n".join(summary_lines), max_chars)

    def _truncate_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > int(max_chars * 0.8):
            truncated = truncated[:last_space]
        return truncated + "..."
