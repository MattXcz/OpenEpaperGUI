"""Render and validate generated drawcustom templates.

The editor emits a Home Assistant Jinja template. Home Assistant is the only
thing that can evaluate it against live entity state, so there are two render
paths:

* **Home Assistant** (``POST /api/template``) -- authoritative. Used by
  "Send to display" and by validation whenever Home Assistant is reachable.
* **Local sandbox** -- a Jinja environment with permissive stubs, used when
  Home Assistant is unconfigured or down. It cannot know entity states, so
  anything it cannot resolve renders as ``0``. The point is only to prove the
  template *renders* and yields a payload the integration will accept.

Validation runs in stages, and the failing stage is reported so the UI can
point at the right problem:

1. ``render``   -- Jinja failed to render the template.
2. ``parse``    -- the rendered text is not valid JSON.
3. ``elements`` -- the JSON is not a list of drawable elements.

Why this module exists: ``imagegen/core.py`` reads ``payload`` as a finished
list of elements and never renders Jinja itself, and the REST
``/api/services/...`` endpoint does not render templates passed in the request
body either. Sending the raw template therefore reaches the tag unrendered and
fails, so the push path renders first and sends the resulting list.
"""

from __future__ import annotations

import json
from typing import Any

from jinja2 import TemplateError
from jinja2.runtime import Undefined
from jinja2.sandbox import SandboxedEnvironment

from .generator import generate_template
from .schema import ELEMENT_TYPES_BY_NAME

# ---------------------------------------------------------------------------
# Required keys
# ---------------------------------------------------------------------------

# Mirrors the ``requires=`` decorators in
# custom_components/open_epaper_link/imagegen/*.py. The integration builds these
# into ``ElementType`` handlers and raises KeyError when one is missing, which
# surfaces as a per-element error and silently drops that element on the tag.
HANDLER_REQUIRES: dict[str, tuple[str, ...]] = {
    "text": ("x", "value"),
    "multiline": ("x", "value", "delimiter", "offset_y"),
    "line": ("x_start", "x_end"),
    "rectangle": ("x_start", "x_end", "y_start", "y_end"),
    "rectangle_pattern": (
        "x_start", "x_size", "y_start", "y_size",
        "x_repeat", "y_repeat", "x_offset", "y_offset",
    ),
    "polygon": ("points",),
    "circle": ("x", "y", "radius"),
    "ellipse": ("x_start", "x_end", "y_start", "y_end"),
    "arc": ("x", "y", "radius", "start_angle", "end_angle"),
    "icon": ("x", "y", "value", "size"),
    "icon_sequence": ("x", "y", "icons", "size"),
    "qrcode": ("x", "y", "data"),
    "dlimg": ("x", "y", "url", "xsize", "ysize"),
    "plot": ("data",),
    "progress_bar": ("x_start", "x_end", "y_start", "y_end", "progress"),
    "debug_grid": (),
}

# Keys that must be lists; passing a scalar would raise inside the handler.
_LIST_KEYS = {"points", "icons", "data"}

_MAX_ISSUES = 20
_EXCERPT_RADIUS = 60


# ---------------------------------------------------------------------------
# Permissive stubs for offline rendering
# ---------------------------------------------------------------------------

class PermissiveUndefined(Undefined):
    """An undefined value that behaves like ``0`` and never raises.

    Home Assistant owns the real values. For a static check we only need the
    template to render, so an unresolved name evaluates to zero and any
    attribute, item or call on it yields another permissive undefined.
    Rendering as ``""`` (Jinja's default) would produce invalid JSON in numeric
    slots such as ``"x": {{ offset }},``.
    """

    __slots__ = ()

    def __str__(self) -> str:
        return "0"

    def __repr__(self) -> str:
        return "0"

    def __int__(self) -> int:
        return 0

    def __float__(self) -> float:
        return 0.0

    def __index__(self) -> int:
        return 0

    def __round__(self, ndigits: int | None = None) -> int:
        return 0

    def __bool__(self) -> bool:
        return False

    def __len__(self) -> int:
        return 0

    def __iter__(self):
        return iter(())

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self

    def __getitem__(self, key: Any) -> Any:
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self

    def _arithmetic(self, other: Any = None) -> Any:
        return self

    __add__ = __radd__ = __sub__ = __rsub__ = _arithmetic
    __mul__ = __rmul__ = __truediv__ = __rtruediv__ = _arithmetic
    __floordiv__ = __rfloordiv__ = __mod__ = __rmod__ = _arithmetic
    __pow__ = __rpow__ = __lshift__ = __rlshift__ = _arithmetic

    def __neg__(self) -> Any:
        return self

    def __pos__(self) -> Any:
        return self

    def __abs__(self) -> Any:
        return self


