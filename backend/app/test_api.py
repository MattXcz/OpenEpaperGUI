"""HTTP-level regression tests.

Run with:  python -m app.test_api   (from the backend directory)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from . import main, storage
from .render import assets_available

ENV_KEYS = ("HA_URL", "HA_TOKEN")


def _fresh() -> TestClient:
    """A client with an empty data dir and no HA environment."""
    data = Path(tempfile.mkdtemp())
    storage.DATA_DIR = data
    storage.PROJECTS_DIR = data / "projects"
    storage.SETTINGS_FILE = data / "settings.json"
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    return TestClient(main.app)


# ---------------------------------------------------------------------------
# Static files / host check
# ---------------------------------------------------------------------------

def test_path_traversal_is_blocked() -> None:
    client = _fresh()
    for url in ("/..%2f..%2fdata%2fsettings.json", "/static/..%2f..%2fetc%2fpasswd"):
        assert client.get(url).status_code == 404, url


def test_rebinding_hosts_are_rejected() -> None:
    client = _fresh()
    ok = ["localhost:8099", "127.0.0.1:8099", "192.168.1.20", "[::1]:8099",
          "epaper.local", "nas", "homeassistant.home.arpa:8099"]
    for host in ok:
        assert client.get("/api/health", headers={"host": host}).status_code == 200, host
    assert client.get("/api/health", headers={"host": "evil.example.com"}).status_code == 400


def test_allowed_hosts_env() -> None:
    client = _fresh()
    main.ALLOWED_HOSTS[:] = ["epaper.example.com", "*.mydomain.net"]
    try:
        for host in ("epaper.example.com", "a.mydomain.net:443"):
            assert client.get("/api/health", headers={"host": host}).status_code == 200, host
        assert client.get("/api/health", headers={"host": "mydomain.net.evil.com"}).status_code == 400
    finally:
        main.ALLOWED_HOSTS[:] = []


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def test_invalid_project_ids() -> None:
    client = _fresh()
    assert client.put("/api/projects/!!!", json={"name": "x"}).status_code == 400
    assert client.get("/api/projects/a.b").status_code == 404
    assert client.delete("/api/projects/a.b").status_code == 404
    assert not storage.PROJECTS_DIR.exists() or not list(storage.PROJECTS_DIR.glob("*.json"))


def test_put_does_not_create() -> None:
    client = _fresh()
    assert client.put("/api/projects/ghost", json={"name": "x"}).status_code == 404
    created = client.post("/api/projects", json={"name": "Real"}).json()
    response = client.put(f"/api/projects/{created['id']}", json={"name": "Renamed"})
    assert response.status_code == 200 and response.json()["name"] == "Renamed"


def test_project_limits() -> None:
    client = _fresh()
    assert client.post("/api/projects", json={"width": 10**9}).status_code == 422
    assert client.post("/api/projects", json={"height": 0}).status_code == 422


def test_generate_reports_warnings() -> None:
    client = _fresh()
    nested = {"kind": "group", "name": "outer", "repeat": {"enabled": True, "count": 2},
              "children": [{"kind": "group", "name": "inner", "children": []}]}
    body = client.post("/api/generate/template", json={"nodes": [nested]}).json()
    assert body["warnings"] and "inner" in body["warnings"][0], body


# ---------------------------------------------------------------------------
# Settings / token handling
# ---------------------------------------------------------------------------

def test_changing_url_drops_stored_token() -> None:
    client = _fresh()
    client.post("/api/settings", json={"haUrl": "http://ha.local:8123", "haToken": "secret"})
    assert storage.effective_settings()["haToken"] == "secret"

    # Same URL (trailing slash, case) keeps the token.
    body = client.post("/api/settings", json={"haUrl": "http://HA.local:8123/"}).json()
    assert body["hasToken"] and not body["tokenCleared"], body

    body = client.post("/api/settings", json={"haUrl": "http://attacker.example"}).json()
    assert not body["hasToken"] and body["tokenCleared"], body
    assert storage.effective_settings()["haToken"] == ""


def test_env_token_is_only_sent_to_env_url() -> None:
    client = _fresh()
    os.environ["HA_URL"] = "http://ha.local:8123"
    os.environ["HA_TOKEN"] = "env-secret"
    try:
        assert storage.effective_settings()["haToken"] == "env-secret"
        client.post("/api/settings", json={"haUrl": "http://attacker.example"})
        assert storage.effective_settings()["haToken"] == ""
    finally:
        for key in ENV_KEYS:
            os.environ.pop(key, None)


def test_settings_url_must_be_http() -> None:
    client = _fresh()
    assert client.post("/api/settings", json={"haUrl": "file:///etc/passwd"}).status_code == 400


def test_settings_file_is_private() -> None:
    client = _fresh()
    client.post("/api/settings", json={"haUrl": "http://ha.local", "haToken": "t"})
    assert (storage.SETTINGS_FILE.stat().st_mode & 0o777) == 0o600


def test_push_rejects_foreign_service_domains() -> None:
    client = _fresh()
    response = client.post("/api/ha/push", json={
        "project": {}, "deviceId": "x", "service": "homeassistant.stop",
    })
    assert response.status_code == 400 and "not allowed" in response.json()["detail"]


def test_push_sends_service_options() -> None:
    client = _fresh()
    client.post("/api/settings", json={"haUrl": "http://ha.local", "haToken": "t"})
    calls = []
    rendered = []

    async def fake_render(self, template):
        rendered.append(template)
        return '[{"type": "circle", "x": 1, "y": 2, "radius": 3}]'

    async def fake_call(self, domain, service, data):
        calls.append((domain, service, data))
        return []

    original_render = main.HomeAssistantClient.render_template
    original = main.HomeAssistantClient.call_service
    main.HomeAssistantClient.render_template = fake_render
    main.HomeAssistantClient.call_service = fake_call
    try:
        response = client.post("/api/ha/push", json={
            "project": {"rotate": 90, "dither": 0, "ttl": 300}, "deviceId": "abc",
        })
        assert response.status_code == 200, response.text
        data = calls[0][2]
        assert (data["rotate"], data["dither"], data["ttl"]) == (90, 0, 300), data
        response = client.post("/api/ha/push", json={"project": {}, "deviceId": "abc"})
        data = calls[1][2]
        assert (data["rotate"], data["dither"], data["ttl"]) == (0, 2, 60), data
    finally:
        main.HomeAssistantClient.render_template = original_render
        main.HomeAssistantClient.call_service = original
    assert client.post("/api/ha/push", json={
        "project": {"rotate": 45}, "deviceId": "abc",
    }).status_code == 422


def test_push_renders_before_sending() -> None:
    """The integration never renders Jinja, so the payload must arrive as a list."""
    client = _fresh()
    client.post("/api/settings", json={"haUrl": "http://ha.local", "haToken": "t"})
    sent = []
    templates = []

    async def fake_render(self, template):
        templates.append(template)
        return '[{"type": "text", "value": "hi", "x": 0, "y": 0}]'

    async def fake_call(self, domain, service, data):
        sent.append(data)
        return []

    original_render = main.HomeAssistantClient.render_template
    original = main.HomeAssistantClient.call_service
    main.HomeAssistantClient.render_template = fake_render
    main.HomeAssistantClient.call_service = fake_call
    try:
        response = client.post("/api/ha/push", json={"project": {}, "deviceId": "abc"})
        assert response.status_code == 200, response.text
        assert templates and "{%" in templates[0] or "[" in templates[0]
        # A list, not the raw template string.
        assert isinstance(sent[0]["payload"], list), sent[0]["payload"]
        assert sent[0]["payload"][0]["type"] == "text"
        assert response.json()["elements"] == 1
    finally:
        main.HomeAssistantClient.render_template = original_render
        main.HomeAssistantClient.call_service = original


def test_push_rejects_unrenderable_template() -> None:
    client = _fresh()
    client.post("/api/settings", json={"haUrl": "http://ha.local", "haToken": "t"})
    calls = []

    async def fake_render(self, template):
        return "not json at all"

    async def fake_call(self, domain, service, data):
        calls.append(data)
        return []

    original_render = main.HomeAssistantClient.render_template
    original = main.HomeAssistantClient.call_service
    main.HomeAssistantClient.render_template = fake_render
    main.HomeAssistantClient.call_service = fake_call
    try:
        response = client.post("/api/ha/push", json={"project": {}, "deviceId": "abc"})
        assert response.status_code == 400, response.text
        assert "not render" in response.json()["detail"]
        assert not calls, "nothing must be sent when the template is invalid"
    finally:
        main.HomeAssistantClient.render_template = original_render
        main.HomeAssistantClient.call_service = original


# ---------------------------------------------------------------------------
# Validation endpoint
# ---------------------------------------------------------------------------

def test_validate_ok() -> None:
    client = _fresh()
    body = client.post("/api/validate", json={"nodes": [
        {"kind": "element", "type": "circle", "props": {"x": 1, "y": 2, "radius": 3}},
    ]}).json()
    assert body["ok"] and body["stage"] == "ok", body
    assert body["count"] == 1
    assert "template" not in body, "the template is served by /api/generate/template"


def test_validate_reports_element_problems() -> None:
    """An emptied required field is omitted by the generator and must be caught."""
    client = _fresh()
    body = client.post("/api/validate", json={"nodes": [
        {"kind": "element", "type": "line", "props": {"x_start": 0, "x_end": ""}},
    ]}).json()
    assert not body["ok"], body
    assert body["stage"] == "elements", body
    assert any("x_end" in issue for issue in body["issues"]), body


def test_validate_skips_ha_when_unconfigured() -> None:
    client = _fresh()
    body = client.post("/api/validate", json={"nodes": []}).json()
    assert body["ok"] and body["source"] == "local"


# ---------------------------------------------------------------------------
# Pixel preview
# ---------------------------------------------------------------------------

requires_assets = pytest.mark.skipif(
    not assets_available(),
    reason="font assets missing; run backend/scripts/fetch_assets.py",
)


@requires_assets
def test_preview_accepts_an_explicit_payload() -> None:
    client = _fresh()
    response = client.post("/api/preview", json={"payload": [
        {"type": "circle", "x": 20, "y": 20, "radius": 10, "fill": "red"},
    ]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["image"].startswith("data:image/png;base64,")
    assert body["elements"] == 1
    assert body["errors"] == []


@requires_assets
def test_preview_renders_the_project_template_first() -> None:
    """Templated values must be resolved before drawing, not drawn literally."""
    client = _fresh()
    body = client.post("/api/preview", json={
        "project": {
            "width": 200,
            "height": 100,
            "nodes": [
                {"kind": "element", "type": "text",
                 "props": {"value": "{{ 1 + 1 }}", "x": 2, "y": 2, "size": 20}},
                {"kind": "element", "type": "progress_bar",
                 "props": {"x_start": 0, "y_start": 50, "x_end": 100, "y_end": 70,
                           "progress": "{{ 25 + 25 }}"}},
            ],
        },
    }).json()
    assert body["errors"] == [], body
    assert body["elements"] == 2


@requires_assets
def test_preview_rejects_a_template_that_does_not_render() -> None:
    client = _fresh()
    response = client.post("/api/preview", json={
        "project": {"width": 200, "height": 100, "nodes": [
            {"kind": "element", "type": "line",
             "props": {"x_start": 0, "x_end": ""}},
        ]},
    })
    assert response.status_code == 400, response.text
    assert "render" in response.json()["detail"]


@requires_assets
def test_preview_reports_element_problems_without_failing() -> None:
    client = _fresh()
    body = client.post("/api/preview", json={"payload": [
        {"type": "circle", "x": 1},
        {"type": "rectangle", "x_start": 0, "x_end": 10, "y_start": 0, "y_end": 10,
         "fill": "black"},
    ]}).json()
    # The incomplete circle is reported by key, and the request still succeeds.
    assert body["errors"], body
    assert "circle" in body["errors"][0] and "missing required key" in body["errors"][0]
    assert body["elements"] == 2


@requires_assets
def test_preview_requires_a_source() -> None:
    client = _fresh()
    response = client.post("/api/preview", json={})
    assert response.status_code == 400
    assert "project" in response.json()["detail"] or "payload" in response.json()["detail"]


def test_preview_rejects_an_unknown_accent() -> None:
    client = _fresh()
    response = client.post("/api/preview", json={"payload": [], "accent": "purple"})
    assert response.status_code == 422


def _run() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    _run()
