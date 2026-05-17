from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.api import tasks as tasks_api
from backend.models.task_models import TaskCreateResponse
from backend.services.skill_catalog import SkillCatalog

router = APIRouter()
_catalog = SkillCatalog()


class SkillRunRequest(BaseModel):
    repoPath: str
    userInput: str = ""


@router.get("", response_model=list[dict])
async def list_skills(x_local_token: Optional[str] = Header(default=None)) -> list[dict]:
    tasks_api._require_local_token(x_local_token)
    return _catalog.list_skills()


@router.post("/{skill_id}/run", response_model=TaskCreateResponse)
async def run_skill(skill_id: str, body: SkillRunRequest, x_local_token: Optional[str] = Header(default=None)) -> TaskCreateResponse:
    tasks_api._require_local_token(x_local_token)
    try:
        request = _catalog.build_task_request(skill_id=skill_id, repo_path=body.repoPath, user_input=body.userInput)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    record = await tasks_api._service.create_and_execute(request)
    return TaskCreateResponse(taskId=record.taskId, status=record.status)
