"""Pixel-accurate preview rendering of drawcustom payloads.

Public entry point is :func:`render_payload`, which returns PNG bytes plus any
per-element errors and notes about what could not be shown.
"""

from __future__ import annotations

# Importing these registers every handler with the dispatcher.
from . import icons, media, shapes, text, visualizations  # noqa: E402,F401
from .colors import ColorResolver
from .coordinates import Coordinates, parse_dimension
from .fonts import assets_available, icon_glyph, load_font, mdi_codepoints
from .renderer import DrawContext, RenderError, render_payload

__all__ = [
    "ColorResolver",
    "Coordinates",
    "DrawContext",
    "RenderError",
    "assets_available",
    "icon_glyph",
    "load_font",
    "mdi_codepoints",
    "parse_dimension",
    "render_payload",
]
