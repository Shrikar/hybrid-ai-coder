from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.health import router as health_router
from backend.api.tasks import router as tasks_router
from backend.api.skills import router as skills_router
from backend.services.config_loader import ConfigLoader
from backend.storage.task_store import TaskStore
from backend.ui.routes import router as ui_router

app = FastAPI(
    title="Hybrid AI Coding Orchestrator",
    description="Local-first hybrid AI coding backend",
    version="0.2.0",
)

_cfg = ConfigLoader().load()
_security = _cfg.get("security", {})
_allow_non_localhost = bool(_security.get("allow_non_localhost", False))
_storage_cfg = _cfg.get("storage", {})
_task_store = TaskStore(db_path=_storage_cfg.get("task_db_path"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(skills_router, prefix="/api/v1/skills", tags=["skills"])
app.include_router(health_router, prefix="/api/v1/health", tags=["health"])
app.include_router(ui_router, prefix="/ui", tags=["ui"])
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def localhost_only_guard(request: Request, call_next):
    if _allow_non_localhost:
        return await call_next(request)

    client_host = request.client.host if request.client else None
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="Localhost-only API")
    return await call_next(request)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hybrid AI Coding Orchestrator API", "status": "running"}


@app.on_event("startup")
async def startup_recovery() -> None:
    _task_store.recover_interrupted_tasks()
