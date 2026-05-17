from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union
from uuid import uuid4

from backend.models.task_models import PendingApproval, TaskCreateRequest, TaskEvent, TaskRecord, TaskStatus


class TaskStore:
    def __init__(self, db_path: Optional[str] = None) -> None:
        preferred = self._resolve_db_path(db_path)
        self.db_path = self._prepare_path(preferred)
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    @staticmethod
    def _resolve_db_path(db_path: Optional[str]) -> str:
        if db_path:
            return db_path
        env = os.getenv("TASK_DB_PATH")
        if env:
            return env
        return str(Path.home() / ".hybrid-ai-coder" / "tasks.db")

    @staticmethod
    def _prepare_path(path: str) -> str:
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            return str(target)
        except PermissionError:
            fallback = Path("/private/tmp/hybrid-ai-coder/tasks.db")
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return str(fallback)

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_events (
                    event_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_approvals (
                    task_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO schema_meta(key, value)
                VALUES ('schema_version', '1')
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """
            )

    def create_task(self, request: TaskCreateRequest) -> TaskRecord:
        task = TaskRecord(
            taskId=str(uuid4()),
            prompt=request.prompt,
            repoPath=request.repoPath,
            mode=request.mode,
            status=TaskStatus.created,
            createdAt=datetime.utcnow(),
        )
        self._upsert(task)
        self.add_event(task.taskId, "task_created", "Task created")
        return task

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._conn() as conn:
            row = conn.execute("SELECT payload FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return TaskRecord(**json.loads(row[0]))

    def update_task(self, task_id: str, **kwargs) -> Optional[TaskRecord]:
        task = self.get_task(task_id)
        if task is None:
            return None

        current = task.model_dump(mode="json")
        current.update(kwargs)
        updated = TaskRecord(**current)
        self._upsert(updated)
        return updated

    def list_tasks(self) -> list[TaskRecord]:
        with self._conn() as conn:
            rows = conn.execute("SELECT payload FROM tasks ORDER BY created_at DESC").fetchall()
        return [TaskRecord(**json.loads(row[0])) for row in rows]

    def update_status(self, task_id: str, status: TaskStatus) -> Optional[TaskRecord]:
        task = self.update_task(task_id, status=status)
        if task:
            self.add_event(task_id, "status_changed", f"Status changed to {status.value}", {"status": status.value})
        return task

    def add_event(self, task_id: str, event_type: str, message: str, payload: Optional[dict[str, Any]] = None) -> TaskEvent:
        event = TaskEvent(
            eventId=str(uuid4()),
            taskId=task_id,
            eventType=event_type,
            message=message,
            payload=payload or {},
            createdAt=datetime.utcnow(),
        )
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO task_events(event_id, task_id, payload, created_at) VALUES (?, ?, ?, ?)",
                (event.eventId, task_id, json.dumps(event.model_dump(mode="json"), default=str), event.createdAt.isoformat()),
            )
        return event

    def list_events(self, task_id: str) -> list[TaskEvent]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM task_events WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            ).fetchall()
        return [TaskEvent(**json.loads(row[0])) for row in rows]

    def list_events_since(self, task_id: str, after_event_id: Optional[str]) -> list[TaskEvent]:
        events = self.list_events(task_id)
        if not after_event_id:
            return events
        idx = next((i for i, e in enumerate(events) if e.eventId == after_event_id), None)
        if idx is None:
            return events
        return events[idx + 1 :]

    def set_pending_approval(self, task_id: str, files: list[dict[str, str]]) -> PendingApproval:
        item = PendingApproval(taskId=task_id, files=files, createdAt=datetime.utcnow())
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pending_approvals(task_id, payload, created_at) VALUES (?, ?, ?)",
                (task_id, json.dumps(item.model_dump(mode="json"), default=str), item.createdAt.isoformat()),
            )
        self.add_event(task_id, "approval_required", "Task is awaiting approval", {"files": len(files)})
        return item

    def get_pending_approval(self, task_id: str) -> Optional[PendingApproval]:
        with self._conn() as conn:
            row = conn.execute("SELECT payload FROM pending_approvals WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return PendingApproval(**json.loads(row[0]))

    def get_pending_approval_payload(self, task_id: str) -> Optional[list[dict[str, str]]]:
        item = self.get_pending_approval(task_id)
        if not item:
            return None
        return item.files

    def clear_pending_approval(self, task_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM pending_approvals WHERE task_id = ?", (task_id,))

    def recover_interrupted_tasks(self) -> int:
        tasks = self.list_tasks()
        count = 0
        for task in tasks:
            if task.status == TaskStatus.executing:
                self.update_task(task.taskId, status=TaskStatus.failed, error="Interrupted during previous run")
                self.add_event(task.taskId, "task_interrupted", "Marked failed after restart")
                count += 1
        return count

    def savings_metrics(self) -> dict[str, Union[float, int]]:
        tasks = self.list_tasks()
        return self._aggregate_savings(tasks)

    def savings_metrics_by_project(self) -> list[dict[str, Union[str, float, int]]]:
        tasks = self.list_tasks()
        grouped: dict[str, list[TaskRecord]] = {}
        for task in tasks:
            key = task.repoPath or "-"
            grouped.setdefault(key, []).append(task)

        out: list[dict[str, Union[str, float, int]]] = []
        for repo_path, project_tasks in grouped.items():
            row = self._aggregate_savings(project_tasks)
            row["repoPath"] = repo_path
            out.append(row)
        out.sort(key=lambda x: int(x.get("totalTasks", 0)), reverse=True)
        return out

    def _aggregate_savings(self, tasks: list[TaskRecord]) -> dict[str, Union[float, int]]:
        total = len(tasks)
        if total == 0:
            return {
                "totalTasks": 0,
                "localOnlyTasks": 0,
                "localOnlyRate": 0.0,
                "avgGptTokensPerTask": 0.0,
                "avgGptCallsPerTask": 0.0,
                "avgGptCostPerTaskUsd": 0.0,
            }

        local_only = sum(1 for t in tasks if t.gptCallsUsed == 0 and t.assignedModel == "local")
        total_tokens = sum(t.gptTokenEstimate for t in tasks)
        total_gpt_calls = sum(t.gptCallsUsed for t in tasks)
        total_gpt_cost = sum(t.gptCostUsd for t in tasks)

        return {
            "totalTasks": total,
            "localOnlyTasks": local_only,
            "localOnlyRate": round(local_only / total, 4),
            "avgGptTokensPerTask": round(total_tokens / total, 2),
            "avgGptCallsPerTask": round(total_gpt_calls / total, 2),
            "avgGptCostPerTaskUsd": round(total_gpt_cost / total, 6),
        }

    def _upsert(self, task: TaskRecord) -> None:
        payload = json.dumps(task.model_dump(mode="json"), default=str)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tasks(task_id, payload, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload
                """,
                (task.taskId, payload, task.createdAt.isoformat()),
            )
