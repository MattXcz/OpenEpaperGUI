"""Minimal Home Assistant REST client."""

from __future__ import annotations

import httpx


class HomeAssistantError(RuntimeError):
    pass


class HomeAssistantClient:
    def __init__(self, base_url: str, token: str, timeout: float = 20.0) -> None:
        if not base_url:
            raise HomeAssistantError("Home Assistant URL is not configured.")
        if not token:
            raise HomeAssistantError("Home Assistant token is not configured.")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method, url, headers=self._headers, **kwargs
                )
        except httpx.HTTPError as exc:
            raise HomeAssistantError(f"Cannot reach Home Assistant: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:500]
            raise HomeAssistantError(
                f"Home Assistant returned {response.status_code}: {detail}"
            )
        return response

    async def ping(self) -> dict:
        response = await self._request("GET", "/api/")
        return response.json()

    async def list_entities(self, domain: str | None = None) -> list[dict]:
        response = await self._request("GET", "/api/states")
        states = response.json()
        if domain:
            prefix = f"{domain}."
            states = [s for s in states if s.get("entity_id", "").startswith(prefix)]
        return [
            {
                "entity_id": s.get("entity_id"),
                "state": s.get("state"),
                "name": (s.get("attributes") or {}).get("friendly_name"),
            }
            for s in states
        ]

    async def call_service(self, domain: str, service: str, data: dict) -> list:
        response = await self._request(
            "POST", f"/api/services/{domain}/{service}", json=data
        )
        try:
            return response.json()
        except ValueError:
            return []

    async def render_template(self, template: str) -> str:
        """Render a Jinja template through Home Assistant.

        ``POST /api/template`` returns rendered text, so this is the only way to
        evaluate a template against live entity state. The REST service
        endpoint does not do it for templates inside ``data``.
        """
        response = await self._request(
            "POST", "/api/template", json={"template": template}
        )
        return response.text
