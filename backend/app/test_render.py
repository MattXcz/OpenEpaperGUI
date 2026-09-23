"""Tests for the pixel-accurate preview renderer.

Run with:  python -m pytest -q app
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from .render import ColorResolver, assets_available, icon_glyph, render_payload
from .render.colors import BLACK, HALF_RED, RED, WHITE, YELLOW
from .render.coordinates import parse_dimension

pytestmark = pytest.mark.skipif(
    not assets_available(),
    reason="font assets missing; run backend/scripts/fetch_assets.py",
)


def _render(payload: list[dict], **kwargs) -> tuple[Image.Image, list[str], list[str]]:
    width = kwargs.pop("width", 200)
    height = kwargs.pop("height", 100)
    png, errors, notes = render_payload(payload, width=width, height=height, **kwargs)
    return Image.open(io.BytesIO(png)).convert("RGB"), errors, notes


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

def test_named_colors_and_shortcuts() -> None:
    resolver = ColorResolver("red")
    assert resolver.resolve("black") == BLACK
    assert resolver.resolve("b") == BLACK
    assert resolver.resolve("white") == WHITE
    assert resolver.resolve("red") == RED
    assert resolver.resolve("yellow") == YELLOW
    assert resolver.resolve("half_red") == HALF_RED
    assert resolver.resolve("hr") == HALF_RED
    assert resolver.resolve("gray") == resolver.resolve("grey")


def test_accent_follows_the_tag() -> None:
    assert ColorResolver("red").resolve("accent") == RED
    assert ColorResolver("yellow").resolve("accent") == YELLOW
    assert ColorResolver("yellow").resolve("ha") == ColorResolver("yellow").resolve("half_accent")


def test_hex_colors() -> None:
    resolver = ColorResolver()
    assert resolver.resolve("#f00") == (255, 0, 0, 255)
    assert resolver.resolve("#ff0000") == (255, 0, 0, 255)
    assert resolver.resolve("#00ff00") == (0, 255, 0, 255)
    # Malformed hex falls back to white rather than raising.
    assert resolver.resolve("#zz") == WHITE


def test_none_means_no_color() -> None:
    assert ColorResolver().resolve(None) is None
    assert ColorResolver().resolve("") is None


# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------

def test_parse_dimension() -> None:
    assert parse_dimension(50, 200) == 50
    assert parse_dimension("50", 200) == 50
    assert parse_dimension("50%", 200) == 100
    assert parse_dimension("12.7", 200) == 12
    assert parse_dimension("nonsense", 200) == 0
    assert parse_dimension(None, 200) == 0
    # bools are not numbers here, they would otherwise become 1/0 silently.
    assert parse_dimension(True, 200) == 0


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def test_canvas_size_and_background() -> None:
    image, errors, _ = _render([], width=296, height=128)
    assert image.size == (296, 128)
    assert not errors
    assert image.getpixel((0, 0)) == (255, 255, 255)


def test_black_background() -> None:
    image, _, _ = _render([], background="black")
    assert image.getpixel((0, 0)) == (0, 0, 0)


def test_text_is_drawn() -> None:
    image, errors, _ = _render(
        [{"type": "text", "value": "Hi", "x": 2, "y": 2, "size": 40}]
    )
    assert not errors
    # Some pixel in the top-left quadrant must be dark.
    dark = sum(
        1
        for x in range(0, 80)
        for y in range(0, 50)
        if sum(image.getpixel((x, y))) < 200
    )
    assert dark > 10, "text did not render"


def test_rotation_keeps_the_declared_canvas_size() -> None:
    """Rotation changes how coordinates are interpreted, not the output size.

    The integration allocates a swapped canvas for 90/270, draws into it and
    rotates back with `expand=True`, so the final image is always width x height
    while the content is laid out in the rotated frame.
    """
    image, _, _ = _render([], width=296, height=128, rotate=90)
    assert image.size == (296, 128)


def test_rotation_moves_drawn_content() -> None:
    """Rotating reinterprets coordinates, so content lands elsewhere.

    A 90 degree rotation draws into a swapped canvas and rotates back, which
    moves a mark at the origin to the right-hand edge.
    """
    upright, _, _ = _render(
        [{"type": "rectangle", "x_start": 0, "x_end": 10, "y_start": 0, "y_end": 10,
          "fill": "black"}],
        width=100, height=50, rotate=0,
    )
    rotated, _, _ = _render(
        [{"type": "rectangle", "x_start": 0, "x_end": 10, "y_start": 0, "y_end": 10,
          "fill": "black"}],
        width=100, height=50, rotate=90,
    )
    assert upright.getpixel((5, 5)) == (0, 0, 0)
    assert rotated.getpixel((5, 5)) == (255, 255, 255), "content should have moved"
    assert rotated.getpixel((95, 5)) == (0, 0, 0), "content should be at the right edge"


def test_unknown_element_is_reported_not_raised() -> None:
    image, errors, _ = _render([{"type": "not_a_type"}])
    assert image.size == (200, 100)
    assert errors and "unknown type" in errors[0]


def test_missing_required_key_is_reported() -> None:
    _, errors, _ = _render([{"type": "circle", "x": 1, "y": 2}])
    assert errors and "radius" in errors[0]


def test_one_bad_element_does_not_stop_the_rest() -> None:
    image, errors, _ = _render([
        {"type": "circle", "x": 1, "y": 2},  # missing radius
        {"type": "rectangle", "x_start": 0, "x_end": 50, "y_start": 0, "y_end": 50,
         "fill": "black"},
    ])
    assert errors, "the broken element should be reported"
    assert image.getpixel((25, 25)) == (0, 0, 0), "the good element should still draw"


def test_hidden_elements_are_skipped() -> None:
    image, errors, _ = _render([
        {"type": "rectangle", "x_start": 0, "x_end": 50, "y_start": 0, "y_end": 50,
         "fill": "black", "visible": False},
    ])
    assert not errors
    assert image.getpixel((25, 25)) == (255, 255, 255)


def test_percentage_coordinates() -> None:
    image, _, _ = _render(
        [{"type": "circle", "x": "50%", "y": "50%", "radius": 5, "fill": "black"}],
        width=200, height=100,
    )
    assert image.getpixel((100, 50)) == (0, 0, 0)


def test_progress_bar_fill_direction() -> None:
    image, _, _ = _render([{
        "type": "progress_bar",
        "x_start": 0, "y_start": 0, "x_end": 100, "y_end": 20,
        "progress": 50, "fill": "red", "outline": "black",
    }])
    # Half-filled: left side red, right side still the white background.
    assert image.getpixel((10, 10))[0] > 200 and image.getpixel((10, 10))[1] < 100
    assert image.getpixel((90, 10)) == (255, 255, 255)


def test_progress_is_clamped() -> None:
    image, _, _ = _render([{
        "type": "progress_bar",
        "x_start": 0, "y_start": 0, "x_end": 100, "y_end": 20,
        "progress": 500, "fill": "red", "outline": "black",
    }])
    assert image.getpixel((95, 10))[0] > 200, "progress must clamp to 100"


def test_polygon_ignores_width_like_the_integration() -> None:
    """The integration always strokes polygons 1px; the preview must match."""
    _, errors, _ = _render([{
        "type": "polygon", "points": [[10, 10], [50, 10], [30, 40]],
        "outline": "black", "width": 9,
    }])
    assert not errors


def test_icon_glyph_resolution() -> None:
    assert icon_glyph("mdi:home") is not None
    assert icon_glyph("home") is not None
    assert icon_glyph("mdi:definitely-not-an-icon") is None


def test_icon_renders_something() -> None:
    image, errors, _ = _render(
        [{"type": "icon", "value": "mdi:home", "x": 2, "y": 2, "size": 48}]
    )
    assert not errors
    dark = sum(
        1
        for x in range(0, 60)
        for y in range(0, 60)
        if sum(image.getpixel((x, y))) < 200
    )
    assert dark > 20, "icon did not render"


def test_unknown_icon_is_reported() -> None:
    _, errors, _ = _render(
        [{"type": "icon", "value": "mdi:not-real", "x": 0, "y": 0, "size": 20}]
    )
    assert errors and "not-real" in errors[0]


def test_qrcode_is_drawn() -> None:
    image, errors, _ = _render(
        [{"type": "qrcode", "data": "https://example.com", "x": 2, "y": 2}]
    )
    assert not errors
    dark = sum(
        1
        for x in range(0, 60)
        for y in range(0, 60)
        if sum(image.getpixel((x, y))) < 200
    )
    assert dark > 20, "QR code did not render"


def test_plot_frame_and_note() -> None:
    """A plot cannot fetch history, so it draws a frame and says so."""
    _, errors, notes = _render([{
        "type": "plot", "x_start": 0, "y_start": 0, "x_end": 100, "y_end": 60,
        "data": [{"entity": "sensor.temperature"}],
    }])
    assert not errors
    assert notes and "history" in notes[0]


def test_remote_image_is_a_note_not_an_error() -> None:
    _, errors, notes = _render([{
        "type": "dlimg", "url": "https://example.com/x.png",
        "x": 0, "y": 0, "xsize": 40, "ysize": 40,
    }])
    assert not errors
    assert notes and "remote" in notes[0]


def test_color_markup_renders() -> None:
    image, errors, _ = _render([{
        "type": "text", "value": "[red]R[/red]", "x": 2, "y": 2,
        "size": 40, "parse_colors": True,
    }])
    assert not errors
    reddish = sum(
        1
        for x in range(0, 60)
        for y in range(0, 50)
        if image.getpixel((x, y))[0] > 150 and image.getpixel((x, y))[1] < 100
    )
    assert reddish > 5, "color markup did not apply"


def test_multiline_uses_delimiter() -> None:
    _, errors, _ = _render([{
        "type": "multiline", "value": "A|B|C", "delimiter": "|",
        "x": 0, "y": 0, "offset_y": 20, "size": 12,
    }])
    assert not errors


def test_invalid_canvas_is_rejected() -> None:
    from .render import RenderError

    with pytest.raises(RenderError):
        render_payload([], width=0, height=10)


def test_output_is_a_paletted_png() -> None:
    """E-paper is 1-bit per channel, so the preview is quantised too."""
    png, _, _ = render_payload(
        [{"type": "circle", "x": 20, "y": 20, "radius": 10, "fill": "red"}],
        width=60, height=60,
    )
    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG"
    assert image.mode == "P"
