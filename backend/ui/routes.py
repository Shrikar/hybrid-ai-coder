from __future__ import annotations

import difflib
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.api import tasks as tasks_api
from backend.models.task_models import TaskCreateRequest
from backend.services.project_mode_service import ProjectModeService
from backend.services.skill_catalog import SkillCatalog

router = APIRouter()
templates = Jinja2Templates(directory="templates")
_catalog = SkillCatalog()
_project_mode = ProjectModeService(
    tasks_api._service,
    ai_config={
        "enabled": getattr(tasks_api, "_ai_router_cfg", {}).get("enabled", True),
        "model": getattr(tasks_api, "_ai_router_cfg", {}).get("model", getattr(tasks_api, "_local_cfg", {}).get("model", "qwen3-coder")),
        "base_url": getattr(tasks_api, "_ai_router_cfg", {}).get("base_url", getattr(tasks_api, "_local_cfg", {}).get("base_url", "http://localhost:11434")),
        "timeout": getattr(tasks_api, "_ai_router_cfg", {}).get("timeout", 20),
    },
)


def _tasks_with_pending_count():
    tasks = tasks_api._task_store.list_tasks()
    view = []
    for task in tasks:
        row = task.model_dump(mode="json")
        pending_count = 0
        if task.requiresApproval:
            pending = tasks_api._task_store.get_pending_approval_payload(task.taskId) or []
            pending_count = len(pending)
        row["pendingApprovalFileCount"] = pending_count
        view.append(row)
    return view


def _selected_task_detail(task_id: Optional[str]):
    if not task_id:
        return None, [], None
    task = tasks_api._task_store.get_task(task_id)
    if task is None:
        return None, [], None
    events = tasks_api._task_store.list_events(task_id)
    preview = None
    if task.requiresApproval:
        preview = tasks_api._task_store.get_pending_approval_payload(task_id) or []
    return task, events, preview


def _safe_read_text(path: Path) -> str:
    try:
        if path.exists() and path.is_file():
            return path.read_text()
    except Exception:
        return ""
    return ""


def _git_head_file(repo_root: Path, rel_path: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"HEAD:{rel_path}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout
    except Exception:
        return ""
    return ""


def _make_unified_diff(path_label: str, before: str, after: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile=f"a/{path_label}",
        tofile=f"b/{path_label}",
        lineterm="",
    )
    return "\n".join(lines)


def _build_review_items(task, approval_preview: Optional[list[dict[str, str]]]) -> list[dict[str, str]]:
    review_items: list[dict[str, str]] = []
    repo_root = Path(task.repoPath).expanduser().resolve()

    if task.requiresApproval and approval_preview:
        for item in approval_preview:
            rel = item.get("path", "")
            proposed = item.get("content", "")
            target = (repo_root / rel).resolve()
            before = _safe_read_text(target)
            diff = _make_unified_diff(rel, before, proposed)
            review_items.append(
                {
                    "path": rel,
                    "diff": diff,
                    "added": str(sum(1 for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))),
                    "removed": str(sum(1 for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---"))),
                }
            )
        return review_items

    for changed in task.changedFiles or []:
        target = Path(changed).resolve()
        try:
            rel = str(target.relative_to(repo_root))
        except Exception:
            rel = target.name
        after = _safe_read_text(target)
        before = _git_head_file(repo_root, rel)
        diff = _make_unified_diff(rel, before, after)
        review_items.append(
            {
                "path": rel,
                "diff": diff,
                "added": str(sum(1 for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++"))),
                "removed": str(sum(1 for ln in diff.splitlines() if ln.startswith("-") and not ln.startswith("---"))),
            }
        )

    return review_items


@router.get("", response_class=HTMLResponse)
async def ui_home(request: Request, task_id: Optional[str] = Query(default=None)):
    tasks = _tasks_with_pending_count()
    skills = _catalog.list_skills()
    metrics = tasks_api._task_store.savings_metrics()
    selected_task, selected_events, selected_preview = _selected_task_detail(task_id)
    selected_review_items = (
        _build_review_items(selected_task, selected_preview) if selected_task is not None else []
    )
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tasks": tasks,
            "skills": skills,
            "metrics": metrics,
            "selected_task": selected_task,
            "selected_events": selected_events,
            "selected_preview": selected_preview,
            "selected_review_items": selected_review_items,
        },
    )


@router.get("/tasks", response_class=HTMLResponse)
async def ui_tasks_list(request: Request):
    tasks = _tasks_with_pending_count()
    return templates.TemplateResponse("partials/task_list.html", {"request": request, "tasks": tasks})


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def ui_task_detail(request: Request, task_id: str):
    task = tasks_api._task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    events = tasks_api._task_store.list_events(task_id)
    preview = None
    if task.requiresApproval:
        pending = tasks_api._task_store.get_pending_approval_payload(task_id)
        preview = pending or []
    review_items = _build_review_items(task, preview)

    is_htmx = request.headers.get("HX-Request", "").lower() == "true"
    if is_htmx:
        return templates.TemplateResponse(
            "partials/task_detail.html",
            {
                "request": request,
                "task": task,
                "events": events,
                "approval_preview": preview,
                "review_items": review_items,
            },
        )

    tasks = _tasks_with_pending_count()
    skills = _catalog.list_skills()
    metrics = tasks_api._task_store.savings_metrics()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tasks": tasks,
            "skills": skills,
            "metrics": metrics,
            "selected_task": task,
            "selected_events": events,
            "selected_preview": preview,
            "selected_review_items": review_items,
        },
    )


