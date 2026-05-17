from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, Header, HTTPException
from sse_starlette.sse import EventSourceResponse

from backend.executors.ai_router_executor import AIRouterExecutor
from backend.executors.gpt_executor import GPTExecutor
from backend.executors.ollama_executor import OllamaExecutor
from backend.models.task_models import TaskCreateRequest, TaskCreateResponse, TaskEvent, TaskRecord
from backend.router.task_router import TaskRouter
from backend.services.config_loader import ConfigLoader
from backend.services.task_execution_service import TaskExecutionService
from backend.storage.task_store import TaskStore

router = APIRouter()

_cfg_loader = ConfigLoader()
_full_cfg = _cfg_loader.load()
_cfg = _cfg_loader.resolve_active_models()
_routing_cfg = _cfg.get("routing", {})
_local_cfg = _cfg.get("local", {})
_cloud_cfg = _cfg.get("cloud", {})
_storage_cfg = _full_cfg.get("storage", {})
_ai_router_cfg = _routing_cfg.get("ai_router", {})
_task_store = TaskStore(db_path=_storage_cfg.get("task_db_path"))
_ai_router_executor = AIRouterExecutor(
    config={
        "enabled": _ai_router_cfg.get("enabled", True),
        "model": _ai_router_cfg.get("model", _local_cfg.get("model", "qwen3-coder")),
        "base_url": _ai_router_cfg.get("base_url", _local_cfg.get("base_url", "http://localhost:11434")),
        "timeout": _ai_router_cfg.get("timeout", 20),
    }
)
_router = TaskRouter(
    complexity_threshold=int(_routing_cfg.get("complexity_threshold", 50)),
    local_retry_limit=int(_routing_cfg.get("local_retry_limit", 2)),
    ai_executor=_ai_router_executor,
    ai_confidence_threshold=float(_ai_router_cfg.get("confidence_threshold", 0.55)),
)
_local_executor = OllamaExecutor(
    config={
        "model": _local_cfg.get("model", "qwen3-coder"),
        "base_url": _local_cfg.get("base_url", "http://localhost:11434"),
        "timeout": _local_cfg.get("timeout", 90),
        "provider": _cfg.get("local_name", "ollama"),
    }
)
_gpt_executor = GPTExecutor(config=_cloud_cfg)
_service = TaskExecutionService(
    task_store=_task_store,
    router=_router,
    local_executor=_local_executor,
    gpt_executor=_gpt_executor,
    local_retry_limit=int(_routing_cfg.get("local_retry_limit", 2)),
)


def _require_local_token(x_local_token: Optional[str]) -> None:
    token_env = _full_cfg.get("security", {}).get("local_api_token_env", "HYBRID_AI_LOCAL_TOKEN")
    expected = os.getenv(token_env, "")
    if expected and x_local_token != expected:
        raise HTTPException(status_code=401, detail="Invalid local API token")


@router.post("", response_model=TaskCreateResponse)
async def create_task(request: TaskCreateRequest, x_local_token: Optional[str] = Header(default=None)) -> TaskCreateResponse:
    _require_local_token(x_local_token)
    record = await _service.create_and_execute(request)
    return TaskCreateResponse(taskId=record.taskId, status=record.status)


@router.post("/{task_id}/resume", response_model=TaskRecord)
async def resume_task(task_id: str, x_local_token: Optional[str] = Header(default=None)) -> TaskRecord:
    _require_local_token(x_local_token)
    try:
        return await _service.resume_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{task_id}/approve", response_model=TaskRecord)
async def approve_task(task_id: str, x_local_token: Optional[str] = Header(default=None)) -> TaskRecord:
    _require_local_token(x_local_token)
    try:
        return _service.approve_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{task_id}/events", response_model=list[TaskEvent])
async def task_events(task_id: str, x_local_token: Optional[str] = Header(default=None)) -> list[TaskEvent]:
    _require_local_token(x_local_token)
    return _task_store.list_events(task_id)


@router.get("/metrics/savings")
async def savings_metrics(x_local_token: Optional[str] = Header(default=None)) -> dict[str, Union[float, int]]:
    _require_local_token(x_local_token)
    return _task_store.savings_metrics()


@router.get("/metrics/savings/projects")
async def savings_metrics_by_project(
    x_local_token: Optional[str] = Header(default=None),
) -> list[dict[str, Union[str, float, int]]]:
    _require_local_token(x_local_token)
    return _task_store.savings_metrics_by_project()


@router.get("/{task_id}", response_model=TaskRecord)
async def get_task(task_id: str, x_local_token: Optional[str] = Header(default=None)) -> TaskRecord:
    _require_local_token(x_local_token)
    record = _task_store.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return record


@router.get("", response_model=list[TaskRecord])
async def list_tasks(x_local_token: Optional[str] = Header(default=None)) -> list[TaskRecord]:
    _require_local_token(x_local_token)
    return _task_store.list_tasks()


@router.get("/{task_id}/events/stream")
async def stream_task_events(
    task_id: str,
    x_local_token: Optional[str] = Header(default=None),
    last_event_id: Optional[str] = None,
):
    _require_local_token(x_local_token)

    async def event_generator():
        cursor = last_event_id
        emitted = 0
        max_polls = 60
        for _ in range(max_polls):
            events = _task_store.list_events_since(task_id, cursor)
            if events:
                for event in events:
                    cursor = event.eventId
                    emitted += 1
                    yield {
                        "event": "task_event",
                        "id": event.eventId,
                        "data": event.model_dump_json(),
                    }
            await asyncio.sleep(0.5)
        if emitted == 0:
            yield {"event": "task_event", "data": json.dumps({"message": "no_new_events"})}

    return EventSourceResponse(event_generator())


@router.get("/{task_id}/approval/preview")
async def approval_preview(task_id: str, x_local_token: Optional[str] = Header(default=None)) -> dict:
    _require_local_token(x_local_token)
    task = _task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    pending = _task_store.get_pending_approval_payload(task_id)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending approval")

    previews = []
    repo_root = Path(task.repoPath).resolve()
    for item in pending:
        rel = item.get("path", "")
        proposed = item.get("content", "")
        target = (repo_root / rel).resolve()
        existing = ""
        try:
            if target.exists() and target.is_file():
                existing = target.read_text()
        except Exception:
            existing = ""
        previews.append(
            {
                "path": rel,
                "existing": existing,
                "proposed": proposed,
            }
        )

    return {"taskId": task_id, "files": previews}