def _stub(*args: Any, **kwargs: Any) -> PermissiveUndefined:
    """A stand-in for any Home Assistant template function."""
    return PermissiveUndefined()


def _stub_filter(value: Any, *args: Any, **kwargs: Any) -> PermissiveUndefined:
    """A stand-in for any Home Assistant/Jinja filter we do not know."""
    return PermissiveUndefined()


# Template functions Home Assistant exposes. Anything not listed here still
# resolves -- unknown *names* become PermissiveUndefined -- but registering the
# common ones keeps `.get()`-style chains readable and self-documenting.
_HA_GLOBALS = (
    "states", "state_attr", "is_state", "is_state_attr", "has_value",
    "expand", "device_entities", "device_id", "device_name",
    "area_entities", "area_id", "area_name", "labels",
    "now", "utcnow", "today_at", "as_timestamp", "as_datetime", "as_local",
    "relative_time", "timedelta", "strptime", "time_trigger",
    "float", "int", "floor", "ceil", "clamp", "iif", "distance", "closest",
    "this", "trigger", "wait", "apply", "pack", "unpack",
)


class _FallbackDict(dict):
    """A mapping that answers any key with a fallback.

    Jinja resolves filters and tests at compile time via ``.get(name)`` and
    fails the template when one is missing. Home Assistant provides filters the
    sandbox does not know, so unknown names resolve to a permissive stub
    instead of being a syntax error.
    """

    def __init__(self, fallback: Any, initial: dict | None = None) -> None:
        super().__init__(initial or {})
        self._fallback = fallback

    def __missing__(self, key: Any) -> Any:
        return self._fallback

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self:
            return super().get(key, default)
        return self._fallback


def build_local_env() -> SandboxedEnvironment:
    """A sandboxed Jinja environment that renders anything."""
    env = SandboxedEnvironment(
        undefined=PermissiveUndefined,
        autoescape=False,
        keep_trailing_newline=False,
    )
    env.filters = _FallbackDict(_stub_filter, env.filters)
    env.tests = _FallbackDict(lambda *a, **k: False, env.tests)
    env.globals.update({name: _stub for name in _HA_GLOBALS})
    return env


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

class RenderFailed(RuntimeError):
    """Raised when a template cannot be rendered at all."""


def render_locally(template: str) -> str:
    """Render with the local sandbox. Raises RenderFailed on a template error."""
    env = build_local_env()
    try:
        return env.from_string(template).render()
    except TemplateError as exc:
        raise RenderFailed(_describe_template_error(exc)) from exc
    except Exception as exc:
        # Runtime failures inside an expression (division by zero, a bad
        # attribute on a real value) are not TemplateError but still mean the
        # template cannot render.
        raise RenderFailed(f"{type(exc).__name__}: {exc}") from exc


async def render_with_ha(client: Any, template: str) -> str:
    """Render with Home Assistant. Raises the client's error on failure."""
    return await client.render_template(template)


def _describe_template_error(exc: TemplateError) -> str:
    """Add line information to a Jinja error when it carries any."""
    message = str(exc).split("\n", 1)[0].strip()
    lineno = getattr(exc, "lineno", None)
    if lineno:
        return f"{message} (line {lineno})"
    return message


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------

def _excerpt(text: str, position: int, radius: int = _EXCERPT_RADIUS) -> str:
    """A snippet around ``position`` with a caret under the offending column.

    The caret is placed on the line that actually contains the error, which is
    not necessarily the last line of the snippet.
    """
    position = max(0, min(position, len(text)))
    start = max(0, position - radius)
    end = min(len(text), position + radius)

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    body = prefix + text[start:end] + suffix

    # Offset of the error within the snippet.
    offset = len(prefix) + (position - start)

    # The snippet line containing the error, and the column within it.
    line_start = body.rfind("\n", 0, offset) + 1
    line_end = body.find("\n", offset)
    if line_end == -1:
        line_end = len(body)
    column = offset - line_start

    caret = " " * max(0, column) + "^"
    return body[: line_end] + "\n" + caret + body[line_end:]