@router.post("/tasks/create", response_class=HTMLResponse)
async def ui_create_task(
    request: Request,
    prompt: str = Form(...),
    repo_path: str = Form(...),
    mode: str = Form("auto"),
    attachments: Optional[list[UploadFile]] = File(default=None),
):
    parsed_attachments = await _parse_attachments(attachments or [])
    req = TaskCreateRequest(prompt=prompt, repoPath=repo_path, mode=mode, attachments=parsed_attachments)
    await tasks_api._service.create_and_execute(req)
    tasks = _tasks_with_pending_count()
    return templates.TemplateResponse("partials/task_list.html", {"request": request, "tasks": tasks})


async def _parse_attachments(files: list[UploadFile]) -> list[dict[str, str]]:
    if not files:
        return []

    out: list[dict[str, str]] = []
    max_files = 5
    max_chars = 3000
    max_image_bytes = 2 * 1024 * 1024
    for file in files[:max_files]:
        content_type = str(file.content_type or "").lower()
        try:
            raw = await file.read()
        except Exception:
            raw = b""

        if content_type.startswith("image/"):
            if len(raw) <= max_image_bytes:
                import base64

                out.append(
                    {
                        "type": "image",
                        "filename": file.filename or "image",
                        "contentType": content_type,
                        "imageBase64": base64.b64encode(raw).decode("ascii"),
                    }
                )
            continue

        text = raw.decode("utf-8", errors="replace")
        snippet = text[:max_chars]
        out.append(
            {
                "type": "text",
                "filename": file.filename or "attachment.txt",
                "contentType": content_type or "text/plain",
                "text": snippet,
            }
        )
    return out


@router.post("/skills/run", response_class=HTMLResponse)
async def ui_run_skill(request: Request, skill_id: str = Form(...), repo_path: str = Form(...), user_input: str = Form("")):
    req = _catalog.build_task_request(skill_id=skill_id, repo_path=repo_path, user_input=user_input)
    await tasks_api._service.create_and_execute(req)
    tasks = _tasks_with_pending_count()
    return templates.TemplateResponse("partials/task_list.html", {"request": request, "tasks": tasks})


@router.post("/projects/discover", response_class=HTMLResponse)
async def ui_project_discover(request: Request, goal: str = Form(...), repo_path: str = Form(...), mode: str = Form("auto")):
    questions = await _project_mode.discover(goal)
    return templates.TemplateResponse(
        "partials/project_questions.html",
        {
            "request": request,
            "goal": goal,
            "repo_path": repo_path,
            "mode": mode,
            "questions": questions,
        },
    )


@router.post("/projects/execute", response_class=HTMLResponse)
async def ui_project_execute(
    request: Request,
    goal: str = Form(...),
    repo_path: str = Form(...),
    mode: str = Form("auto"),
    outcome: str = Form(""),
    scope: str = Form(""),
    stack: str = Form(""),
    quality: str = Form(""),
    constraints: str = Form(""),
    auto_execute: Optional[str] = Form(None),
):
    answers = {
        "outcome": outcome,
        "scope": scope,
        "stack": stack,
        "quality": quality,
        "constraints": constraints,
    }
    plan = await _project_mode.build_plan(goal, answers)
    records = await _project_mode.execute(
        tasks=plan["tasks"],
        repo_path=repo_path,
        mode=mode,
        auto_execute=bool(auto_execute),
    )
    return templates.TemplateResponse(
        "partials/project_result.html",
        {
            "request": request,
            "goal": goal,
            "plan_text": plan["plan"],
            "task_prompts": plan["tasks"],
            "created_records": records,
            "auto_execute": bool(auto_execute),
        },
    )


@router.post("/tasks/{task_id}/approve", response_class=HTMLResponse)
async def ui_approve_task(request: Request, task_id: str):
    try:
        tasks_api._service.approve_task(task_id)
    except ValueError:
        pass
    return RedirectResponse(url=f"/ui?task_id={task_id}", status_code=303)


@router.post("/tasks/{task_id}/resume", response_class=HTMLResponse)
async def ui_resume_task(request: Request, task_id: str):
    try:
        await tasks_api._service.resume_task(task_id)
    except ValueError:
        pass
    return RedirectResponse(url=f"/ui?task_id={task_id}", status_code=303)
