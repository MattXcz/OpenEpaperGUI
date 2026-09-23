"""Simple JSON-file project storage."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
PROJECTS_DIR = DATA_DIR / "projects"
SETTINGS_FILE = DATA_DIR / "settings.json"

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _ensure_dirs() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", (name or "").strip().lower()).strip("-")
    return slug or "project"


def _project_path(project_id: str) -> Path:
    safe = _SLUG_RE.sub("", project_id)
    return PROJECTS_DIR / f"{safe}.json"


def list_projects() -> list[dict]:
    _ensure_dirs()
    projects = []
    for path in sorted(PROJECTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        projects.append(
            {
                "id": data.get("id", path.stem),
                "name": data.get("name", path.stem),
                "width": data.get("width"),
                "height": data.get("height"),
                "updatedAt": data.get("updatedAt"),
            }
        )
    projects.sort(key=lambda p: p.get("updatedAt") or "", reverse=True)
    return projects


def get_project(project_id: str) -> dict | None:
    path = _project_path(project_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_project(project: dict) -> dict:
    _ensure_dirs()
    project = dict(project)
    if not project.get("id"):
        project["id"] = _slugify(project.get("name", "")) + "-" + uuid.uuid4().hex[:6]
    project.setdefault("name", "Untitled")
    project.setdefault("width", 296)
    project.setdefault("height", 128)
    project.setdefault("nodes", [])
    project.setdefault("variables", [])
    project["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _project_path(project["id"]).write_text(
        json.dumps(project, indent=2, ensure_ascii=False), "utf-8"
    )
    return project


def delete_project(project_id: str) -> bool:
    path = _project_path(project_id)
    if path.exists():
        path.unlink()
        return True
    return False


def load_settings() -> dict:
    _ensure_dirs()
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(settings: dict) -> dict:
    _ensure_dirs()
    current = load_settings()
    current.update(settings)
    SETTINGS_FILE.write_text(
        json.dumps(current, indent=2, ensure_ascii=False), "utf-8"
    )
    return current


def effective_settings() -> dict:
    """Settings with environment variables as fallback."""
    settings = load_settings()
    return {
        "haUrl": settings.get("haUrl") or os.environ.get("HA_URL", ""),
        "haToken": settings.get("haToken") or os.environ.get("HA_TOKEN", ""),
        "deviceId": settings.get("deviceId", ""),
        "service": settings.get("service", "open_epaper_link.drawcustom"),
    }


def public_settings() -> dict:
    """Settings safe to send to the browser (token redacted)."""
    settings = effective_settings()
    token = settings.get("haToken") or ""
    return {
        "haUrl": settings.get("haUrl", ""),
        "deviceId": settings.get("deviceId", ""),
        "service": settings.get("service", ""),
        "hasToken": bool(token),
        "tokenSource": "env" if os.environ.get("HA_TOKEN") and not load_settings().get("haToken") else "settings",
    }