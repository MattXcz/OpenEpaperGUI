"""Color resolution for the preview renderer.

Mirrors the palette the OpenEPaperLink integration draws with so a preview
matches what the tag will show: named colors, the `half_*` halftones, single
letter shortcuts and hex values, with `accent` resolving to the tag's own
accent color.
"""

from __future__ import annotations

from typing import TypeAlias

RGBA: TypeAlias = tuple[int, int, int, int]

WHITE: RGBA = (255, 255, 255, 255)
BLACK: RGBA = (0, 0, 0, 255)
HALF_BLACK: RGBA = (127, 127, 127, 255)
RED: RGBA = (255, 0, 0, 255)
HALF_RED: RGBA = (255, 127, 127, 255)
YELLOW: RGBA = (255, 255, 0, 255)
HALF_YELLOW: RGBA = (255, 255, 127, 255)

_NAMED: dict[str, RGBA] = {
    "black": BLACK, "b": BLACK,
    "white": WHITE, "w": WHITE,
    "red": RED, "r": RED,
    "yellow": YELLOW, "y": YELLOW,
    "half_black": HALF_BLACK, "hb": HALF_BLACK,
    "half_white": HALF_BLACK, "hw": HALF_BLACK,
    "gray": HALF_BLACK, "grey": HALF_BLACK, "g": HALF_BLACK,
    "half_red": HALF_RED, "hr": HALF_RED,
    "half_yellow": HALF_YELLOW, "hy": HALF_YELLOW,
}

_ACCENT_KEYS = {"accent", "a"}
_HALF_ACCENT_KEYS = {"half_accent", "ha"}


class ColorResolver:
    """Turns a drawcustom color value into an RGBA tuple.

    Unknown names resolve to white, matching the integration. `accent` follows
    the tag: red or yellow, chosen by the caller.
    """

    def __init__(self, accent: str = "red") -> None:
        self.accent = "yellow" if str(accent).lower() == "yellow" else "red"

    def resolve(self, color: object) -> RGBA | None:
        """Resolve a color. ``None`` stays ``None`` (meaning "no fill")."""
        if color is None:
            return None

        text = str(color).strip().lower()
        if not text:
            return None

        if text.startswith("#"):
            return self._parse_hex(text[1:])

        if text in _ACCENT_KEYS:
            return YELLOW if self.accent == "yellow" else RED
        if text in _HALF_ACCENT_KEYS:
            return HALF_YELLOW if self.accent == "yellow" else HALF_RED

        return _NAMED.get(text, WHITE)

    @staticmethod
    def _parse_hex(value: str) -> RGBA:
        """Parse `#RGB` or `#RRGGBB` (the `#` already stripped)."""
        try:
            if len(value) == 3:
                return (
                    int(value[0] * 2, 16),
                    int(value[1] * 2, 16),
                    int(value[2] * 2, 16),
                    255,
                )
            if len(value) == 6:
                return (
                    int(value[0:2], 16),
                    int(value[2:4], 16),
                    int(value[4:6], 16),
                    255,
                )
        except ValueError:
            pass
        return WHITE
