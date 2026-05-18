from __future__ import annotations

import asyncio
from typing import Optional

from backend.models.task_models import TaskStatus
from backend.services.task_execution_service import TaskExecutionService
from backend.storage.task_store import TaskStore


class TaskWorker:
    def __init__(
        self,
        service: TaskExecutionService,
        store: TaskStore,
        max_retries: int = 2,
        retry_delay_seconds: float = 1.5,
    ) -> None:
        self.service = service
        self.store = store
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self._queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self._runner: Optional[asyncio.Task] = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        if self._runner is None or self._runner.done():
            self._runner = asyncio.create_task(self._run_loop())
        await self.enqueue_recovered()

    async def stop(self) -> None:
        self._stopping = True
        if self._runner and not self._runner.done():
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass

    async def enqueue(self, task_id: str, attempt: int = 0) -> None:
        await self._queue.put((task_id, attempt))

    async def enqueue_recovered(self) -> None:
        self.store.recover_interrupted_tasks()
        for task in self.store.list_tasks_by_status([TaskStatus.created]):
            await self.enqueue(task.taskId, 0)

    async def _run_loop(self) -> None:
        while not self._stopping:
            task_id, attempt = await self._queue.get()
            try:
                task = self.store.get_task(task_id)
                if task is None:
                    continue
                if task.status not in {TaskStatus.created, TaskStatus.failed}:
                    continue
                await self.service.execute_task(task_id)
            except Exception as exc:  # noqa: BLE001
                if attempt < self.max_retries:
                    self.store.add_event(
                        task_id,
                        "worker_retry",
                        f"Worker retry attempt {attempt + 1} after failure: {exc}",
                    )
                    await asyncio.sleep(self.retry_delay_seconds)
                    await self.enqueue(task_id, attempt + 1)
                else:
                    self.store.update_task(task_id, status=TaskStatus.failed, error=f"Worker failed: {exc}")
                    self.store.add_event(task_id, "worker_failed", "Worker exhausted retries")
            finally:
                self._queue.task_done()
