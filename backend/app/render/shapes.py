"""Shape handlers for the preview renderer.

Rectangles, lines, polygons, circles, ellipses and arcs, with the same rounding
and dash behaviour the integration applies.
"""

from __future__ import annotations

import math

from .text import handler


def _rounded_corners(spec: str) -> tuple[bool, bool, bool, bool]:
    """Parse a `corners` value into (top_left, top_right, bottom_right, bottom_left)."""
    if spec == "all":
        return True, True, True, True
    order = {"top_left": 0, "top_right": 1, "bottom_right": 2, "bottom_left": 3}
    flags = [False] * 4
    for part in str(spec).split(","):
        index = order.get(part.strip())
        if index is not None:
            flags[index] = True
    return flags[0], flags[1], flags[2], flags[3]


def draw_dashed_line(
    draw,
    start: tuple[float, float],
    end: tuple[float, float],
    dash_length: float,
    space_length: float,
    fill,
    width: int = 1,
) -> None:
    """Draw a dashed segment by walking the line and alternating dash/space."""
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return

    step_x, step_y = dx / length, dy / length
    position = 0.0
    while position < length:
        dash_end = min(position + dash_length, length)
        draw.line(
            [
                (x1 + step_x * position, y1 + step_y * position),
                (x1 + step_x * dash_end, y1 + step_y * dash_end),
            ],
            fill=fill,
            width=width,
        )
        position = dash_end + space_length


@handler("line")
def draw_line(ctx, element: dict) -> None:
    # y is optional: without it the line sits at the previous element's bottom.
    if "y_start" not in element:
        y_start = ctx.pos_y + int(element.get("y_padding", 0))
        y_end = y_start
    else:
        y_start = ctx.coords.y(element["y_start"])
        y_end = ctx.coords.y(element.get("y_end", element["y_start"]))

    x_start = ctx.coords.x(element["x_start"])
    x_end = ctx.coords.x(element["x_end"])
    fill = ctx.colors.resolve(element.get("fill", "black"))
    width = int(element.get("width", 1))

    if element.get("dashed", False):
        draw_dashed_line(
            ctx.draw,
            (x_start, y_start),
            (x_end, y_end),
            float(element.get("dash_length", 5)),
            float(element.get("space_length", 3)),
            fill,
            width,
        )
    else:
        ctx.draw.line([(x_start, y_start), (x_end, y_end)], fill=fill, width=width)

    ctx.pos_y = max(y_start, y_end)


@handler("rectangle")
def draw_rectangle(ctx, element: dict) -> None:
    x_start = ctx.coords.x(element["x_start"])
    x_end = ctx.coords.x(element["x_end"])
    y_start = ctx.coords.y(element["y_start"])
    y_end = ctx.coords.y(element["y_end"])

    fill = ctx.colors.resolve(element.get("fill"))
    outline = ctx.colors.resolve(element.get("outline", "black"))
    width = int(element.get("width", 1))
    # The integration defaults the radius to 10 as soon as `corners` is present.
    default_radius = 10 if "corners" in element else 0
    radius = int(element.get("radius", default_radius))
    corners = _rounded_corners(
        element.get("corners", "all" if "radius" in element else "")
    )

    ctx.draw.rounded_rectangle(
        (x_start, y_start, x_end, y_end),
        fill=fill,
        outline=outline,
        width=width,
        radius=radius,
        corners=corners,
    )
    ctx.pos_y = y_end


@handler("rectangle_pattern")
def draw_rectangle_pattern(ctx, element: dict) -> None:
    fill = ctx.colors.resolve(element.get("fill"))
    outline = ctx.colors.resolve(element.get("outline", "black"))
    width = int(element.get("width", 1))
    default_radius = 10 if "corners" in element else 0
    radius = int(element.get("radius", default_radius))
    corners = _rounded_corners(
        element.get("corners", "all" if "radius" in element else "")
    )

    x_start = int(element["x_start"])
    y_start = int(element["y_start"])
    x_size = int(element["x_size"])
    y_size = int(element["y_size"])
    x_offset = int(element["x_offset"])
    y_offset = int(element["y_offset"])

    max_y = y_start
    for column in range(int(element["x_repeat"])):
        for row in range(int(element["y_repeat"])):
            x_pos = x_start + column * (x_offset + x_size)
            y_pos = y_start + row * (y_offset + y_size)
            ctx.draw.rounded_rectangle(
                (x_pos, y_pos, x_pos + x_size, y_pos + y_size),
                fill=fill,
                outline=outline,
                width=width,
                radius=radius,
                corners=corners,
            )
            max_y = max(max_y, y_pos + y_size)

    ctx.pos_y = max_y


