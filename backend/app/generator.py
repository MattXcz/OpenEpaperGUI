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
        ,{
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
the whole payload. A repeat group expands to N items, so inside the loop body
each item is prefixed with a comma -- or with ``{% if not loop.first %},{% endif %}``
when the group itself is the first item of the payload.

That only works while we know, before rendering, how many items each node
produces. Nodes that emit nothing (hidden elements, empty or zero-iteration
groups) are dropped up front so they cannot leave a dangling comma behind. When
an iteration count is itself a Jinja expression, or groups are nested (where
``loop.first`` only describes the innermost loop), the item count is not known
here, so the template falls back to a runtime flag
(``{% set oepl_ns = namespace(first=true) %}``) that every item checks and clears.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .schema import ELEMENT_TYPES_BY_NAME, INTERNAL_FIELDS, emitted_always

INDENT = "  "

_INTEGER_RE = re.compile(r"-?\d+")
_NUMERIC_RE = re.compile(r"-?\d+(?:\.\d+)?")
# drawcustom accepts percentages for positions, e.g. `x: "50%"`.
_PERCENT_RE = re.compile(r"-?\d+(?:\.\d+)?%")
_WHOLE_TAG_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}", re.DOTALL)
# Splits a string into literal chunks and whole Jinja tags (odd indexes).
_JINJA_SEGMENT_RE = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.DOTALL)


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

    text = str(value).strip()
    if not text:
        # Nothing to emit. `_fmt_value` filters these out first; this only
        # guards hand-crafted point / plot lists.
        return "null"
    if _is_template(text):
        return text
    if _NUMERIC_RE.fullmatch(text):
        # A numeric string, e.g. "42" typed into a number field.
        return text
    if _PERCENT_RE.fullmatch(text):
        # A relative position. It has to stay a JSON string: `{{ 50% }}` is a
        # Jinja syntax error and a bare `50%` is invalid JSON.
        return json.dumps(text)
    # A bare expression such as `spacing` or `15 + i*spacing`. Wrapping it is
    # what the user meant; emitting it raw would produce invalid JSON.
    return "{{ " + text + " }}"


def _fmt_string(value: str) -> str:
    if not _is_template(value):
        return json.dumps(value, ensure_ascii=False)

    # Escape the literal chunks so the surrounding JSON string stays valid, but
    # leave the Jinja tags byte-for-byte alone: escaping a quote inside
    # `{{ … }}` would break the expression itself.
    chunks = []
    for index, part in enumerate(_JINJA_SEGMENT_RE.split(value)):
        chunks.append(part if index % 2 else json.dumps(part, ensure_ascii=False)[1:-1])
    return '"' + "".join(chunks) + '"'


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
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                inner.append(f'"{key}": {"true" if value else "false"}')
            elif isinstance(value, (int, float)):
                inner.append(f'"{key}": {_fmt_number(value)}')
            else:
                inner.append(f'"{key}": {_fmt_string(str(value))}')
        lines.append("{" + ", ".join(inner) + "}")
    return "[" + ", ".join(lines) + "]"


def _object_items(field: dict, value: Any) -> list[tuple[dict, Any]] | None:
    """Sub-properties of an `object` field (plot axes / legends) to emit.

    `None` means the whole object is switched off and omitted. Home Assistant
    treats an empty object as "off" as well, so when every sub-property equals
    its default the field's `emit_key` is emitted anyway to keep it on.
    """
    if not isinstance(value, dict):
        return None
    items = []
    for sub in field["fields"]:
        raw = value.get(sub["key"], sub.get("default"))
        if _same_as_default(raw, sub.get("default")):
            continue
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        items.append((sub, raw))
    if not items:
        key = field.get("emit_key")
        sub = next((s for s in field["fields"] if s["key"] == key), None)
        if sub is None or sub.get("default") is None:
            return None
        items.append((sub, value.get(key, sub["default"])))
    return items


def _fmt_object(field: dict, value: Any) -> str | None:
    items = _object_items(field, value)
    if items is None:
        return None
    parts = []
    for sub, raw in items:
        formatted = _fmt_value(sub, raw)
        if formatted is not None:
            parts.append(f'"{sub["key"]}": {formatted}')
    return "{" + ", ".join(parts) + "}"


def _fmt_value(field: dict, value: Any) -> str | None:
    """Format a single property. Returns None when the property is omitted."""
    kind = field["kind"]

    if kind == "bool":
        return "true" if value else "false"

    if kind == "number":
        if value is None or (isinstance(value, str) and not value.strip()):
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

    if kind == "object":
        return _fmt_object(field, value)

    # text / textarea
    if value is None or value == "":
        return None
    return _fmt_string(str(value))


# ---------------------------------------------------------------------------
# Which properties an element emits
# ---------------------------------------------------------------------------

