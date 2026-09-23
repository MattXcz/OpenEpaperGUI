"""Icon handlers for the preview renderer.

Icons are drawn from the Material Design Icons webfont using the codepoints in
the shipped metadata, exactly like the integration does. An unknown name is
skipped with a note rather than aborting the preview.
"""

from __future__ import annotations

from .fonts import icon_glyph, load_font
from .text import handler


def _draw_glyph(ctx, element: dict, glyph: str, x: int, y: int, size: int, fill) -> tuple:
    """Draw one MDI glyph and return its bounding box."""
    font = load_font("materialdesignicons-webfont.ttf", size)
    anchor = element.get("anchor", "la")
    stroke_width = int(element.get("stroke_width", 0))
    stroke_fill = ctx.colors.resolve(element.get("stroke_fill", "white"))
    ctx.draw.text(
        (x, y),
        glyph,
        fill=fill,
        font=font,
        anchor=anchor,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )
    return ctx.draw.textbbox((x, y), glyph, font=font, anchor=anchor)


@handler("icon")
def draw_icon(ctx, element: dict) -> None:
    ctx.draw.fontmode = "1"

    x = ctx.coords.x(element["x"])
    y = ctx.coords.y(element["y"])
    size = int(element["size"])
    # The integration accepts either `color` or `fill` here.
    fill = ctx.colors.resolve(element.get("color") or element.get("fill", "black"))

    glyph = icon_glyph(element["value"])
    if glyph is None:
        raise KeyError(f"unknown icon name '{element['value']}'")

    bbox = _draw_glyph(ctx, element, glyph, x, y, size, fill)
    ctx.pos_y = bbox[3]


@handler("icon_sequence")
def draw_icon_sequence(ctx, element: dict) -> None:
    ctx.draw.fontmode = "1"

    x_start = ctx.coords.x(element["x"])
    y_start = ctx.coords.y(element["y"])
    size = int(element["size"])
    # Default spacing is a quarter of the icon size.
    spacing = element.get("spacing")
    spacing = size // 4 if spacing is None else int(spacing)
    fill = ctx.colors.resolve(element.get("fill", "black"))
    direction = element.get("direction", "right")

    current_x, current_y = x_start, y_start
    max_x, max_y = x_start, y_start

    for name in element["icons"]:
        glyph = icon_glyph(name)
        if glyph is None:
            ctx.errors.append(f"Icon sequence: unknown icon name '{name}'")
            continue

        bbox = _draw_glyph(ctx, element, glyph, current_x, current_y, size, fill)
        max_x = max(max_x, bbox[2])
        max_y = max(max_y, bbox[3])

        step = size + spacing
        if direction == "right":
            current_x += step
        elif direction == "left":
            current_x -= step
        elif direction == "down":
            current_y += step
        elif direction == "up":
            current_y -= step

    ctx.pos_y = max(max_y, current_y)
