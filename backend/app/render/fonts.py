"""Font loading for the preview renderer.

Loads the bundled fonts and the Material Design Icons webfont, and resolves MDI
names to their codepoints via the shipped metadata. Everything is cached: the
metadata file is 3 MB of JSON and re-reading it per element would dominate the
render time.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"

DEFAULT_FONT = "ppb.ttf"
MDI_FONT_FILE = "materialdesignicons-webfont.ttf"
MDI_META_FILE = "materialdesignicons-webfont_meta.json"

# Bounded so a preview with many sizes cannot grow the cache without limit.
_FONT_CACHE_SIZE = 64


class FontUnavailable(RuntimeError):
    """Raised when a requested font file is not present in the image."""


def assets_available() -> bool:
    """Whether the font assets have been fetched."""
    return (ASSETS_DIR / DEFAULT_FONT).exists() and (ASSETS_DIR / MDI_FONT_FILE).exists()


@lru_cache(maxsize=_FONT_CACHE_SIZE)
def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font at a pixel size.

    Falls back to the default font when the requested file is missing, matching
    the integration's behaviour.
    """
    size = max(1, int(size))
    path = ASSETS_DIR / str(name)
    if not path.exists():
        path = ASSETS_DIR / DEFAULT_FONT
    if not path.exists():
        raise FontUnavailable(
            f"Font assets are missing from {ASSETS_DIR}. "
            "Run backend/scripts/fetch_assets.py or rebuild the Docker image."
        )
    return ImageFont.truetype(str(path), size)


@lru_cache(maxsize=1)
def mdi_codepoints() -> dict[str, str]:
    """Map every MDI name and alias to its codepoint (hex string, no `0x`)."""
    meta_path = ASSETS_DIR / MDI_META_FILE
    if not meta_path.exists():
        return {}

    try:
        entries = json.loads(meta_path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    mapping: dict[str, str] = {}
    for entry in entries:
        codepoint = entry.get("codepoint")
        name = entry.get("name")
        if not codepoint or not name:
            continue
        mapping[name] = codepoint
        for alias in entry.get("aliases") or ():
            # A name always wins over an alias, so only fill gaps.
            mapping.setdefault(alias, codepoint)
    return mapping


def icon_glyph(value: object) -> str | None:
    """Resolve an icon name (`mdi:home`, `home`) to its glyph character."""
    name = str(value or "").strip()
    if name.startswith("mdi:"):
        name = name[4:]
    codepoint = mdi_codepoints().get(name)
    if not codepoint:
        return None
    try:
        return chr(int(codepoint, 16))
    except ValueError:
        return None
