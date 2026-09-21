"""Render a generated template with Jinja and assert the result is valid JSON.

Run with:  python -m app.test_generator   (from the backend directory)
"""

from __future__ import annotations

import json

from jinja2 import Environment

from .generator import generate_template

ICON_MAP = {"sunny": "mdi:weather-sunny", "rainy": "mdi:weather-rainy"}


def _context() -> dict:
    return {
        "times": [f"{6 + i}:00" for i in range(8)],
        "temps": [10 + i for i in range(8)],
        "forecast": [{"condition": "sunny" if i % 2 else "rainy"} for i in range(8)],
        "icon_map": ICON_MAP,
        "nadpisy": ["A", "B", "C", "D"],
        "offset_0": 110, "offset_1": 130, "offset_2": 150,
        "offset_3": 170, "offset_4": 190, "offset_5": 210,
    }


def _render(template: str) -> list:
    env = Environment()
    env.globals["states"] = lambda entity: "42"
    rendered = env.from_string(template).render(**_context())
    return json.loads(rendered)


def _weather_project() -> dict:
    def el(node_id, etype, props):
        return {"id": node_id, "kind": "element", "type": etype, "props": props}

    return {
        "name": "Weather",
        "width": 296,
        "height": 128,
        "variables": [{"name": "spacing", "value": "49"}],
        "nodes": [
            el("a", "text", {"value": " ", "x": 0, "y": 0, "size": 1, "color": "yellow"}),
            {
                "id": "g1", "kind": "group",
                "repeat": {"enabled": True, "var": "i", "count": 8, "pre": []},
                "children": [
                    el("b", "text", {"value": "{{ times[i] }}", "x": "{{ 15 + i*spacing }}", "y": 5, "size": 10}),
                    el("c", "icon", {
                        "value": "{{ icon_map.get(forecast[i].condition,'mdi:emoticon-happy') }}",
                        "x": "{{ 5 + i*spacing }}", "y": 10, "size": 50,
                    }),
                    el("d", "text", {"value": "{{ temps[i] }}°", "x": "{{ 20 + i*spacing }}", "y": 58, "size": 24, "color": "yellow"}),
                ],
            },
            {
                "id": "g2", "kind": "group",
                "repeat": {
                    "enabled": True, "var": "i", "count": 4,
                    "pre": ["offsets = [offset_0, offset_1, offset_2, offset_3, offset_4, offset_5]"],
                },
                "children": [
                    el("e", "multiline", {
                        "value": "•{{nadpisy[i]}}|", "delimiter": "|", "offset_y": 20,
                        "x": 2, "y": "{{ offsets[i] }}", "size": 18,
                    }),
                ],
            },
        ],
    }


def test_weather_matches_reference() -> None:
    """The generated template renders to the expected element list."""
    payload = _render(generate_template(_weather_project()))

    assert len(payload) == 1 + 8 * 3 + 4, f"unexpected element count: {len(payload)}"

    assert payload[0] == {"type": "text", "value": " ", "x": 0, "y": 0, "size": 1, "color": "yellow"}

    first = payload[1]
    assert first == {"type": "text", "value": "6:00", "x": 15, "y": 5, "size": 10}, first

    icon = payload[2]
    assert icon["value"] == "mdi:weather-rainy", icon
    assert icon["x"] == 5 and icon["y"] == 10 and icon["size"] == 50

    temp = payload[3]
    assert temp["value"] == "10°" and temp["x"] == 20 and temp["color"] == "yellow"

    # Second loop iteration must shift by `spacing`.
    assert payload[4]["x"] == 15 + 49, payload[4]

    # Multiline rows use the offsets set before the loop.
    row = payload[25]
    assert row["type"] == "multiline" and row["y"] == 110, row


def test_group_first_has_no_leading_comma() -> None:
    """A repeat group placed first must not emit a leading comma."""
    project = {
        "name": "First", "width": 296, "height": 128, "variables": [],
        "nodes": [{
            "id": "g", "kind": "group",
            "repeat": {"enabled": True, "var": "i", "count": 3, "pre": []},
            "children": [
                {"id": "c", "kind": "element", "type": "circle",
                 "props": {"x": "{{ i * 10 + 20 }}", "y": 20, "radius": 5}},
            ],
        }],
    }
    payload = _render(generate_template(project))
    assert len(payload) == 3, payload
    assert [item["x"] for item in payload] == [20, 30, 40], payload


def test_single_element() -> None:
    project = {
        "name": "One", "width": 296, "height": 128, "variables": [],
        "nodes": [{"id": "a", "kind": "element", "type": "circle",
                   "props": {"x": 50, "y": 50, "radius": 20}}],
    }
    payload = _render(generate_template(project))
    assert payload == [{"type": "circle", "x": 50, "y": 50, "radius": 20}], payload


def test_empty_project() -> None:
    project = {"name": "Empty", "width": 296, "height": 128, "variables": [], "nodes": []}
    assert _render(generate_template(project)) == []


def test_hidden_elements_are_skipped() -> None:
    project = {
        "name": "Hidden", "width": 296, "height": 128, "variables": [],
        "nodes": [
            {"id": "a", "kind": "element", "type": "circle",
             "props": {"x": 10, "y": 10, "radius": 5, "visible": False}},
            {"id": "b", "kind": "element", "type": "circle",
             "props": {"x": 30, "y": 30, "radius": 5}},
        ],
    }
    payload = _render(generate_template(project))
    assert payload == [{"type": "circle", "x": 30, "y": 30, "radius": 5}], payload


def test_colors_and_shapes() -> None:
    project = {
        "name": "Shapes", "width": 296, "height": 128, "variables": [],
        "nodes": [
            {"id": "r", "kind": "element", "type": "rectangle", "props": {
                "x_start": 0, "x_end": 50, "y_start": 0, "y_end": 30,
                "fill": "red", "outline": "black", "width": 2, "radius": 4, "corners": "all",
            }},
            {"id": "p", "kind": "element", "type": "polygon", "props": {
                "points": [[0, 0], [10, 0], [10, 10]], "fill": None, "outline": "accent", "width": 1,
            }},
            {"id": "pb", "kind": "element", "type": "progress_bar", "props": {
                "x_start": 0, "y_start": 0, "x_end": 100, "y_end": 10,
                "progress": "{{ states('sensor.battery')|int(0) }}",
            }},
        ],
    }
    payload = _render(generate_template(project))
    assert payload[0]["fill"] == "red" and payload[0]["radius"] == 4
    # `fill: null` is the documented default, so it is omitted entirely.
    assert "fill" not in payload[1], payload[1]
    assert payload[1]["outline"] == "accent"
    assert payload[1]["points"] == [[0, 0], [10, 0], [10, 10]], payload[1]
    # A Jinja progress expression must survive rendering as a number.
    assert payload[2]["progress"] == 42, payload[2]


def test_number_types_are_numeric() -> None:
    """Numeric fields must not be emitted as strings."""
    project = {
        "name": "N", "width": 296, "height": 128, "variables": [],
        "nodes": [{"id": "t", "kind": "element", "type": "text",
                   "props": {"value": "x", "x": 5, "y": 7.5, "size": 20}}],
    }
    payload = _render(generate_template(project))
    assert payload[0]["x"] == 5 and isinstance(payload[0]["x"], int)
    assert payload[0]["y"] == 7.5 and isinstance(payload[0]["y"], float)
    # size matches the default and is therefore omitted.
    assert "size" not in payload[0], payload[0]


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