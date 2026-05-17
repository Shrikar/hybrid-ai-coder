from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PolicyDecision:
    requires_approval: bool
    reason: str


class PolicyEngine:
    def __init__(self, config: dict):
        p = config.get("policy", {})
        self.approval_file_threshold = int(p.get("approval_file_threshold", 5))
        self.approval_path_keywords = [x.lower() for x in p.get("approval_path_keywords", ["security", "migration", "auth", "pom.xml"])]

    def evaluate_apply(self, file_paths: list[str]) -> PolicyDecision:
        if len(file_paths) >= self.approval_file_threshold:
            return PolicyDecision(True, "file_count_threshold")

        for path in file_paths:
            low = path.lower()
            if any(k in low for k in self.approval_path_keywords):
                return PolicyDecision(True, "path_keyword_match")

        return PolicyDecision(False, "no_policy_trigger")
