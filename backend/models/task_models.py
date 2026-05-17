from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskMode(str, Enum):
    auto = "auto"
    gpt = "gpt"
    local = "local"


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
    status: TaskStatus
    createdAt: datetime
    assignedModel: Optional[str] = None
    routingReason: Optional[str] = None
    routerDecision: Optional[str] = None
    routerConfidence: float = 0.0
    routerReason: Optional[str] = None
    complexityScore: int = 0
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
