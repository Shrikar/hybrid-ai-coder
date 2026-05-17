import pytest

from backend.models.task_models import ExecutorResult, TaskCreateRequest, ValidationSummary
from backend.router.task_router import TaskRouter
from backend.services.task_execution_service import TaskExecutionService
from backend.storage.task_store import TaskStore


class StubLocalExecutor:
    def __init__(self, responses):
        self.responses = responses
        self.i = 0

    async def execute(self, prompt, context=None):
        idx = min(self.i, len(self.responses) - 1)
        self.i += 1
        return self.responses[idx]


class StubGptExecutor:
    def __init__(self, responses):
        self.responses = responses
        self.i = 0

    async def execute(self, prompt, context=None):
        idx = min(self.i, len(self.responses) - 1)
        self.i += 1
        return self.responses[idx]


@pytest.mark.asyncio
async def test_budget_exceeded_sets_flag_and_fails():
    store = TaskStore()
    router = TaskRouter(local_retry_limit=0)
    local = StubLocalExecutor(
        [
            ExecutorResult(
                result=None,
                error="local failed",
                validationSummary=ValidationSummary(passed=False, checksRun=["local"], failedChecks=["local"]),
            )
        ]
    )
    gpt = StubGptExecutor(
        [
            ExecutorResult(
                result=None,
                error="gpt failed",
                validationSummary=ValidationSummary(passed=False, checksRun=["gpt"], failedChecks=["gpt"]),
            ),
            ExecutorResult(
                result=None,
                error="gpt failed again",
                validationSummary=ValidationSummary(passed=False, checksRun=["gpt"], failedChecks=["gpt"]),
            ),
        ]
    )

    service = TaskExecutionService(store, router, local, gpt, local_retry_limit=0)
    task = await service.create_and_execute(TaskCreateRequest(prompt="architecture security task", repoPath="/tmp/repo"))

    assert task.status == "failed"
    assert task.budgetExceeded is True
    assert "budget exceeded" in (task.error or "").lower()
    assert task.gptCallsUsed == 2


@pytest.mark.asyncio
async def test_local_success_stays_local_without_gpt():
    store = TaskStore()
    router = TaskRouter(local_retry_limit=2)
    local = StubLocalExecutor(
        [ExecutorResult(result="done", validationSummary=ValidationSummary(passed=True, checksRun=["local"]))]
    )
    gpt = StubGptExecutor([])
    service = TaskExecutionService(store, router, local, gpt, local_retry_limit=2)

    task = await service.create_and_execute(TaskCreateRequest(prompt="create class dto", repoPath="/tmp/repo"))

    assert task.status == "completed"
    assert task.assignedModel == "local"
    assert task.gptCallsUsed == 0
