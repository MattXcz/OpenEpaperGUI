"""Turn the visual project model into an OpenEPaperLink `drawcustom` payload.

The output is a Home Assistant Jinja template that renders to a JSON array of
drawing elements, e.g.::

    {% set spacing = 49 %}
    [
      {
        "type": "text",
        "value": " ",
        "x": 0,
        "y": 0,
        "size": 1,
        "color": "yellow"
      }
      {% for i in range(8) %}
        ,
        {
          "type": "text",
          "value": "{{ times[i] }}",
          "x": {{ 15 + i*spacing }},
          "y": 5,
          "size": 10
        }
      {% endfor %}
    ]

Comma handling
--------------
Every emitted item is prefixed with a comma unless it is the very first item of
the whole payload. A repeat group is a single logical item that expands to N
items, so inside the loop body each iteration is prefixed with a comma (or with
``{% if not loop.first %},{% endif %}`` when the group is the first item).
"""

from __future__ import annotations

import json
from typing import Any

from .schema import ELEMENT_TYPES_BY_NAME, INTERNAL_FIELDS, REQUIRED_FIELDS

INDENT = "  "


# ---------------------------------------------------------------------------
# Value formatting
# ---------------------------------------------------------------------------

def _is_template(value: Any) -> bool:
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def _fmt_number(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    # A string in a numeric slot is treated as a Jinja expression.
    return str(value)


def _fmt_string(value: str) -> str:
    if _is_template(value):
        # Keep the template intact; only escape backslashes and newlines.
        escaped = value.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "")
        return f'"{escaped}"'
    return json.dumps(value, ensure_ascii=False)


def _fmt_points(points: Any) -> str:
    if not isinstance(points, list):
        return "[]"
    pairs = []
    for point in points:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            pairs.append(f"[{_fmt_number(point[0])}, {_fmt_number(point[1])}]")
    return "[" + ", ".join(pairs) + "]"


def _fmt_iconlist(icons: Any) -> str:
    if not isinstance(icons, list):
        return "[]"
    return "[" + ", ".join(_fmt_string(str(i)) for i in icons) + "]"


def _fmt_plotdata(entries: Any) -> str:
    if not isinstance(entries, list):
        return "[]"
    lines = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        inner = []
        for key, value in entry.items():
            if value in (None, ""):
                continue
            if isinstance(value, bool):
                inner.append(f'"{key}": {"true" if value else "false"}')
            elif isinstance(value, (int, float)):
                inner.append(f'"{key}": {_fmt_number(value)}')
            else:
                inner.append(f'"{key}": {_fmt_string(str(value))}')
        lines.append("{" + ", ".join(inner) + "}")
    return "[" + ", ".join(lines) + "]"


def _fmt_value(field: dict, value: Any) -> str | None:
    """Format a single property. Returns None when the property is omitted."""
    kind = field["kind"]

    if kind == "bool":
        return "true" if value else "false"

    if kind == "number":
        if value is None or value == "":
            return None
        return _fmt_number(value)

    if kind == "color":
        if value is None or value == "":
            return "null" if field.get("allow_none") else None
        return _fmt_string(str(value))

    if kind == "select":
        if value is None or value == "":
            return None
        return _fmt_string(str(value))

    if kind == "points":
        if not value:
            return None
        return _fmt_points(value)

    if kind == "iconlist":
        if not value:
            return None
        return _fmt_iconlist(value)

    if kind == "plotdata":
        if not value:
            return None
        return _fmt_plotdata(value)

    # text / textarea
    if value is None or value == "":
        return None
    return _fmt_string(str(value))


# ---------------------------------------------------------------------------
# Element emission
# ---------------------------------------------------------------------------

def _element_lines(element: dict, indent: str) -> list[str]:
    """Render one element as a list of JSON lines (without trailing comma)."""
    element_type = element.get("type")
    spec = ELEMENT_TYPES_BY_NAME.get(element_type)
    if not spec:
        return []

    props = element.get("props") or {}
    if props.get("visible") is False:
        return []

    required = REQUIRED_FIELDS.get(element_type, set())

    pairs: list[tuple[str, str]] = [("type", _fmt_string(element_type))]
    for field in spec["fields"]:
        key = field["key"]
        if key in INTERNAL_FIELDS or key == "type":
            continue
        raw = props.get(key, field.get("default"))
        default = field.get("default")

        # Only emit optional properties when they differ from the default.
        if key not in required and _same_as_default(raw, default):
            continue

        formatted = _fmt_value(field, raw)
        if formatted is None:
            continue
        pairs.append((key, formatted))

    lines = [indent + "{"]
    for index, (key, formatted) in enumerate(pairs):
        comma = "," if index < len(pairs) - 1 else ""
        lines.append(f'{indent}{INDENT}"{key}": {formatted}{comma}')
    lines.append(indent + "}")
    return lines


def _same_as_default(value: Any, default: Any) -> bool:
    """True when a property can be omitted because it equals the default."""
    if value is None and default is None:
        return True
    if isinstance(value, str) and isinstance(default, str):
        return value == default
    if isinstance(value, bool) or isinstance(default, bool):
        return value is default or value == default
    if isinstance(value, (int, float)) and isinstance(default, (int, float)):
        return float(value) == float(default)
    if isinstance(value, list) and isinstance(default, list):
        return value == default
    return False


