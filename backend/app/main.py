"""FastAPI application for the OpenEPaper GUI editor."""

from __future__ import annotations

import base64
import ipaddress
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import storage
from .generator import (
    collect_warnings,
    generate_payload,
    generate_template,
    generate_yaml,
)
from .ha_client import HomeAssistantClient, HomeAssistantError
from .render import RenderError, assets_available, render_payload
from .render.fonts import ASSETS_DIR
from .schema import FONTS, default_props, public_schema
from .templating import payload_from_rendered, validate_project

FRONTEND_DIR = Path(
    os.environ.get("FRONTEND_DIR")
    or (Path(__file__).resolve().parents[2] / "frontend")
)

app = FastAPI(title="OpenEPaper GUI", version="1.0.0")

# The backend serves the frontend, so no cross-origin access is needed by
# default. The app has no authentication, and a wildcard here would let any
# page the user happens to visit read their projects and push to their
# displays. Only set CORS_ORIGINS if you host the frontend separately.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _env_list(name: str) -> list[str]:
    return [item.strip().lower() for item in os.environ.get(name, "").split(",") if item.strip()]


# DNS rebinding protection. CORS does not help against a malicious page whose
# own hostname is re-pointed at this server: the browser then treats the app
# as same-origin. Such requests always carry the attacker's hostname in `Host`,
# so only accept hosts that cannot be attacker-controlled names: IP literals,
# `localhost`, typical LAN suffixes and whatever is listed in ALLOWED_HOSTS.
# `ALLOWED_HOSTS=*` switches the check off.
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS")
_LAN_SUFFIXES = (".local", ".lan", ".home", ".internal", ".home.arpa", ".localdomain")


def host_allowed(host_header: str) -> bool:
    if "*" in ALLOWED_HOSTS:
        return True
    host = (host_header or "").strip().lower()
    if host.startswith("["):  # [::1]:8099
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:
        host = host.rsplit(":", 1)[0]
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if host == "localhost" or "." not in host or host.endswith(_LAN_SUFFIXES):
        return True
    for allowed in ALLOWED_HOSTS:
        if allowed.startswith("*.") and host.endswith(allowed[1:]):
            return True
        if host == allowed:
            return True
    return False


@app.middleware("http")
async def check_host(request: Request, call_next):
    if not host_allowed(request.headers.get("host", "")):
        return PlainTextResponse(
            "Host not allowed. Add it to the ALLOWED_HOSTS environment variable.",
            status_code=400,
        )
    return await call_next(request)


# Services the push endpoint may call with the stored token. Without a limit,
# anyone who can reach the editor could call *any* Home Assistant service.
ALLOWED_SERVICE_DOMAINS = _env_list("ALLOWED_SERVICE_DOMAINS") or ["open_epaper_link"]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Project(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    name: str = Field(default="Untitled", max_length=200)
    width: int = Field(default=296, ge=1, le=4096)
    height: int = Field(default=128, ge=1, le=4096)
    background: str = Field(default="white", max_length=32)
    nodes: list[dict] = Field(default_factory=list, max_length=2000)
    variables: list[dict] = Field(default_factory=list, max_length=500)
    # drawcustom service options, sent with "Send to display".
    rotate: Literal[0, 90, 180, 270] = 0
    dither: Literal[0, 1, 2] = 2
    ttl: int = Field(default=60, ge=0, le=86400)


class Settings(BaseModel):
    haUrl: str | None = Field(default=None, max_length=500)
    haToken: str | None = Field(default=None, max_length=2000)
    deviceId: str | None = Field(default=None, max_length=200)
    service: str | None = Field(default=None, max_length=200)


class PushRequest(BaseModel):
    project: Project
    deviceId: str | None = None
    service: str | None = None
    background: str | None = None
    dryRun: bool = False


class PreviewRequest(BaseModel):
    """A preview request: either a project or an explicit payload.

    ``payload`` lets the editor preview exactly what it has on the canvas
    without a round trip through the generator; ``project`` is rendered through
    the generator so a preview can also be requested for a saved project.
    """

    project: Project | None = None
    payload: list[dict] | None = Field(default=None, max_length=2000)
    accent: Literal["red", "yellow"] = "red"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/schema")
async def schema() -> dict:
    return public_schema()


@app.get("/api/fonts/{name}")
async def font_file(name: str) -> FileResponse:
    """The display fonts, so the canvas draws text in the real typeface.

    Only the names in the schema are served; the path is never built from
    arbitrary input.
    """
    if name not in FONTS or not (ASSETS_DIR / name).exists():
        raise HTTPException(status_code=404, detail=f"Font {name!r} not available")
    return FileResponse(
        str(ASSETS_DIR / name),
        media_type="font/ttf",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/schema/defaults/{element_type}")
async def schema_defaults(element_type: str) -> dict:
    try:
        return {"type": element_type, "props": default_props(element_type)}
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Unknown type: {element_type}"
        ) from exc


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@app.get("/api/projects")
async def list_projects() -> list[dict]:
    return storage.list_projects()


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str) -> dict:
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.post("/api/projects")
async def create_project(project: Project) -> dict:
    return storage.save_project(project.model_dump())


