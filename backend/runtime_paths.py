from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    env_root = os.getenv("HYBRID_AI_CODER_HOME")
    if env_root:
        p = Path(env_root).expanduser().resolve()
        if (p / "config" / "config.json").exists():
            return p

    cwd = Path.cwd().resolve()
    if (cwd / "config" / "config.json").exists():
        return cwd

    src_root = Path(__file__).resolve().parents[1]
    if (src_root / "config" / "config.json").exists():
        return src_root

    return cwd


def config_path() -> Path:
    return project_root() / "config" / "config.json"


def templates_dir() -> Path:
    return project_root() / "templates"


def static_dir() -> Path:
    return project_root() / "static"
