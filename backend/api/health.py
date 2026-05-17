from __future__ import annotations

from fastapi import APIRouter
from backend.services.config_loader import ConfigLoader
from backend.services.startup_diagnostics import StartupDiagnostics

router = APIRouter()


@router.get("", summary="Health check")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/diagnostics", summary="Startup diagnostics")
async def diagnostics() -> dict:
    cfg = ConfigLoader().load()
    return StartupDiagnostics(cfg).run()
