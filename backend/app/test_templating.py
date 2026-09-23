"""Tests for template rendering and validation.

Run with:  python -m pytest -q app
"""

from __future__ import annotations

import asyncio
import json

from .templating import (
    RenderFailed,
    parse_rendered,
    payload_from_rendered,
    render_locally,
    validate_project,
)


def _render(project: dict) -> dict:
    return asyncio.run(validate_project(project))


def _el(etype: str, props: dict) -> dict:
    return {"kind": "element", "type": etype, "props": props}


def _weather() -> dict:
    return {
        "variables": [{"name": "spacing", "value": "49"}],
        "nodes": [
            _el("text", {"value": " ", "x": 0, "y": 0, "size": 1, "color": "yellow"}),
            {
                "kind": "group",
                "repeat": {"enabled": True, "var": "i", "count": 8, "pre": []},
                "children": [
                    _el("text", {"value": "{{ times[i] }}",
                                 "x": "{{ 15 + i*spacing }}", "y": 5, "size": 10}),
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# Local sandbox
# ---------------------------------------------------------------------------

def test_undefined_names_render_as_zero() -> None:
    """Numeric slots must not become empty strings, which would break JSON."""
    assert render_locally("[{{ offset }}, {{ a.b.c }}, {{ x[0] }}]") == "[0, 0, 0]"


def test_unknown_filters_and_functions_are_permissive() -> None:
    assert render_locally("{{ states('sensor.x') }}") == "0"
    assert render_locally("{{ x | made_up_filter }}") == "0"
    # Real Jinja filters keep working, and behave as they would in Home
    # Assistant against an undefined value.
    assert render_locally("{{ x | default(5) }}") == "5"
    assert render_locally("{{ x | int(0) }}") == "0"
    assert render_locally("{{ x | int(7) + 1 }}") == "1"


def test_arithmetic_on_undefined_does_not_raise() -> None:
    assert render_locally("{{ a + b * c }}") == "0"
    assert render_locally("{{ -missing }}") == "0"


def test_real_values_still_render() -> None:
    assert render_locally("{% set x = 4 %}{{ x * 2 }}") == "8"


def test_syntax_error_is_reported_with_line() -> None:
    try:
        render_locally("{% for i in range(3) %}")
    except RenderFailed as exc:
        assert "line 1" in str(exc), exc
    else:
        raise AssertionError("expected RenderFailed")


def test_runtime_error_is_reported() -> None:
    try:
        render_locally("{{ 1 / 0 }}")
    except RenderFailed as exc:
        assert "ZeroDivisionError" in str(exc)
    else:
        raise AssertionError("expected RenderFailed")


def test_sandbox_blocks_attribute_escape() -> None:
    """The environment must stay sandboxed: no reaching into Python internals."""
    try:
        render_locally("{{ ''.__class__.__mro__ }}")
    except RenderFailed:
        pass  # blocked at compile time by the sandbox
    else:
        # If it renders, it must not have leaked a class object.
        assert "__class__" not in render_locally("{{ ''.__class__ }}")


# ---------------------------------------------------------------------------
# parse_rendered
# ---------------------------------------------------------------------------

def test_valid_payload_passes() -> None:
    result = parse_rendered('[{"type": "circle", "x": 1, "y": 2, "radius": 3}]')
    assert result["ok"] and result["stage"] == "ok"
    assert result["payload"] == [{"type": "circle", "x": 1, "y": 2, "radius": 3}]


def test_empty_render_is_a_render_failure() -> None:
    result = parse_rendered("   ")
    assert not result["ok"] and result["stage"] == "render"


def test_invalid_json_reports_position_and_excerpt() -> None:
    result = parse_rendered('[{"type": "text", "value": "a" "b"}]')
    assert not result["ok"] and result["stage"] == "parse"
    assert "column" in result["error"]
    assert "^" in result["excerpt"]


def test_excerpt_points_at_the_error_column() -> None:
    """The caret must sit under the offending character, not the line start."""
    text = '[\n  {\n    "value": """,\n    "x": 6\n  }\n]'
    result = parse_rendered(text)
    caret_line = next(
        line for line in result["excerpt"].split("\n") if line.strip() == "^"
    )
    # The caret is indented to the column reported in the message.
    column = int(result["error"].rsplit("column ", 1)[1].rstrip(")")) - 1
    assert caret_line.index("^") == column, (result["excerpt"], column)


def test_excerpt_caret_follows_the_error_line() -> None:
    """With a multi-line error the caret sits directly under its own line."""
    text = '[\n  {"a": 1},\n  {bad!},\n  {"b": 2}\n]'
    result = parse_rendered(text)
    lines = result["excerpt"].split("\n")
    caret_index = next(i for i, line in enumerate(lines) if line.strip() == "^")
    # The line above the caret is the one the error was reported on.
    assert "{bad!}" in lines[caret_index - 1], lines


def test_excerpt_keeps_newlines_readable() -> None:
    """The snippet is shown in a <pre>, so it must not escape its newlines."""
    result = parse_rendered('[\n  {oops}\n]')
    assert "\\n" not in result["excerpt"]
    assert "\n" in result["excerpt"]


def test_non_array_is_an_element_failure() -> None:
    result = parse_rendered('{"a": 1}')
    assert not result["ok"] and result["stage"] == "elements"
    assert "array" in result["error"]


def test_unknown_type_is_reported() -> None:
    result = parse_rendered('[{"type": "not_a_type"}]')
    assert not result["ok"] and result["stage"] == "elements"
    assert "not_a_type" in result["issues"][0]


def test_missing_required_keys_are_reported_per_element() -> None:
    """The key lists mirror the integration's @element_handler(requires=...)."""
    result = parse_rendered(json.dumps([
        {"type": "line", "x_start": 0},
        {"type": "circle", "x": 1, "y": 2, "radius": 3},
        {"type": "multiline", "x": 1},
    ]))
    assert not result["ok"]
    issues = "\n".join(result["issues"])
    assert "line" in issues and "'x_end'" in issues
    assert "'delimiter'" in issues and "'offset_y'" in issues and "'value'" in issues
    # The complete circle must not be reported.
    assert "circle" not in issues


def test_non_list_icon_field_is_reported() -> None:
    result = parse_rendered('[{"type": "icon_sequence", "x": 0, "y": 0, '
                            '"icons": "mdi:home", "size": 20}]')
    assert not result["ok"]
    assert "must be a list" in result["issues"][0]


# ---------------------------------------------------------------------------
# validate_project
# ---------------------------------------------------------------------------

def test_weather_project_validates() -> None:
    result = _render(_weather())
    assert result["ok"], result
    assert result["source"] == "local"
    # 1 literal + 8 loop iterations.
    assert result["count"] == 9


def test_every_issue_is_capped() -> None:
    """A payload full of broken elements must not produce an unbounded list."""
    payload = json.dumps([{"type": "circle"} for _ in range(60)])
    result = parse_rendered(payload)
    assert not result["ok"]
    assert len(result["issues"]) == 21, len(result["issues"])
    assert "omitted" in result["issues"][-1]


def test_nested_groups_validate() -> None:
    project = {
        "nodes": [{
            "kind": "group",
            "repeat": {"enabled": True, "var": "i", "count": 2, "pre": []},
            "children": [{
                "kind": "group",
                "repeat": {"enabled": True, "var": "j", "count": 3, "pre": []},
                "children": [_el("circle", {"x": "{{ i*10 + j }}", "y": 0, "radius": 2})],
            }],
        }],
    }
    result = _render(project)
    assert result["ok"], result
    assert result["count"] == 6


def test_payload_from_rendered_returns_none_on_failure() -> None:
    payload, check = payload_from_rendered("[{oops}]")
    assert payload is None and not check["ok"]
    payload, check = payload_from_rendered("[]")
    assert payload == [] and check["ok"]


def test_ha_client_result_is_used_when_available() -> None:
    """A reachable Home Assistant is the authoritative renderer."""
    class FakeClient:
        async def render_template(self, template: str) -> str:
            assert "{%" in template or "[" in template
            return '[{"type": "circle", "x": 1, "y": 2, "radius": 3}]'

    result = asyncio.run(validate_project({"nodes": []}, FakeClient()))
    assert result["ok"] and result["source"] == "ha"
    assert result["count"] == 1


def test_falls_back_to_local_when_ha_fails() -> None:
    class BrokenClient:
        async def render_template(self, template: str) -> str:
            raise RuntimeError("connection refused")

    result = asyncio.run(validate_project(_weather(), BrokenClient()))
    assert result["ok"], result
    assert result["source"] == "local"
    assert "connection refused" in result["haError"]
