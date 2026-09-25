"""Importing pasted payloads and templates back into editor nodes."""

from __future__ import annotations

import json

import pytest

from .generator import generate_template
from .importer import CodeImportError, import_code
from .test_generator import _group, _project, _text, _weather_project


def _roundtrip(project: dict) -> None:
    """Template → import → template must be unchanged."""
    template = generate_template(project)
    result = import_code(template)
    again = {**project, "nodes": result["nodes"], "variables": result["variables"]}
    assert generate_template(again) == template


def test_plain_json_payload() -> None:
    code = json.dumps([
        {"type": "text", "value": "Test 123", "x": 102, "y": 52, "size": 12, "font": "rbm.ttf"},
        {"type": "line", "x_start": 40, "x_end": 118, "y_start": 118, "y_end": 164},
    ])
    result = import_code(code)
    assert [node["type"] for node in result["nodes"]] == ["text", "line"]
    assert result["nodes"][0]["props"]["font"] == "rbm.ttf"
    assert result["warnings"] == []


def test_service_data_with_options() -> None:
    code = json.dumps({"data": {"background": "black", "rotate": 90, "payload": [
        {"type": "text", "value": "A", "x": 0, "y": 0},
    ]}})
    result = import_code(code)
    assert result["options"] == {"background": "black", "rotate": 90}
    assert len(result["nodes"]) == 1


def test_payload_as_json_string() -> None:
    code = json.dumps({"payload": json.dumps([{"type": "text", "value": "A", "x": 0, "y": 0}])})
    assert len(import_code(code)["nodes"]) == 1


def test_unknown_types_and_props_are_reported() -> None:
    code = json.dumps([
        {"type": "sparkle", "x": 1},
        {"type": "text", "value": "A", "x": 0, "y": 0, "blink": True},
    ])
    result = import_code(code)
    assert len(result["nodes"]) == 1
    assert "blink" not in result["nodes"][0]["props"]
    assert len(result["warnings"]) == 2


def test_weather_template_roundtrips() -> None:
    _roundtrip(_weather_project())


def test_nested_and_dynamic_loops_roundtrip() -> None:
    inner = {**_group([_text(value="{{ i }}{{ j }}")], count=3, var="j"), "name": "Repeat group"}
    _roundtrip(_project(_group([_text(value="h{{ i }}"), inner], count="n")))


def test_loop_pre_statements_roundtrip() -> None:
    _roundtrip(_project(_text(), _group([_text(x="{{ offset }}")], pre=["offset = i * 20"])))


def test_unquoted_expression_becomes_a_string() -> None:
    result = import_code('[{"type": "text", "value": "{{ states("sensor.t") }}", "x": {{ 5 + 1 }}, "y": 0}]')
    props = result["nodes"][0]["props"]
    assert props["value"] == '{{ states("sensor.t") }}'
    assert props["x"] == "{{ 5 + 1 }}"


def test_variables_before_the_payload() -> None:
    result = import_code('{% set spacing = 49 %}\n[{"type": "text", "value": "A", "x": {{ spacing }}, "y": 0}]')
    assert result["variables"] == [{"name": "spacing", "value": "49"}]


@pytest.mark.parametrize("code", [
    "",
    "not json",
    '[{% if x %}{"type": "text", "value": "A", "x": 0, "y": 0}{% endif %}]',
    '[{% for x in items %}{"type": "text", "value": "A", "x": 0, "y": 0}{% endfor %}]',
    '[{% for i in range(2) %}{"type": "text", "value": "A", "x": 0, "y": 0}]',
    '[{"type": "text", "value": "A", {% if x %}"x": 0{% endif %}, "y": 0}]',
    '{"foo": 1}',
])
def test_unsupported_code_is_rejected(code: str) -> None:
    with pytest.raises(CodeImportError):
        import_code(code)