def _indent_block(lines: list[str], extra: str) -> list[str]:
    return [extra + line if line.strip() else line for line in lines]


# ---------------------------------------------------------------------------
# Node emission
# ---------------------------------------------------------------------------

def _emit_element(element: dict, first: bool, indent: str) -> list[str]:
    body = _element_lines(element, indent)
    if not body:
        return []
    if not first:
        body[0] = indent + "," + body[0].lstrip()
    return body


def _emit_group(group: dict, first: bool, indent: str) -> list[str]:
    repeat = group.get("repeat") or {}
    children = group.get("children") or []
    if not children:
        return []

    var = repeat.get("var") or "i"
    count = repeat.get("count", 1)
    enabled = repeat.get("enabled", True)

    if not enabled:
        # Emit children once, as plain elements.
        out: list[str] = []
        for child in children:
            out.extend(_emit_element(child, first and not out, indent))
        return out

    lines: list[str] = []

    # Optional `{% set %}` statements executed before the loop.
    for statement in repeat.get("pre") or []:
        statement = str(statement).strip()
        if not statement:
            continue
        if not statement.startswith("{%"):
            statement = "{% set " + statement + " %}"
        lines.append(indent + statement)

    lines.append(indent + "{% for " + var + " in range(" + str(count) + ") %}")

    body_indent = indent + INDENT
    for index, child in enumerate(children):
        child_lines = _element_lines(child, body_indent)
        if not child_lines:
            continue
        if index == 0:
            if first:
                # First item of the payload: only add a comma from iteration 2 on.
                child_lines[0] = (
                    body_indent + "{% if not loop.first %},{% endif %}"
                    + child_lines[0].lstrip()
                )
            else:
                child_lines[0] = body_indent + "," + child_lines[0].lstrip()
        else:
            child_lines[0] = body_indent + "," + child_lines[0].lstrip()
        lines.extend(child_lines)

    lines.append(indent + "{% endfor %}")
    return lines


def _emit_node(node: dict, first: bool, indent: str) -> list[str]:
    if node.get("kind") == "group":
        return _emit_group(node, first, indent)
    return _emit_element(node, first, indent)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_template(project: dict) -> str:
    """Generate the full Jinja template for a project."""
    nodes = project.get("nodes") or []
    variables = project.get("variables") or []

    lines: list[str] = []

    for variable in variables:
        name = (variable.get("name") or "").strip()
        if not name:
            continue
        value = variable.get("value")
        if value is None or value == "":
            continue
        lines.append("{% set " + name + " = " + str(value).strip() + " %}")

    if lines:
        lines.append("")

    lines.append("[")

    emitted_any = False
    for node in nodes:
        block = _emit_node(node, not emitted_any, INDENT)
        if not block:
            continue
        emitted_any = True
        lines.extend(block)

    lines.append("]")
    return "\n".join(lines)


def generate_payload(project: dict) -> list[dict]:
    """Generate the *static* payload, ignoring repeat groups.

    Used for the design-time canvas so the editor never needs a Jinja runtime.
    """
    payload: list[dict] = []

    def emit(element: dict) -> None:
        spec = ELEMENT_TYPES_BY_NAME.get(element.get("type"))
        if not spec:
            return
        props = element.get("props") or {}
        if props.get("visible") is False:
            return
        required = REQUIRED_FIELDS.get(element["type"], set())
        item: dict[str, Any] = {"type": element["type"]}
        for field in spec["fields"]:
            key = field["key"]
            if key in INTERNAL_FIELDS or key == "type":
                continue
            value = props.get(key, field.get("default"))
            if key not in required and _same_as_default(value, field.get("default")):
                continue
            if value is None or value == "":
                continue
            item[key] = value
        payload.append(item)

    for node in project.get("nodes") or []:
        if node.get("kind") == "group":
            repeat = node.get("repeat") or {}
            if repeat.get("enabled", True):
                continue  # dynamic, cannot be resolved statically
            for child in node.get("children") or []:
                emit(child)
        else:
            emit(node)

    return payload


def generate_yaml(project: dict) -> str:
    """Generate a plain YAML payload (no Jinja) for quick copy/paste."""
    payload = generate_payload(project)
    return _to_yaml(payload)


def _to_yaml(value: Any, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            return pad + "{}"
        out = []
        for key, item in value.items():
            if isinstance(item, (dict, list)) and item:
                out.append(f"{pad}{key}:")
                out.append(_to_yaml(item, indent + 2))
            else:
                out.append(f"{pad}{key}: {_scalar(item)}")
        return "\n".join(out)
    if isinstance(value, list):
        if not value:
            return pad + "[]"
        out = []
        for item in value:
            if isinstance(item, dict):
                rendered = _to_yaml(item, indent + 2).lstrip()
                out.append(f"{pad}- {rendered}")
            elif isinstance(item, list):
                out.append(f"{pad}- {json.dumps(item)}")
            else:
                out.append(f"{pad}- {_scalar(item)}")
        return "\n".join(out)
    return pad + _scalar(value)


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _fmt_number(value)
    text = str(value)
    if _is_template(text):
        return text
    return json.dumps(text, ensure_ascii=False)