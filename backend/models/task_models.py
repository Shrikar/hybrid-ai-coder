from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class TaskMode(str, Enum):
    auto = "auto"
    cloud = "cloud"
    gpt = "gpt"
    local = "local"
    pi = "pi"


class TaskStatus(str, Enum):
    created = "created"
    executing = "executing"
    running = "running"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    failed = "failed"


class TaskCreateRequest(BaseModel):
    prompt: str
    repoPath: str
    mode: TaskMode = TaskMode.auto
    attachments: list[dict[str, str]] = Field(default_factory=list)
    legacyModeAliasUsed: bool = Field(default=False, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def mark_legacy_mode_alias(cls, values: Any) -> Any:
        if isinstance(values, dict):
            mode = values.get("mode")
            if isinstance(mode, str) and mode.lower() == "gpt":
                values["legacyModeAliasUsed"] = True
        return values

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode_aliases(cls, value: Any) -> Any:
        if isinstance(value, str) and value.lower() == "gpt":
            return "cloud"
        if value == TaskMode.gpt:
            return TaskMode.cloud
        return value


class TaskCreateResponse(BaseModel):
    taskId: str
    status: TaskStatus


class ValidationSummary(BaseModel):
    passed: bool = True
    checksRun: list[str] = Field(default_factory=list)
    failedChecks: list[str] = Field(default_factory=list)


class TokenUsage(BaseModel):
    promptTokens: int = 0
    completionTokens: int = 0
    totalTokens: int = 0
    costUsd: float = 0.0


class ExecutorResult(BaseModel):
    result: Optional[str] = None
    error: Optional[str] = None
    changedFiles: list[str] = Field(default_factory=list)
    validationSummary: ValidationSummary = Field(default_factory=ValidationSummary)
    tokenUsage: TokenUsage = Field(default_factory=TokenUsage)


class TaskEvent(BaseModel):
    eventId: str
    taskId: str
    eventType: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime


class PendingApproval(BaseModel):
    taskId: str
    files: list[dict[str, str]] = Field(default_factory=list)
    createdAt: datetime


class TaskRecord(BaseModel):
    taskId: str
    prompt: str
    repoPath: str
    mode: TaskMode
    attachments: list[dict[str, str]] = Field(default_factory=list)
    status: TaskStatus
    createdAt: datetime
    assignedModel: Optional[str] = None
    routingReason: Optional[str] = None
    routerDecision: Optional[str] = None
    routerConfidence: float = 0.0
    routerReason: Optional[str] = None
    complexityScore: int = 0
    cloudCallsUsed: int = 0
    cloudTokenEstimate: int = 0
    cloudCostUsd: float = 0.0
    # Backward-compat aliases. Kept in response payloads during transition.
    gptCallsUsed: int = 0
    gptTokenEstimate: int = 0
    gptCostUsd: float = 0.0
    localRetries: int = 0
    budgetExceeded: bool = False
    requiresApproval: bool = False
    currentSubtaskIndex: int = 0
    totalSubtasks: int = 0
    result: Optional[str] = None
    error: Optional[str] = None
    changedFiles: list[str] = Field(default_factory=list)
    validationSummary: ValidationSummary = Field(default_factory=ValidationSummary)
    completedAt: Optional[datetime] = None

    @model_validator(mode="after")
    def sync_legacy_cloud_fields(self):
        # Canonical source is cloud* fields. Maintain gpt* aliases for compatibility.
        if self.cloudCallsUsed == 0 and self.gptCallsUsed:
            self.cloudCallsUsed = self.gptCallsUsed
        if self.cloudTokenEstimate == 0 and self.gptTokenEstimate:
            self.cloudTokenEstimate = self.gptTokenEstimate
        if self.cloudCostUsd == 0.0 and self.gptCostUsd:
            self.cloudCostUsd = self.gptCostUsd

        self.gptCallsUsed = self.cloudCallsUsed
        self.gptTokenEstimate = self.cloudTokenEstimate
        self.gptCostUsd = self.cloudCostUsd

        if self.mode == TaskMode.gpt:
            self.mode = TaskMode.cloud
        return self
