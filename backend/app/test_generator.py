"""Render a generated template with Jinja and assert the result is valid JSON.

Run with:  python -m app.test_generator   (from the backend directory)
"""

from __future__ import annotations

import json

from jinja2 import Environment

from .generator import collect_warnings, generate_template, generate_yaml
from .schema import default_props

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
        "n": 3,
        "spacing": 7,
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


# ---------------------------------------------------------------------------
# Regression tests: inputs that used to emit invalid JSON
# ---------------------------------------------------------------------------

def _text(**props: object) -> dict:
    """A text element with the required props filled in."""
    return {"kind": "element", "type": "text", "props": {"value": "A", "x": 1, "y": 1, **props}}


def _group(children: list, **repeat: object) -> dict:
    return {
        "kind": "group",
        "repeat": {"enabled": True, "var": "i", "count": 2, "pre": [], **repeat},
        "children": children,
    }


def _project(*nodes: dict) -> dict:
    return {"name": "R", "width": 296, "height": 128, "variables": [], "nodes": list(nodes)}


def test_hidden_first_child_of_first_group() -> None:
    """A skipped child must not leave the comma slot filled behind it."""
    payload = _render(generate_template(
        _project(_group([_text(visible=False), _text(value="B")]))
    ))
    assert [item["value"] for item in payload] == ["B", "B"], payload


def test_group_with_only_hidden_children_is_dropped() -> None:
    """An empty group must not make the next node emit a leading comma."""
    payload = _render(generate_template(
        _project(_group([_text(visible=False)]), _text(value="C"))
    ))
    assert [item["value"] for item in payload] == ["C"], payload


def test_zero_iteration_group_is_dropped() -> None:
    payload = _render(generate_template(
        _project(_group([_text()], count=0), _text(value="D"))
    ))
    assert [item["value"] for item in payload] == ["D"], payload


def test_disabled_group_skips_hidden_children() -> None:
    payload = _render(generate_template(
        _project(_group([_text(visible=False), _text(value="F")], enabled=False))
    ))
    assert [item["value"] for item in payload] == ["F"], payload


def test_quotes_in_template_values() -> None:
    """A quote in the literal part of a template value must be escaped..."""
    payload = _render(generate_template(_project(_text(value='{{ n }} 5" panel'))))
    assert payload[0]["value"] == '3 5" panel', payload


def test_quotes_inside_jinja_expression_survive() -> None:
    """...but a quote inside `{{ … }}` must be left alone, or Jinja breaks."""
    payload = _render(generate_template(_project(_text(value='{{ states("sensor.x") }}'))))
    assert payload[0]["value"] == "42", payload


def test_bare_expression_in_number_field() -> None:
    """A bare expression is wrapped in `{{ }}` rather than emitted raw."""
    payload = _render(generate_template(_project(_text(x="spacing"))))
    assert payload[0]["x"] == 7, payload


def test_dynamic_iteration_count() -> None:
    """A Jinja iteration count falls back to the runtime comma guard."""
    payload = _render(generate_template(
        _project(_group([_text()], count="{{ n }}"), _text(value="E"))
    ))
    assert [item["value"] for item in payload] == ["A", "A", "A", "E"], payload


def test_dynamic_iteration_count_of_zero() -> None:
    """Same template, but the loop produces nothing at render time."""
    project = _project(_group([_text()], count="{{ n - 3 }}"), _text(value="E"))
    payload = _render(generate_template(project))
    assert [item["value"] for item in payload] == ["E"], payload


def test_static_output_has_no_runtime_guard() -> None:
    """The guard is only paid for when an iteration count is dynamic."""
    static = generate_template(_weather_project())
    assert "namespace(first=true)" not in static, static


def test_percentage_positions() -> None:
    """`x: "50%"` is documented drawcustom syntax and must stay a string."""
    payload = _render(generate_template(_project(_text(x="50%", y="12.5%"))))
    assert payload[0]["x"] == "50%" and payload[0]["y"] == "12.5%", payload


def _element(etype: str, **props: object) -> dict:
    return {"kind": "element", "type": etype, "props": {**default_props(etype), **props}}


def test_dynamic_defaults_are_always_emitted() -> None:
    """Fields whose HA default is dynamic must never be omitted.

    Omitting `y_end: 0` makes HA draw to `y_start`; omitting a plot's box makes
    it span the whole canvas; omitting `multiline.y` auto-positions it.
    """
    payload = _render(generate_template(_project(
        _element("line", y_start=60, y_end=0),
        _element("plot"),
        _element("multiline", y=0),
        _element("debug_grid", spacing=10),
    )))
    line, plot, multiline, grid = payload
    assert line["y_start"] == 60 and line["y_end"] == 0, line
    assert {k: plot[k] for k in ("x_start", "y_start", "x_end", "y_end")} == \
        {"x_start": 10, "y_start": 20, "x_end": 199, "y_end": 119}, plot
    assert multiline["y"] == 0, multiline
    assert grid["label_step"] == 40, grid


def test_plot_duration_default_matches_home_assistant() -> None:
    """Default duration is HA's 86400, so leaving it untouched is correct."""
    payload = _render(generate_template(_project(_element("plot"))))
    assert "duration" not in payload[0], payload
    payload = _render(generate_template(_project(_element("plot", duration=3600))))
    assert payload[0]["duration"] == 3600, payload


def test_yaml_with_jinja_is_valid_yaml() -> None:
    import yaml

    project = _project(_text(value='{{ states("sensor.t") }} °C', x="50%", color="#fff"))
    parsed = yaml.safe_load(generate_yaml(project))
    assert parsed[0]["value"] == '{{ states("sensor.t") }} °C', parsed
    assert parsed[0]["x"] == "50%" and parsed[0]["color"] == "#fff", parsed


def test_nested_group_is_reported() -> None:
    inner = {**_group([_text()]), "name": "inner"}
    project = _project({**_group([inner]), "name": "outer"})
    warnings = collect_warnings(project)
    assert len(warnings) == 1 and "inner" in warnings[0], warnings
    assert collect_warnings(_weather_project()) == []


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