def _forced_fields(element_type: str, props: dict) -> set[str]:
    """Optional fields that must be emitted for this particular element.

    These mirror defaults in the OpenEPaperLink image generator that depend on
    other properties, so "equal to the schema default" is not the same as
    "equal to what Home Assistant would use".
    """
    forced: set[str] = set()
    if element_type == "text":
        # Without `anchor`, HA uses "la" for multi-line text and "lt" otherwise.
        # Wrapping (`max_width`) can introduce line breaks at render time.
        value = props.get("value")
        max_width = props.get("max_width")
        if (isinstance(value, str) and "\n" in value) or max_width not in (None, ""):
            forced.add("anchor")
    if element_type in ("rectangle", "rectangle_pattern"):
        # HA rounds with radius 10 when `corners` is given without `radius`.
        corners = props.get("corners")
        spec = ELEMENT_TYPES_BY_NAME[element_type]
        default = next((f["default"] for f in spec["fields"] if f["key"] == "corners"), None)
        if corners not in (None, "") and corners != default:
            forced.add("radius")
    return forced


def _emitted_fields(element: dict) -> list[tuple[dict, Any]] | None:
    """(field, value) pairs an element emits, or None when it emits nothing."""
    element_type = element.get("type")
    spec = ELEMENT_TYPES_BY_NAME.get(element_type)
    if not spec:
        return None

    props = element.get("props") or {}
    if props.get("visible") is False:
        return None

    always = emitted_always(element_type) | _forced_fields(element_type, props)
    out = []
    for field in spec["fields"]:
        key = field["key"]
        if key in INTERNAL_FIELDS or key == "type":
            continue
        raw = props.get(key, field.get("default"))
        # Only emit optional properties when they differ from the default.
        if key not in always and _same_as_default(raw, field.get("default")):
            continue
        out.append((field, raw))
    return out


def _element_lines(element: dict, indent: str) -> list[str]:
    """Render one element as a list of JSON lines (without trailing comma)."""
    fields = _emitted_fields(element)
    if fields is None:
        return []

    pairs: list[tuple[str, str]] = [("type", _fmt_string(element["type"]))]
    for field, raw in fields:
        formatted = _fmt_value(field, raw)
        if formatted is None:
            continue
        pairs.append((field["key"], formatted))

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


# ---------------------------------------------------------------------------
# Node emission
# ---------------------------------------------------------------------------

# Comma placement is decided statically whenever we know how many payload items
# every node produces. A Jinja-driven iteration count or nested groups break
# that, so the template then switches to a runtime flag for the whole payload.
# The name is prefixed so it cannot collide with a user's own `ns`.
GUARD_INIT = "{% set oepl_ns = namespace(first=true) %}"
GUARD_PREFIX = "{% if not oepl_ns.first %},{% endif %}{% set oepl_ns.first = false %}"

# First item of the payload, emitted inside a loop: comma from iteration 2 on.
LOOP_FIRST_PREFIX = "{% if not loop.first %},{% endif %}"


def _is_group(node: dict) -> bool:
    return node.get("kind") == "group"


def _static_count(count: Any) -> int | None:
    """Iteration count when it is a plain integer, else None (Jinja decides)."""
    if isinstance(count, bool):
        return None
    if isinstance(count, int):
        return count
    if isinstance(count, float) and count.is_integer():
        return int(count)
    if isinstance(count, str) and _INTEGER_RE.fullmatch(count.strip()):
        return int(count.strip())
    return None


def _count_expr(count: Any) -> str:
    """The expression that goes inside `range(...)`."""
    static = _static_count(count)
    if static is not None:
        return str(max(0, static))
    # A Jinja-valued count: `{{ n }}` has to become a bare `n` inside the tag.
    text = str(count).strip()
    match = _WHOLE_TAG_RE.fullmatch(text)
    return match.group(1) if match else text


def _node_item_count(node: dict) -> int | None:
    """How many payload items a node produces, or None when only Jinja knows."""
    if not _is_group(node):
        return 1 if _emitted_fields(node) is not None else 0

    total = 0
    for child in node.get("children") or []:
        count = _node_item_count(child)
        if count is None:
            return None
        total += count
    if total == 0:
        return 0

    repeat = node.get("repeat") or {}
    if not repeat.get("enabled", True):
        return total

    count = _static_count(repeat.get("count", 1))
    if count is None:
        return None
    return max(0, count) * total


def _has_nested_groups(nodes: list) -> bool:
    return any(
        _is_group(node) and any(_is_group(child) for child in node.get("children") or [])
        for node in nodes
    ) or any(_has_nested_groups(node.get("children") or []) for node in nodes if _is_group(node))


def _prefix(first: bool, seen: bool, guard: bool, in_loop: bool) -> str:
    """Separator emitted in front of one payload item.

    `first` is True while nothing has been emitted before this node, `seen`
    while nothing has been emitted inside it yet.
    """
    if guard:
        return GUARD_PREFIX
    if not first or seen:
        return ","
    return LOOP_FIRST_PREFIX if in_loop else ""


def _emit_element(element: dict, prefix: str, indent: str) -> list[str]:
    body = _element_lines(element, indent)
    if not body:
        return []
    if prefix:
        body[0] = indent + prefix + body[0].lstrip()
    return body


