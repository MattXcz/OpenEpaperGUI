"""Server-side rendering of a drawcustom payload to a PNG.

This is the *real* renderer: the same Pillow operations, fonts, colors and
coordinate rules the OpenEPaperLink integration uses when it draws to a tag, so
the preview is pixel-accurate rather than an approximation.

Written from the documented behaviour of
``custom_components/open_epaper_link/imagegen`` (Apache-2.0); no code is copied.
The layout, colour and coordinate rules were reimplemented against the same
public contract, which is what makes the output line up.

Only the drawing is implemented here. Data that lives in Home Assistant (entity
history for `plot`, remote images for `dlimg`) is not fetched: a `plot` renders
an empty frame and a `dlimg` renders a labelled placeholder, so the layout is
still visible without the preview depending on a live instance.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageDraw

from .colors import ColorResolver
from .coordinates import Coordinates
from .fonts import assets_available
from .text import HANDLERS, UnsupportedElement


class RenderError(RuntimeError):
    """Raised when the payload cannot be rendered at all."""


@dataclass
class DrawContext:
    """State shared by the element handlers while drawing one image."""

    image: Image.Image
    colors: ColorResolver
    coords: Coordinates
    # Y position the previous element ended at, used when `y` is omitted.
    pos_y: int = 0
    # Non-fatal per-element problems, reported alongside the image.
    errors: list[str] = field(default_factory=list)
    # Set when the payload asked for something a static preview cannot show.
    notes: list[str] = field(default_factory=list)

    @property
    def draw(self) -> ImageDraw.ImageDraw:
        return ImageDraw.Draw(self.image)


def render_payload(
    payload: list[dict],
    *,
    width: int,
    height: int,
    accent: str = "red",
    background: str = "white",
    rotate: int = 0,
) -> tuple[bytes, list[str], list[str]]:
    """Render a payload to PNG bytes.

    Returns ``(png_bytes, errors, notes)``. Per-element failures are collected
    rather than raised, matching how the integration skips a broken element and
    keeps drawing the rest.
    """
    if width <= 0 or height <= 0:
        raise RenderError(f"Invalid canvas size: {width}x{height}")
    if not assets_available():
        raise RenderError(
            "Font assets are not available. Run backend/scripts/fetch_assets.py "
            "or rebuild the Docker image."
        )

    colors = ColorResolver(accent)

    # A 90/270 rotation swaps the canvas, exactly as the integration does.
    if rotate in (90, 270):
        image = Image.new("RGBA", (height, width), colors.resolve(background))
    else:
        image = Image.new("RGBA", (width, height), colors.resolve(background))

    ctx = DrawContext(
        image=image,
        colors=colors,
        coords=Coordinates(image.width, image.height),
    )

    for index, element in enumerate(payload or []):
        if not isinstance(element, dict):
            ctx.errors.append(f"Element {index + 1}: expected an object")
            continue
        if element.get("visible", True) is False:
            continue

        element_type = element.get("type")
        handler = HANDLERS.get(element_type)
        if handler is None:
            ctx.errors.append(f"Element {index + 1}: unknown type '{element_type}'")
            continue

        try:
            handler(ctx, element)
        except UnsupportedElement as exc:
            ctx.notes.append(f"Element {index + 1}: {exc}")
        except KeyError as exc:
            ctx.errors.append(
                f"Element {index + 1} (type '{element_type}'): missing required key {exc}"
            )
        except Exception as exc:  # noqa: BLE001 - one bad element must not kill the preview
            ctx.errors.append(
                f"Element {index + 1} (type '{element_type}'): {type(exc).__name__}: {exc}"
            )

    if rotate:
        image = image.rotate(-rotate, expand=True)

    return _to_png(image), ctx.errors, ctx.notes


def _to_png(image: Image.Image) -> bytes:
    """Encode as a paletted PNG.

    E-paper is 1-bit per channel, so quantising here keeps the preview honest:
    what looks right on screen is what the tag can actually show.
    """
    buffer = io.BytesIO()
    image.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=8).save(
        buffer, format="PNG", optimize=True
    )
    return buffer.getvalue()


def text_width(text: str, font: Any) -> float:
    """Width of a string in pixels."""
    return font.getlength(text)