def _check_element(index: int, element: Any, issues: list[str]) -> None:
    number = index + 1
    if not isinstance(element, dict):
        issues.append(f"Element {number}: expected an object, got {type(element).__name__}")
        return

    element_type = element.get("type")
    if not element_type:
        issues.append(f"Element {number}: missing required key 'type'")
        return
    if element_type not in ELEMENT_TYPES_BY_NAME:
        issues.append(f"Element {number}: unknown type '{element_type}'")
        return

    for key in HANDLER_REQUIRES.get(element_type, ()):
        if key not in element:
            issues.append(
                f"Element {number} (type '{element_type}'): missing required key '{key}'"
            )

    for key in _LIST_KEYS & element.keys():
        if not isinstance(element[key], list):
            issues.append(
                f"Element {number} (type '{element_type}'): '{key}' must be a list, "
                f"got {type(element[key]).__name__}"
            )


def parse_rendered(rendered: str) -> dict:
    """Parse rendered output into a payload and report any problem.

    Returns ``{ok, stage, error, excerpt, issues, payload}``. ``stage`` is the
    stage that failed, or ``"ok"`` when everything passed.
    """
    text = (rendered or "").strip()

    if not text:
        return {
            "ok": False,
            "stage": "render",
            "error": "The template rendered to an empty string.",
            "excerpt": None,
            "issues": [],
            "payload": None,
        }

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "stage": "parse",
            "error": f"Rendered output is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})",
            "excerpt": _excerpt(text, exc.pos),
            "issues": [],
            "payload": None,
        }

    if not isinstance(payload, list):
        return {
            "ok": False,
            "stage": "elements",
            "error": f"Expected a JSON array of elements, got {type(payload).__name__}.",
            "excerpt": _excerpt(text, 0),
            "issues": [],
            "payload": None,
        }

    issues: list[str] = []
    for index, element in enumerate(payload):
        _check_element(index, element, issues)

    if len(issues) > _MAX_ISSUES:
        # Truncate exactly: a single element can add several issues at once, so
        # stopping mid-collection would let the list overshoot the cap.
        issues = issues[:_MAX_ISSUES] + ["… further problems omitted"]

    if issues:
        return {
            "ok": False,
            "stage": "elements",
            "error": issues[0],
            "excerpt": None,
            "issues": issues,
            "payload": payload,
        }

    return {
        "ok": True,
        "stage": "ok",
        "error": None,
        "excerpt": None,
        "issues": [],
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# High level entry points
# ---------------------------------------------------------------------------

async def validate_project(project: dict, client: Any = None) -> dict:
    """Generate, render and validate a project's template.

    ``client`` is a HomeAssistantClient, or None to render locally. Falls back
    to the local sandbox if Home Assistant cannot be reached, so the editor
    still reports template and JSON problems while offline. ``source`` says
    which path actually produced the output.
    """
    template = generate_template(project)

    source = "local"
    rendered: str | None = None
    ha_error: str | None = None

    if client is not None:
        try:
            rendered = await client.render_template(template)
            source = "ha"
        except Exception as exc:  # noqa: BLE001 - see below
            # Deliberately broad. The fallback exists so the editor still
            # reports template and JSON problems while Home Assistant is
            # unreachable, misconfigured, or returning its own errors, and
            # those surface as several unrelated exception types.
            ha_error = str(exc)

    if rendered is None:
        try:
            rendered = render_locally(template)
        except RenderFailed as exc:
            return {
                "ok": False,
                "source": source,
                "stage": "render",
                "error": str(exc),
                "excerpt": _excerpt(template, 0),
                "issues": [],
                "template": template,
            }

    result = parse_rendered(rendered)
    result["source"] = source
    result["template"] = template
    if result["payload"] is not None:
        result["count"] = len(result["payload"])
    result["rendered"] = rendered if not result["ok"] else None
    if ha_error:
        result["haError"] = ha_error
    return result


def payload_from_rendered(rendered: str) -> tuple[list | None, dict]:
    """Convenience wrapper for the push path."""
    result = parse_rendered(rendered)
    return result["payload"] if result["ok"] else None, result
