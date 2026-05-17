from pathlib import Path

import pytest

from backend.models.task_models import ExecutorResult, TaskCreateRequest, ValidationSummary
from backend.router.task_router import TaskRouter
from backend.services.task_execution_service import TaskExecutionService
from backend.storage.task_store import TaskStore


class StubLocalExecutor:
    async def execute(self, prompt, context=None):
        content = (
            "FILE: src/main/java/com/example/App.java\n"
            "```java\n"
            "public class App {}\n"
            "```\n"
        )
        return ExecutorResult(
            result=content,
            validationSummary=ValidationSummary(passed=True, checksRun=["local"]),
        )


class StubGptExecutor:
    async def execute(self, prompt, context=None):
        return ExecutorResult(
            result="FILE: README.md\n```md\n# done\n```\n",
            validationSummary=ValidationSummary(passed=True, checksRun=["gpt"]),
        )


@pytest.mark.asyncio
async def test_orchestrator_applies_files(tmp_path: Path):
    store = TaskStore()
    router = TaskRouter(local_retry_limit=1)
    service = TaskExecutionService(store, router, StubLocalExecutor(), StubGptExecutor(), local_retry_limit=1)

    task = await service.create_and_execute(
        TaskCreateRequest(prompt="create spring boot app", repoPath=str(tmp_path))
    )

    assert task.status == "completed"
    assert len(task.changedFiles) >= 1
    assert (tmp_path / "src/main/java/com/example/App.java").exists()
