"""Simple JSON-file project storage."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
PROJECTS_DIR = DATA_DIR / "projects"
SETTINGS_FILE = DATA_DIR / "settings.json"

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")
# Project ids map 1:1 to file names, so only a safe, non-empty subset is valid.
# Anything else is rejected instead of silently rewritten, which used to map
# `!!!` to `.json` and `a.b` / `ab` to the same file.
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class InvalidProjectId(ValueError):
    pass


def _ensure_dirs() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", (name or "").strip().lower()).strip("-")
    return slug or "project"


def is_valid_id(project_id: str) -> bool:
    return bool(_ID_RE.fullmatch(project_id or ""))


def _project_path(project_id: str) -> Path:
    if not is_valid_id(project_id):
        raise InvalidProjectId(project_id)
    return PROJECTS_DIR / f"{project_id}.json"


def _atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    """Write via a temp file + rename so a crash never leaves half a JSON file."""
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(text, "utf-8")
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


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


def project_exists(project_id: str) -> bool:
    return is_valid_id(project_id) and _project_path(project_id).exists()


def get_project(project_id: str) -> dict | None:
    if not is_valid_id(project_id):
        return None
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
    if not is_valid_id(project.get("id") or ""):
        project["id"] = _slugify(project.get("name", "")) + "-" + uuid.uuid4().hex[:6]
    project.setdefault("name", "Untitled")
    project.setdefault("width", 296)
    project.setdefault("height", 128)
    project.setdefault("nodes", [])
    project.setdefault("variables", [])
    project["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _atomic_write(
        _project_path(project["id"]),
        json.dumps(project, indent=2, ensure_ascii=False),
    )
    return project


def delete_project(project_id: str) -> bool:
    if not is_valid_id(project_id):
        return False
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


def _norm_url(url: str | None) -> str:
    return (url or "").strip().rstrip("/").lower()


def save_settings(settings: dict) -> dict:
    """Merge and persist settings.

    The stored token is bound to the Home Assistant URL it was entered for.
    Without that, anyone who can reach the editor could point `haUrl` at their
    own server and have the next status check send them the token. So changing
    the URL without supplying a token in the same request drops the stored one.
    Returns the saved settings plus `tokenCleared` when that happened.
    """
    _ensure_dirs()
    current = load_settings()
    token_cleared = False
    if "haUrl" in settings and "haToken" not in settings:
        before = current.get("haUrl") or os.environ.get("HA_URL", "")
        after = settings["haUrl"] or os.environ.get("HA_URL", "")
        if _norm_url(before) != _norm_url(after):
            token_cleared = bool(current.pop("haToken", None)) or bool(os.environ.get("HA_TOKEN"))
    current.update(settings)
    _atomic_write(
        SETTINGS_FILE,
        json.dumps(current, indent=2, ensure_ascii=False),
        mode=0o600,  # holds a long-lived Home Assistant token
    )
    return {**current, "tokenCleared": token_cleared}


def effective_settings() -> dict:
    """Settings with environment variables as fallback.

    The `HA_TOKEN` environment token is only ever sent to `HA_URL`: if the URL
    was changed in the UI, a token has to be entered there as well.
    """
    settings = load_settings()
    env_url = os.environ.get("HA_URL", "")
    url = settings.get("haUrl") or env_url
    token = settings.get("haToken") or ""
    source = "settings" if token else "none"
    if not token and os.environ.get("HA_TOKEN") and _norm_url(url) == _norm_url(env_url):
        token = os.environ["HA_TOKEN"]
        source = "env"
    return {
        "haUrl": url,
        "haToken": token,
        "tokenSource": source,
        "deviceId": settings.get("deviceId", ""),
        "service": settings.get("service") or "open_epaper_link.drawcustom",
    }


def public_settings() -> dict:
    """Settings safe to send to the browser (token redacted)."""
    settings = effective_settings()
    return {
        "haUrl": settings["haUrl"],
        "deviceId": settings["deviceId"],
        "service": settings["service"],
        "hasToken": bool(settings["haToken"]),
        "tokenSource": settings["tokenSource"],
    }
