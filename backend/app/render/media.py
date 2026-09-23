"""Media handlers for the preview renderer: QR codes and images.

QR codes are generated locally with the same parameters the integration uses
(version 1, high error correction). Images that live outside the editor — a
remote URL, an entity picture — cannot be fetched here, so they render as a
labelled placeholder that keeps the layout visible.
"""

from __future__ import annotations

import base64
import io
import urllib.parse
from pathlib import Path

from PIL import Image

from .text import UnsupportedElement, handler


@handler("qrcode")
def draw_qrcode(ctx, element: dict) -> None:
    import qrcode

    x = ctx.coords.x(element["x"])
    y = ctx.coords.y(element["y"])
    color = ctx.colors.resolve(element.get("color", "black"))
    background = ctx.colors.resolve(element.get("bgcolor", "white"))
    border = int(element.get("border", 1))
    box_size = int(element.get("boxsize", 2))

    code = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    code.add_data(str(element["data"]))
    code.make(fit=True)

    # qrcode wants plain RGB; the RGBA tuples are trimmed to their first three
    # components exactly as the integration does.
    image = code.make_image(fill_color=color[:3], back_color=background[:3]).convert("RGBA")

    ctx.image.paste(image, (x, y), image)
    ctx.pos_y = y + image.height


@handler("dlimg")
def draw_downloaded_image(ctx, element: dict) -> None:
    """Render an image element.

    Only data URIs and paths that are already on disk can be resolved. Anything
    that would need a network fetch or a Home Assistant entity is reported as a
    note so the preview stays honest about what it could not show.
    """
    x = ctx.coords.x(element["x"])
    y = ctx.coords.y(element["y"])
    x_size = int(element["xsize"])
    y_size = int(element["ysize"])
    rotate = int(element.get("rotate", 0))
    resize_method = element.get("resize_method", "stretch")
    url = str(element["url"])

    source: Image.Image | None = None

    if url.startswith("data:"):
        source = _from_data_uri(url)
    elif url.startswith(("http://", "https://")):
        raise UnsupportedElement(
            "remote images are not fetched for the preview; "
            "Home Assistant downloads them when drawing to the tag"
        )
    elif url.startswith(("image.", "camera.")):
        raise UnsupportedElement(
            f"entity image '{url}' needs Home Assistant to resolve"
        )
    else:
        source = _from_path(url)

    if source is None:
        _draw_placeholder(ctx, x, y, x_size, y_size, url)
        return

    if rotate:
        source = source.rotate(-rotate, expand=True)
    source = source.convert("RGBA")
    source = _resize(source, (x_size, y_size), resize_method)

    layer = Image.new("RGBA", ctx.image.size)
    layer.paste(source, (x, y), source)
    ctx.image.paste(Image.alpha_composite(ctx.image, layer), (0, 0))
    ctx.pos_y = y + y_size


def _resize(source: Image.Image, target: tuple[int, int], method: str) -> Image.Image:
    """Resize following the documented `resize_method` values."""
    if source.size == target:
        return source

    if method in {"crop", "cover", "contain"}:
        source = _resize_preserving_aspect(source, target, method)
    if source.size != target:
        source = source.resize(target, Image.LANCZOS)
    return source


def _resize_preserving_aspect(
    source: Image.Image, target: tuple[int, int], method: str
) -> Image.Image:
    """Scale to cover/contain the target box, then crop or pad."""
    target_w, target_h = target
    source_w, source_h = source.size
    if not source_w or not source_h:
        return source

    scale = (
        max(target_w / source_w, target_h / source_h)
        if method in {"crop", "cover"}
        else min(target_w / source_w, target_h / source_h)
    )
    resized = source.resize(
        (max(1, round(source_w * scale)), max(1, round(source_h * scale))),
        Image.LANCZOS,
    )

    if method in {"crop", "cover"}:
        left = (resized.width - target_w) // 2
        top = (resized.height - target_h) // 2
        return resized.crop((left, top, left + target_w, top + target_h))

    # contain: centre on a transparent canvas of the target size.
    canvas = Image.new("RGBA", target, (0, 0, 0, 0))
    canvas.paste(
        resized,
        ((target_w - resized.width) // 2, (target_h - resized.height) // 2),
        resized,
    )
    return canvas


def _from_data_uri(url: str) -> Image.Image | None:
    try:
        header, encoded = url.split(",", 1)
        data = base64.b64decode(encoded) if ";base64" in header else urllib.parse.unquote_to_bytes(encoded)
        return Image.open(io.BytesIO(data))
    except Exception:  # noqa: BLE001 - malformed data URI is a placeholder, not a crash
        return None


def _from_path(path: str) -> Image.Image | None:
    candidate = Path(path)
    if not candidate.is_file():
        return None
    try:
        return Image.open(candidate)
    except Exception:  # noqa: BLE001 - unreadable image is a placeholder
        return None


def _draw_placeholder(ctx, x: int, y: int, width: int, height: int, label: str) -> None:
    """Draw a boxed label where an image would go."""
    outline = ctx.colors.resolve("black")
    ctx.draw.rectangle(
        (x, y, x + width, y + height), outline=outline, width=1
    )
    from .fonts import load_font

    size = max(8, min(12, height // 4 or 8))
    font = load_font("ppb.ttf", size)
    text = label if len(label) <= 24 else f"{label[:21]}…"
    ctx.draw.text((x + 3, y + 3), text, fill=outline, font=font)
    ctx.pos_y = y + height
