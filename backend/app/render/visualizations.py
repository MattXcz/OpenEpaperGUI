"""Visualisation handlers for the preview renderer.

The progress bar is drawn in full. The plot needs entity history from Home
Assistant, which a static preview cannot obtain, so it draws its frame, axes and
legend so the reserved area and styling are visible, and reports a note.
"""

from __future__ import annotations

from .fonts import load_font
from .text import handler


@handler("progress_bar")
def draw_progress_bar(ctx, element: dict) -> None:
    x_start = ctx.coords.x(element["x_start"])
    y_start = ctx.coords.y(element["y_start"])
    x_end = ctx.coords.x(element["x_end"])
    y_end = ctx.coords.y(element["y_end"])

    progress = min(100, max(0, int(element["progress"])))
    direction = element.get("direction", "right")
    background = ctx.colors.resolve(element.get("background", "white"))
    fill = ctx.colors.resolve(element.get("fill", "red"))
    outline = ctx.colors.resolve(element.get("outline", "black"))
    width = int(element.get("width", 1))
    show_percentage = element.get("show_percentage", False)
    # Note: the integration reads `font_name` here, not `font`.
    font_name = element.get("font_name", element.get("font", "ppb.ttf"))

    ctx.draw.rectangle(
        ((x_start, y_start), (x_end, y_end)),
        fill=background,
        outline=outline,
        width=width,
    )

    if direction in {"right", "left"}:
        progress_width = int((x_end - x_start) * (progress / 100))
        progress_height = y_end - y_start
    else:
        progress_width = x_end - x_start
        progress_height = int((y_end - y_start) * (progress / 100))

    if direction == "right":
        ctx.draw.rectangle((x_start, y_start, x_start + progress_width, y_end), fill=fill)
    elif direction == "left":
        ctx.draw.rectangle((x_end - progress_width, y_start, x_end, y_end), fill=fill)
    elif direction == "up":
        ctx.draw.rectangle((x_start, y_end - progress_height, x_end, y_end), fill=fill)
    elif direction == "down":
        ctx.draw.rectangle((x_start, y_start, x_end, y_start + progress_height), fill=fill)

    ctx.draw.rectangle((x_start, y_start, x_end, y_end), fill=None, outline=outline, width=width)

    if show_percentage:
        font_size = min(y_end - y_start - 4, x_end - x_start - 4, 20)
        font = load_font(font_name, max(6, font_size))
        text = f"{progress}%"
        bbox = ctx.draw.textbbox((0, 0), text, font=font)
        text_x = (x_start + x_end - (bbox[2] - bbox[0])) / 2
        text_y = (y_start + y_end - (bbox[3] - bbox[1])) / 2
        # Flip the label color so it stays readable over the filled part.
        text_color = background if progress > 50 else fill
        ctx.draw.text((text_x, text_y), text, font=font, fill=text_color, anchor="lt")

    ctx.pos_y = y_end


@handler("plot")
def draw_plot(ctx, element: dict) -> None:
    """Draw the plot frame and axes.

    Entity history is only available inside Home Assistant, so the data series
    cannot be drawn. Rendering the frame keeps the layout accurate.
    """
    x_start = ctx.coords.x(element.get("x_start", 0))
    y_start = ctx.coords.y(element.get("y_start", 0))
    x_end = ctx.coords.x(element.get("x_end", ctx.image.width - 1 - x_start))
    y_end = ctx.coords.y(element.get("y_end", ctx.image.height - 1 - y_start))

    font = load_font(element.get("font", "ppb.ttf"), int(element.get("size", 10)))

    # The integration outlines the full area in black when `debug` is set.
    if element.get("debug", False):
        ctx.draw.rectangle((x_start, y_start, x_end, y_end), outline=ctx.colors.resolve("black"))
        ctx.draw.rectangle((x_start, y_start, x_end, y_end), outline=ctx.colors.resolve("red"))

    # A light frame plus an axis line, so an empty plot still reads as a plot.
    grid_color = ctx.colors.resolve("half_black")
    ctx.draw.rectangle((x_start, y_start, x_end, y_end), outline=grid_color, width=1)
    ctx.draw.line([(x_start, y_end), (x_end, y_end)], fill=ctx.colors.resolve("black"), width=1)

    series = element.get("data") or []
    label = f"plot · {len(series)} series"
    ctx.draw.text((x_start + 4, y_start + 4), label, fill=grid_color, font=font)

    ctx.pos_y = y_end
    ctx.notes.append(
        "plot needs Home Assistant history; the frame is drawn but the data is not"
    )