@handler("polygon")
def draw_polygon(ctx, element: dict) -> None:
    vertices = [
        (ctx.coords.x(x), ctx.coords.y(y)) for x, y in element["points"]
    ]
    fill = ctx.colors.resolve(element.get("fill"))
    outline = ctx.colors.resolve(element.get("outline", "black"))

    # Note: the integration ignores `width` for polygons and always strokes 1px.
    ctx.draw.polygon(vertices, fill=fill, outline=outline)

    if vertices:
        ctx.pos_y = max(vertex[1] for vertex in vertices)


@handler("circle")
def draw_circle(ctx, element: dict) -> None:
    x = ctx.coords.x(element["x"])
    y = ctx.coords.y(element["y"])
    radius = int(element["radius"])
    fill = ctx.colors.resolve(element.get("fill"))
    outline = ctx.colors.resolve(element.get("outline", "black"))
    width = int(element.get("width", 1))

    ctx.draw.ellipse(
        [(x - radius, y - radius), (x + radius, y + radius)],
        fill=fill,
        outline=outline,
        width=width,
    )
    ctx.pos_y = y + radius


@handler("ellipse")
def draw_ellipse(ctx, element: dict) -> None:
    x_start = ctx.coords.x(element["x_start"])
    x_end = ctx.coords.x(element["x_end"])
    y_start = ctx.coords.y(element["y_start"])
    y_end = ctx.coords.y(element["y_end"])
    fill = ctx.colors.resolve(element.get("fill"))
    outline = ctx.colors.resolve(element.get("outline", "black"))
    width = int(element.get("width", 1))

    ctx.draw.ellipse(
        [(x_start, y_start), (x_end, y_end)],
        fill=fill,
        outline=outline,
        width=width,
    )
    ctx.pos_y = y_end


@handler("arc")
def draw_arc(ctx, element: dict) -> None:
    x = ctx.coords.x(element["x"])
    y = ctx.coords.y(element["y"])
    radius = ctx.coords.size(element["radius"], is_width=True)
    start_angle = float(element["start_angle"])
    end_angle = float(element["end_angle"])

    bbox = [(x - radius, y - radius), (x + radius, y + radius)]
    fill = ctx.colors.resolve(element.get("fill"))
    outline = ctx.colors.resolve(element.get("outline", "black"))
    width = int(element.get("width", 1))

    if fill:
        # A fill turns the arc into a pie slice.
        ctx.draw.pieslice(bbox, start=start_angle, end=end_angle, fill=fill, outline=outline)
    else:
        ctx.draw.arc(bbox, start=start_angle, end=end_angle, fill=outline, width=width)

    ctx.pos_y = y + radius


@handler("debug_grid")
def draw_debug_grid(ctx, element: dict) -> None:
    width, height = ctx.image.size
    spacing = int(element.get("spacing", 20))
    line_color = ctx.colors.resolve(element.get("line_color", "black"))
    dashed = element.get("dashed", True)
    dash_length = float(element.get("dash_length", 2))
    space_length = float(element.get("space_length", 4))
    show_labels = element.get("show_labels", True)
    label_step = int(element.get("label_step", spacing * 2))
    label_color = ctx.colors.resolve(element.get("label_color", "black"))
    label_font_size = int(element.get("label_font_size", 12))
    font = load_font_safe(element.get("font", "ppb.ttf"), label_font_size)

    def segment(start, end):
        if dashed:
            draw_dashed_line(
                ctx.draw, start, end, dash_length, space_length, line_color, 1
            )
        else:
            ctx.draw.line([start, end], fill=line_color, width=1)

    for y in range(0, height, spacing):
        segment((0, y), (width, y))
        if show_labels and label_step and y % label_step == 0:
            ctx.draw.text((2, y + 2), str(y), fill=label_color, font=font)

    for x in range(0, width, spacing):
        segment((x, 0), (x, height))
        if show_labels and label_step and x % label_step == 0:
            ctx.draw.text((x + 2, 2), str(x), fill=label_color, font=font)

    ctx.pos_y = height


def load_font_safe(name: str, size: int):
    """Load a font for label drawing, tolerating a missing asset."""
    from .fonts import load_font

    return load_font(name, size)
