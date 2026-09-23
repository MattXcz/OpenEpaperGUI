"""Coordinate parsing for the preview renderer.

Positions may be absolute pixels or percentages of the canvas, and `int()`
truncation is applied the same way the integration does it so a preview lines up
with the tag to the pixel.
"""

from __future__ import annotations

Number: type = int | float


def parse_dimension(value: object, total: int) -> int:
    """Convert a dimension to absolute pixels.

    Percentages are relative to ``total``; anything unparseable becomes 0.
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip()
    if not text:
        return 0

    if text.endswith("%"):
        try:
            return int((float(text[:-1]) / 100) * total)
        except ValueError:
            return 0

    try:
        return int(float(text))
    except ValueError:
        return 0


class Coordinates:
    """Parses x/y/size values against a canvas size."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def x(self, value: object) -> int:
        return parse_dimension(value, self.width)

    def y(self, value: object) -> int:
        return parse_dimension(value, self.height)

    def size(self, value: object, *, is_width: bool = True) -> int:
        return parse_dimension(value, self.width if is_width else self.height)
