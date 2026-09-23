"""Element handlers for the preview renderer.

Each handler draws one element onto the shared canvas. Registration happens via
the `@handler` decorator into `HANDLERS`, which the renderer dispatches on.

Behaviour follows the integration's `imagegen` package: same defaults, same
coordinate and colour rules, same auto-positioning via `ctx.pos_y`.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from PIL import ImageFont

from .fonts import load_font

HANDLERS: dict[str, Callable] = {}


class UnsupportedElement(RuntimeError):
    """An element that needs live Home Assistant data to draw."""


def handler(element_type: str):
    """Register a drawing function for an element type."""

    def decorate(fn: Callable) -> Callable:
        HANDLERS[element_type] = fn
        return fn

    return decorate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Inline color markup: [red]text[/red]. Mirrors the integration's pattern.
_COLOR_TAG_RE = re.compile(
    r"\[(black|white|red|yellow|accent|half_black|half_red|half_yellow|half_accent"
    r"|gray|grey|g|hb|hr|hy|ha)\](.*?)\[/\1\]",
    re.DOTALL,
)


def parse_colored_text(text: str) -> list[tuple[str, str]]:
    """Split `[color]text[/color]` markup into (text, color) segments."""
    segments: list[tuple[str, str]] = []
    position = 0
    for match in _COLOR_TAG_RE.finditer(text):
        if match.start() > position:
            segments.append((text[position:match.start()], "black"))
        segments.append((match.group(2), match.group(1)))
        position = match.end()
    if position < len(text):
        segments.append((text[position:], "black"))
    return segments


def anchor_offset(anchor: str | None, width: float, height: float) -> tuple[float, float]:
    """Horizontal and vertical offset implied by a Pillow-style anchor."""
    if not anchor or len(anchor) < 2:
        return 0.0, 0.0
    horizontal = {"l": 0.0, "m": -width / 2, "r": -width}.get(anchor[0], 0.0)
    vertical = {"a": -height / 2, "t": 0.0, "m": -height / 2, "s": 0.0, "b": -height}.get(
        anchor[1], 0.0
    )
    return horizontal, vertical


def draw_text_run(
    ctx,
    x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    color: tuple,
    *,
    anchor: str | None = None,
    align: str = "left",
    spacing: int = 5,
    stroke_width: int = 0,
    stroke_fill: tuple | None = None,
) -> None:
    """Draw one run of text at an explicit position."""
    ctx.draw.text(
        (x, y),
        text,
        fill=color,
        font=font,
        anchor=anchor,
        align=align,
        spacing=spacing,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

@handler("text")
def draw_text(ctx, element: dict) -> None:
    draw = ctx.draw
    draw.fontmode = "1"

    x = ctx.coords.x(element["x"])
    if "y" in element:
        y = ctx.coords.y(element["y"])
    else:
        y = ctx.pos_y + int(element.get("y_padding", 10))

    size = ctx.coords.size(element.get("size", 20), is_width=False)
    font = load_font(element.get("font", "ppb.ttf"), size)
    align = element.get("align", "left")
    color = ctx.colors.resolve(element.get("color", "black"))
    anchor = element.get("anchor")
    spacing = int(element.get("spacing", 5))
    stroke_width = int(element.get("stroke_width", 0))
    stroke_fill = ctx.colors.resolve(element.get("stroke_fill", "white"))

    text = str(element["value"])
    max_width = element.get("max_width")

    if max_width is not None:
        max_width = ctx.coords.x(max_width)
        if element.get("truncate", False):
            if draw.textlength(text, font=font) > max_width:
                ellipsis = "..."
                truncated = text
                while truncated and draw.textlength(truncated + ellipsis, font=font) > max_width:
                    truncated = truncated[:-1]
                text = truncated + ellipsis
        else:
            words = text.split()
            lines: list[str] = []
            current: list[str] = []
            for word in words:
                candidate = " ".join([*current, word])
                if not current or draw.textlength(candidate, font=font) <= max_width:
                    current.append(word)
                else:
                    lines.append(" ".join(current))
                    current = [word]
            if current:
                lines.append(" ".join(current))
            text = "\n".join(lines)

    if not anchor:
        # The integration defaults to a top anchor for single-line text and a
        # baseline-ish one for multi-line.
        anchor = "la" if "\n" in text else "lt"

    if element.get("parse_colors", False):
        _draw_colored_text(
            ctx, x, y, text, font, align, anchor, spacing, stroke_width, stroke_fill
        )
        return

    bbox = draw.textbbox((x, y), text, font=font, anchor=anchor, spacing=spacing, align=align)
    draw_text_run(
        ctx, x, y, text, font, color,
        anchor=anchor, align=align, spacing=spacing,
        stroke_width=stroke_width, stroke_fill=stroke_fill,
    )
    ctx.pos_y = bbox[3]


def _draw_colored_text(ctx, x, y, text, font, align, anchor, spacing, stroke_width, stroke_fill):
    """Draw text containing `[color]…[/color]` markup."""
    draw = ctx.draw
    segments = parse_colored_text(text)

    if "\n" in text:
        lines: list[list[tuple[str, str]]] = [[]]
        for segment_text, segment_color in segments:
            parts = segment_text.split("\n")
            for index, part in enumerate(parts):
                if part:
                    lines[-1].append((part, segment_color))
                if index < len(parts) - 1:
                    lines.append([])
        lines = [line for line in lines if line]

        line_height = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
        block_height = (len(lines) - 1) * (line_height + spacing) + line_height
        _, offset_y = anchor_offset(anchor, 0, block_height)
        adjusted_y = y + offset_y

        max_y = adjusted_y
        for index, line in enumerate(lines):
            line_y = adjusted_y + index * (line_height + spacing)
            max_y = max(
                max_y,
                _draw_segment_line(
                    ctx, line, font, x, line_y, align, anchor,
                    stroke_width, stroke_fill,
                ),
            )
        ctx.pos_y = max_y
        return

    width = sum(font.getlength(segment_text) for segment_text, _ in segments)
    offset_x, _ = anchor_offset(anchor, width, 0)
    if align == "center":
        offset_x -= width / 2
    elif align == "right":
        offset_x -= width

    max_y = y
    cursor = x + offset_x
    for segment_text, segment_color in segments:
        color = ctx.colors.resolve(segment_color)
        bbox = draw.textbbox((cursor, y), segment_text, font=font, anchor="lt")
        draw_text_run(
            ctx, cursor, y, segment_text, font, color,
            anchor="lt", stroke_width=stroke_width, stroke_fill=stroke_fill,
        )
        max_y = max(max_y, bbox[3])
        cursor += font.getlength(segment_text)
    ctx.pos_y = max_y


def _draw_segment_line(ctx, line, font, x, line_y, align, anchor, stroke_width, stroke_fill):
    """Draw one line of colour-markup text. Returns its bottom edge."""
    width = sum(font.getlength(segment_text) for segment_text, _ in line)
    offset_x, _ = anchor_offset(anchor, width, 0)
    if align == "center":
        offset_x -= width / 2
    elif align == "right":
        offset_x -= width

    cursor = x + offset_x
    bottom = line_y
    for segment_text, segment_color in line:
        color = ctx.colors.resolve(segment_color)
        bbox = ctx.draw.textbbox((cursor, line_y), segment_text, font=font, anchor="lt")
        draw_text_run(
            ctx, cursor, line_y, segment_text, font, color,
            anchor="lt", stroke_width=stroke_width, stroke_fill=stroke_fill,
        )
        bottom = max(bottom, bbox[3])
        cursor += font.getlength(segment_text)
    return bottom


@handler("multiline")
def draw_multiline(ctx, element: dict) -> None:
    """Draw delimiter-separated lines, each offset by `offset_y`."""
    draw = ctx.draw
    draw.fontmode = "1"

    size = ctx.coords.size(element.get("size", 20), is_width=False)
    font = load_font(element.get("font", "ppb.ttf"), size)
    color = ctx.colors.resolve(element.get("color", "black"))
    align = element.get("align", "left")
    anchor = element.get("anchor", "lm")
    stroke_width = int(element.get("stroke_width", 0))
    stroke_fill = ctx.colors.resolve(element.get("stroke_fill", "white"))

    x = ctx.coords.x(element["x"])
    if "y" in element:
        current_y = ctx.coords.y(element["y"])
    elif "start_y" in element:
        current_y = ctx.coords.y(element["start_y"])
    else:
        current_y = ctx.pos_y + int(element.get("y_padding", 10))

    # Newlines are dropped: the delimiter is the only line break.
    lines = str(element["value"]).replace("\n", "").split(str(element["delimiter"]))
    offset_y = int(element["offset_y"])

    max_y = current_y
    for line in lines:
        if element.get("parse_colors", False):
            for segment_text, segment_color in parse_colored_text(str(line)):
                segment_color_resolved = ctx.colors.resolve(segment_color)
                bbox = draw.textbbox(
                    (x, current_y), segment_text, font=font, anchor="lt"
                )
                draw_text_run(
                    ctx, x, current_y, segment_text, font, segment_color_resolved,
                    anchor="lt", stroke_width=stroke_width, stroke_fill=stroke_fill,
                )
                max_y = max(max_y, bbox[3])
        else:
            bbox = draw.textbbox(
                (x, current_y), str(line), font=font, anchor=anchor, align=align
            )
            draw_text_run(
                ctx, x, current_y, str(line), font, color,
                anchor=anchor, align=align,
                stroke_width=stroke_width, stroke_fill=stroke_fill,
            )
            max_y = max(max_y, bbox[3])
        current_y += offset_y

    ctx.pos_y = max_y