@app.put("/api/projects/{project_id}")
async def update_project(project_id: str, project: Project) -> dict:
    if not storage.is_valid_id(project_id):
        raise HTTPException(status_code=400, detail="Invalid project id")
    if not storage.project_exists(project_id):
        # Create with POST; a PUT to a deleted project must not resurrect it.
        raise HTTPException(status_code=404, detail="Project not found")
    data = project.model_dump()
    data["id"] = project_id
    return storage.save_project(data)


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str) -> dict:
    if not storage.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"deleted": project_id}


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

@app.post("/api/generate/template")
async def generate_template_endpoint(project: Project) -> dict:
    data = project.model_dump()
    return {
        "template": generate_template(data),
        "yaml": generate_yaml(data),
        "payload": generate_payload(data),
        "warnings": collect_warnings(data),
    }


@app.post("/api/validate")
async def validate_endpoint(project: Project) -> dict:
    """Render the generated template and check the payload it produces.

    Uses Home Assistant when it is reachable so the check reflects live entity
    state, and falls back to a local sandbox otherwise. The response reports the
    failing stage (render / parse / elements) plus an excerpt and a list of
    per-element problems.
    """
    settings = storage.effective_settings()
    client: HomeAssistantClient | None = None
    if settings.get("haUrl") and settings.get("haToken"):
        client = HomeAssistantClient(settings["haUrl"], settings["haToken"])

    result = await validate_project(project.model_dump(), client)
    # The template is large and already available from /api/generate/template.
    result.pop("template", None)
    if result.get("payload") is not None:
        result["count"] = len(result["payload"])
        result.pop("payload", None)
    return result


@app.post("/api/preview")
async def preview_endpoint(request: PreviewRequest) -> dict:
    """Render a payload to a PNG with the real drawing code.

    Unlike the canvas (a design-time approximation), this uses the same fonts,
    colours, coordinates and Pillow calls the integration uses, so the result is
    pixel-accurate.

    A project is run through the generator *and then rendered* before drawing,
    because the payload contains Jinja expressions (`{{ states('sensor.x') }}`)
    that would otherwise reach the renderer as literal strings. Rendering uses
    Home Assistant when configured and the local sandbox otherwise.

    Returns the image as a data URI along with per-element ``errors`` and
    ``notes``. Problems do not fail the request: a preview that shows fifteen
    correct elements and one broken one is more useful than an error.
    """
    if not assets_available():
        raise HTTPException(
            status_code=503,
            detail="Font assets are not available. Run backend/scripts/fetch_assets.py "
                   "or rebuild the Docker image.",
        )

    width, height = 296, 128
    background, rotate = "white", 0
    render_notes: list[str] = []

    if request.project is not None:
        project = request.project.model_dump()
        background = project.get("background", "white")
        rotate = project.get("rotate", 0)
        width, height = project["width"], project["height"]

        settings = storage.effective_settings()
        client: HomeAssistantClient | None = None
        if settings.get("haUrl") and settings.get("haToken"):
            client = HomeAssistantClient(settings["haUrl"], settings["haToken"])

        check = await validate_project(project, client)
        if not check["ok"]:
            raise HTTPException(
                status_code=400,
                detail=f"The template must render before it can be previewed: {check['error']}",
            )
        payload = check["payload"]
        if check.get("haError"):
            render_notes.append(f"rendered locally, not by Home Assistant: {check['haError']}")
    elif request.payload is not None:
        payload = request.payload
    else:
        raise HTTPException(status_code=400, detail="Provide either 'project' or 'payload'.")

    try:
        png, errors, notes = render_payload(
            payload,
            width=width,
            height=height,
            accent=request.accent,
            background=background,
            rotate=rotate,
        )
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "image": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
        "width": width,
        "height": height,
        "elements": len(payload),
        "errors": errors,
        "notes": [*render_notes, *notes],
    }


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
async def get_settings() -> dict:
    return storage.public_settings()


