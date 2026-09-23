"""HTTP-level regression tests.

Run with:  python -m app.test_api   (from the backend directory)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from . import main, storage

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
