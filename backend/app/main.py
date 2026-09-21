"""FastAPI application for the OpenEPaper GUI editor."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import storage
from .generator import generate_payload, generate_template, generate_yaml
from .ha_client import HomeAssistantClient, HomeAssistantError
from .schema import default_props, public_schema

FRONTEND_DIR = Path(
    os.environ.get("FRONTEND_DIR")
    or (Path(__file__).resolve().parents[2] / "frontend")
)

app = FastAPI(title="OpenEPaper GUI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Project(BaseModel):
    id: str | None = None
    name: str = "Untitled"
    width: int = 296
    height: int = 128
    background: str = "white"
    nodes: list[dict] = Field(default_factory=list)
    variables: list[dict] = Field(default_factory=list)


class Settings(BaseModel):
    haUrl: str | None = None
    haToken: str | None = None
    deviceId: str | None = None
    service: str | None = None


class PushRequest(BaseModel):
    project: Project
    deviceId: str | None = None
    service: str | None = None
    background: str | None = None
    dryRun: bool = False


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/schema")
async def schema() -> dict:
    return public_schema()


@app.get("/api/schema/defaults/{element_type}")
async def schema_defaults(element_type: str) -> dict:
    try:
        return {"type": element_type, "props": default_props(element_type)}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown type: {element_type}")


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
    storage.save_settings(payload)
    return storage.public_settings()


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
        raise HTTPException(status_code=502, detail=str(exc))


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

    project = request.project.model_dump()
    template = generate_template(project)

    data = {
        "device_id": device_id,
        "payload": template,
        "background": request.background or project.get("background", "white"),
    }
    if request.dryRun:
        data["dry-run"] = True

    try:
        client = HomeAssistantClient(settings["haUrl"], settings["haToken"])
        result = await client.call_service(domain, service_name, data)
    except HomeAssistantError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "service": service, "deviceId": device_id, "result": result}


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

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{path:path}")
    async def spa(path: str) -> FileResponse:
        candidate = FRONTEND_DIR / path
        if candidate.is_file():
            return FileResponse(str(candidate))
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