@app.post("/api/settings")
async def update_settings(settings: Settings) -> dict:
    payload = {k: v for k, v in settings.model_dump().items() if v is not None}
    url = (payload.get("haUrl") or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Home Assistant URL must start with http:// or https://")
    saved = storage.save_settings(payload)
    return {**storage.public_settings(), "tokenCleared": saved["tokenCleared"]}


# ---------------------------------------------------------------------------
# Home Assistant
# ---------------------------------------------------------------------------

@app.get("/api/ha/status")
async def ha_status() -> dict:
    settings = storage.effective_settings()
    try:
        client = HomeAssistantClient(settings["haUrl"], settings["haToken"])
        info = await client.ping()
        return {"connected": True, "message": info.get("message", "API running")}
    except HomeAssistantError as exc:
        return {"connected": False, "message": str(exc)}


@app.get("/api/ha/entities")
async def ha_entities(domain: str | None = None) -> list[dict]:
    settings = storage.effective_settings()
    try:
        client = HomeAssistantClient(settings["haUrl"], settings["haToken"])
        return await client.list_entities(domain)
    except HomeAssistantError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/ha/push")
async def ha_push(request: PushRequest) -> dict:
    settings = storage.effective_settings()
    device_id = request.deviceId or settings.get("deviceId")
    if not device_id:
        raise HTTPException(status_code=400, detail="No target device configured.")

    service = request.service or settings.get("service") or "open_epaper_link.drawcustom"
    if "." not in service:
        raise HTTPException(status_code=400, detail=f"Invalid service: {service}")
    domain, service_name = service.split(".", 1)
    if domain.lower() not in ALLOWED_SERVICE_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail=f"Service domain '{domain}' is not allowed "
                   "(see ALLOWED_SERVICE_DOMAINS).",
        )

    project = request.project.model_dump()
    template = generate_template(project)

    try:
        client = HomeAssistantClient(settings["haUrl"], settings["haToken"])
    except HomeAssistantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # `imagegen/core.py` reads `payload` as a finished list of elements and never
    # renders Jinja itself, and /api/services does not render templates inside
    # `data` either. Rendering through Home Assistant first is therefore the only
    # way the tag receives a usable payload.
    try:
        rendered = await client.render_template(template)
    except HomeAssistantError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload, check = payload_from_rendered(rendered)
    if payload is None:
        raise HTTPException(
            status_code=400,
            detail=f"Generated template did not render to a valid payload: {check['error']}",
        )

    data = {
        "device_id": device_id,
        "payload": payload,
        "background": request.background or project.get("background", "white"),
        "rotate": project["rotate"],
        "dither": project["dither"],
        "ttl": project["ttl"],
    }
    if request.dryRun:
        data["dry-run"] = True

    try:
        result = await client.call_service(domain, service_name, data)
    except HomeAssistantError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "ok": True,
        "service": service,
        "deviceId": device_id,
        "elements": len(payload),
        "result": result,
    }


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

if FRONTEND_DIR.exists():
    @app.middleware("http")
    async def no_cache_static(request, call_next):
        """Serve freshly built assets so UI updates land without a hard refresh."""
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    # Every asset is referenced as /static/..., and there is no client-side
    # router, so a catch-all fallback is not needed. It used to be one, and it
    # joined the request path onto FRONTEND_DIR without checking where the
    # result landed: `GET /..%2f..%2fdata%2fsettings.json` read the saved
    # Home Assistant token straight off disk. StaticFiles does that check for
    # us, so unknown paths now correctly 404.
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))
else:  # pragma: no cover
    @app.get("/")
    async def index_missing() -> JSONResponse:
        return JSONResponse({"detail": "Frontend not found"}, status_code=500)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=True,
    )
