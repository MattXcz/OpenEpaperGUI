"""Turn pasted `drawcustom` code back into editor nodes.

Accepts what people actually have lying around:

* a plain JSON payload (``[{"type": "text", ...}, ...]``), e.g. from "Copy JSON"
* JSON service data with a ``payload`` key, optionally nested under ``data``
* a Jinja template as produced by the generator (or written by hand in the
  same shape): ``{% set %}`` before the payload become project variables,
  ``{% for v in range(n) %}`` loops become repeat groups, and ``{{ … }}``
  expressions are kept as expressions, quoted or not.

Anything the editor cannot represent (conditions, loops over lists, tags
inside an element) is rejected with a message instead of being guessed at.
Properties the schema does not know are dropped with a warning, because the
generator would drop them silently on the next export.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .schema import ELEMENT_TYPES_BY_NAME

# drawcustom service options that map onto project settings.
SERVICE_OPTIONS = ("background", "rotate", "dither", "ttl")

_SET_RE = re.compile(r"^set\s+([A-Za-z_][\w.]*)\s*=\s*(.+)$", re.S)
_FOR_RE = re.compile(r"^for\s+([A-Za-z_]\w*)\s+in\s+range\((.+)\)$", re.S)
_INTEGER_RE = re.compile(r"-?\d+")
# The comma guards the generator emits; they carry no layout information.
_GUARD_IF_RE = re.compile(r"^if\s+not\s+(loop|oepl_ns)\.first$")
_GUARD_NAME = "oepl_ns"


class CodeImportError(ValueError):
    """The code cannot be turned into editor nodes."""


def import_code(code: str) -> dict:
    """Parse pasted code into ``{nodes, variables, options, warnings}``."""
    text = code.strip()
    if not text:
        raise CodeImportError("Nothing to import.")

    warnings: list[str] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        nodes, variables = _parse_template(text, warnings)
        return {"nodes": nodes, "variables": variables, "options": {}, "warnings": warnings}

    payload, options = _unwrap(data)
    nodes = [node for node in (_element(item, warnings) for item in payload) if node]
    return {"nodes": nodes, "variables": [], "options": options, "warnings": warnings}


def _unwrap(data: Any) -> tuple[list, dict]:
    """The element list and service options of a JSON document."""
    if isinstance(data, list):
        return data, {}
    if isinstance(data, dict):
        if isinstance(data.get("data"), dict):
            data = data["data"]
        payload = data.get("payload")
        if isinstance(payload, str):
            # Service data can carry the payload as a JSON-encoded string.
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise CodeImportError(f"`payload` is not valid JSON: {exc.msg}") from exc
        if isinstance(payload, list):
            options = {key: data[key] for key in SERVICE_OPTIONS if key in data}
            return payload, options
        if "type" in data:
            return [data], {}
    raise CodeImportError("Expected a list of elements or an object with a `payload` list.")


# ---------------------------------------------------------------------------
# Elements
# ---------------------------------------------------------------------------

def _element(item: Any, warnings: list[str]) -> dict | None:
    if not isinstance(item, dict):
        warnings.append(f"Skipped an entry that is not an object: {json.dumps(item)[:40]}")
        return None
    element_type = item.get("type")
    spec = ELEMENT_TYPES_BY_NAME.get(element_type)
    if not spec:
        warnings.append(f"Skipped unknown element type {element_type!r}.")
        return None

    known = {field["key"] for field in spec["fields"]}
    props = {key: value for key, value in item.items() if key in known}
    unknown = sorted(key for key in item if key not in known and key != "type")
    if unknown:
        warnings.append(f"{spec['label']}: ignored unknown properties {', '.join(unknown)}.")
    return {"kind": "element", "type": element_type, "props": props}


# ---------------------------------------------------------------------------
# Jinja templates
# ---------------------------------------------------------------------------

def _tokens(text: str):
    """Yield ``("tag", body)``, ``("open", None)`` and ``("object", json)``.

    Walks the template once, keeping track of JSON strings and object depth.
    ``{{ … }}`` is treated as one atom everywhere, because the generator keeps
    expressions byte-for-byte inside strings, quotes included. It is escaped
    inside a string and wrapped into one outside, so the element parses as JSON
    and the prop holds the expression exactly as written.
    """
    pos = 0
    depth = 0
    in_string = False
    buf: list[str] = []
    length = len(text)

    while pos < length:
        if text.startswith("{{", pos):
            end = text.find("}}", pos + 2)
            if end < 0:
                raise CodeImportError("Unclosed `{{` expression.")
            expr = text[pos:end + 2]
            if depth == 0:
                raise CodeImportError(f"Expression outside an element is not supported: {expr[:60]}")
            # Escaped either way, so quotes inside the expression survive json.loads.
            buf.append(json.dumps(expr)[1:-1] if in_string else json.dumps(expr))
            pos = end + 2
            continue

        if text.startswith("{%", pos) and not in_string:
            end = text.find("%}", pos + 2)
            if end < 0:
                raise CodeImportError("Unclosed `{%` tag.")
            if depth:
                raise CodeImportError(
                    "Jinja tags inside an element are not supported: "
                    + text[pos:end + 2][:60]
                )
            yield "tag", text[pos + 2:end].strip().strip("-").strip()
            pos = end + 2
            continue

        char = text[pos]
        if in_string:
            buf.append(char)
            if char == "\\" and pos + 1 < length:
                buf.append(text[pos + 1])
                pos += 1
            elif char == '"':
                in_string = False
        elif depth:
            buf.append(char)
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield "object", "".join(buf)
                    buf = []
        elif char == "{":
            depth = 1
            buf = [char]
        elif char == "[":
            yield "open", None
        elif not (char.isspace() or char in ",]"):
            raise CodeImportError(f"Unexpected text outside an element: {text[pos:pos + 30]!r}")
        pos += 1

    if depth:
        raise CodeImportError("An element is missing its closing `}`.")


def _parse_template(text: str, warnings: list[str]) -> tuple[list, list]:
    root: list = []
    stack: list[list] = [root]
    variables: list[dict] = []
    pending: list[str] = []   # `set` statements waiting for the next loop
    guard_ifs = 0
    started = False

    for kind, value in _tokens(text):
        if kind == "open":
            started = True
            continue

        if kind == "object":
            if pending:
                warnings.append(f"Ignored `set` outside a loop: {'; '.join(pending)}.")
                pending = []
            try:
                item = json.loads(value)
            except json.JSONDecodeError as exc:
                raise CodeImportError(f"Invalid element: {exc.msg} in {value[:60]!r}") from exc
            node = _element(item, warnings)
            if node:
                stack[-1].append(node)
            continue

        tag = value
        if match := _SET_RE.match(tag):
            name, expr = match.group(1), match.group(2).strip()
            if name.split(".")[0] == _GUARD_NAME:
                continue
            if not started and len(stack) == 1:
                variables.append({"name": name, "value": expr})
            else:
                pending.append(f"{name} = {expr}")
        elif match := _FOR_RE.match(tag):
            count = match.group(2).strip()
            group = {
                "kind": "group",
                "name": "Repeat group",
                "repeat": {
                    "enabled": True,
                    "var": match.group(1),
                    "count": int(count) if _INTEGER_RE.fullmatch(count) else count,
                    "pre": pending,
                },
                "children": [],
            }
            pending = []
            stack[-1].append(group)
            stack.append(group["children"])
        elif tag == "endfor":
            if len(stack) == 1:
                raise CodeImportError("`{% endfor %}` without a matching `{% for %}`.")
            stack.pop()
        elif _GUARD_IF_RE.match(tag):
            guard_ifs += 1
        elif tag == "endif" and guard_ifs:
            guard_ifs -= 1
        elif tag.startswith("for "):
            raise CodeImportError(
                f"Only `for … in range(…)` loops can be imported, not `{{% {tag} %}}`."
            )
        elif tag.split()[0] in {"if", "elif", "else", "endif"}:
            raise CodeImportError(
                "Conditions (`{% if %}`) cannot be represented in the editor. "
                "Paste the rendered JSON instead."
            )
        else:
            raise CodeImportError(f"Unsupported Jinja tag `{{% {tag} %}}`.")

    if len(stack) > 1:
        raise CodeImportError("A `{% for %}` loop is missing its `{% endfor %}`.")
    if pending:
        warnings.append(f"Ignored trailing `set`: {'; '.join(pending)}.")
    if not root and not variables:
        raise CodeImportError("No elements found.")
    return root, variables