def _emit_children(children: list, first: bool, indent: str, guard: bool, in_loop: bool) -> list[str]:
    out: list[str] = []
    seen = False
    for child in children:
        # A child that emits nothing (hidden, unknown type, empty group) must
        # not consume the "no comma yet" slot, or the next one emits a stray
        # comma.
        if _node_item_count(child) == 0:
            continue
        if _is_group(child):
            # Nested groups always run with the runtime guard (see module doc),
            # so `first` / `seen` no longer matter here.
            block = _emit_group(child, first and not seen, indent, guard)
        else:
            block = _emit_element(child, _prefix(first, seen, guard, in_loop), indent)
        if not block:
            continue
        seen = True
        out.extend(block)
    return out


def _emit_group(group: dict, first: bool, indent: str, guard: bool) -> list[str]:
    children = group.get("children") or []
    repeat = group.get("repeat") or {}

    if not repeat.get("enabled", True):
        # Emit the children once, as plain elements.
        return _emit_children(children, first, indent, guard, in_loop=False)

    lines: list[str] = []

    # Optional `{% set %}` statements executed before the loop.
    for statement in repeat.get("pre") or []:
        statement = str(statement).strip()
        if not statement:
            continue
        if not statement.startswith("{%"):
            statement = "{% set " + statement + " %}"
        lines.append(indent + statement)

    var = str(repeat.get("var") or "i").strip() or "i"
    count = _count_expr(repeat.get("count", 1))
    lines.append(indent + "{% for " + var + " in range(" + count + ") %}")
    lines.extend(_emit_children(children, first, indent + INDENT, guard, in_loop=True))
    lines.append(indent + "{% endfor %}")
    return lines


def _emit_node(node: dict, first: bool, indent: str, guard: bool) -> list[str]:
    if _is_group(node):
        return _emit_group(node, first, indent, guard)
    return _emit_element(node, _prefix(first, False, guard, False), indent)


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

    counts = [_node_item_count(node) for node in nodes]
    # One unknown count anywhere makes static comma placement unsafe, because a
    # node that emits nothing at render time would leave a dangling comma.
    # Nested loops break `loop.first` the same way.
    guard = any(count is None for count in counts) or _has_nested_groups(nodes)
    if guard:
        lines.append(GUARD_INIT)

    if lines:
        lines.append("")

    lines.append("[")

    emitted_any = False
    for node, count in zip(nodes, counts):
        if count == 0:
            continue  # emits nothing, so it must not affect comma placement
        block = _emit_node(node, not emitted_any, INDENT, guard)
        if not block:
            continue
        emitted_any = True
        lines.extend(block)

    lines.append("]")
    return "\n".join(lines)


def collect_warnings(project: dict) -> list[str]:
    """Things in the project the generator cannot express, or likely mistakes."""
    warnings: list[str] = []

    def check(node: dict, loop_vars: tuple[str, ...]) -> None:
        if _is_group(node):
            repeat = node.get("repeat") or {}
            inner = loop_vars
            if repeat.get("enabled", True):
                var = str(repeat.get("var") or "i").strip() or "i"
                if var in loop_vars:
                    warnings.append(
                        f"Group \"{node.get('name') or 'group'}\" reuses the loop variable "
                        f"\"{var}\" of an enclosing group; the outer value is hidden inside it."
                    )
                inner = loop_vars + (var,)
            for child in node.get("children") or []:
                check(child, inner)
        elif node.get("type") not in ELEMENT_TYPES_BY_NAME:
            warnings.append(f"Unknown element type \"{node.get('type')}\" is skipped.")

    for node in project.get("nodes") or []:
        check(node, ())
    return warnings


def _static_value(field: dict, value: Any) -> Any:
    if field["kind"] == "object":
        items = _object_items(field, value)
        return None if items is None else {sub["key"]: raw for sub, raw in items}
    return value


def generate_payload(project: dict) -> list[dict]:
    """Generate the *static* payload, ignoring repeat groups.

    Used for the design-time canvas so the editor never needs a Jinja runtime.
    """
    payload: list[dict] = []

    def emit(element: dict) -> None:
        fields = _emitted_fields(element)
        if fields is None:
            return
        item: dict[str, Any] = {"type": element["type"]}
        for field, raw in fields:
            value = _static_value(field, raw)
            if value is None or value == "":
                continue
            item[field["key"]] = value
        payload.append(item)

    def walk(nodes: list) -> None:
        for node in nodes:
            if _is_group(node):
                repeat = node.get("repeat") or {}
                if repeat.get("enabled", True):
                    continue  # dynamic, cannot be resolved statically
                walk(node.get("children") or [])
            else:
                emit(node)

    walk(project.get("nodes") or [])
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
    # Always quote: a bare `{{ … }}` starts a YAML flow mapping, and values
    # like `50%`, `yes` or `#fff` would change type or become comments.
    return json.dumps(str(value), ensure_ascii=False)
