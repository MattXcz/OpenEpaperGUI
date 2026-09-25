"""Element schema for the OpenEPaperLink `drawcustom` payload.

The schema is the single source of truth for:
  * the property inspector in the frontend (served via /api/schema)
  * the canvas geometry (how a bounding box is derived from the props)
  * the Jinja/YAML generator (which props are emitted, and in what order)

Field kinds
-----------
number      numeric input
text        single line text
textarea    multi line text (supports \n)
color       color picker with the ESL palette
select      dropdown, `options` holds the allowed values
bool        checkbox
points      list of [x, y] pairs
iconlist    list of mdi icon names
plotdata    list of {entity, color, width, ...} objects
object      nested option object (plot axes / legends), `None` = off
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Shared field fragments
# ---------------------------------------------------------------------------

COLORS = [
    "black",
    "white",
    "accent",
    "red",
    "yellow",
    "half_black",
    "half_white",
    "half_red",
    "half_yellow",
    "half_accent",
]

ANCHORS = [
    "lt", "lm", "lb", "mt", "mm", "mb", "rt", "rm", "rb",
    "la", "ma", "ra",
]

FONTS = ["ppb.ttf", "rbm.ttf"]

VISIBLE = {
    "key": "visible",
    "label": "Visible",
    "kind": "bool",
    "default": True,
    "group": "Advanced",
}

POSITION_GROUP = "Position"
STYLE_GROUP = "Style"
AXES_GROUP = "Axes & legends"

# `corners` accepts "all" or a comma separated list of corners.
CORNERS = [
    "all",
    "top_left,top_right",
    "bottom_left,bottom_right",
    "top_left,bottom_left",
    "top_right,bottom_right",
    "top_left",
    "top_right",
    "bottom_left",
    "bottom_right",
]


def _num(key: str, label: str, default: Any = None, *, group: str = POSITION_GROUP,
         min: float | None = None, max: float | None = None, step: float = 1,
         help: str | None = None) -> dict:
    return {
        "key": key, "label": label, "kind": "number", "default": default,
        "group": group, "min": min, "max": max, "step": step, "help": help,
    }


def _text(key: str, label: str, default: Any = "", *, group: str = "Content",
          help: str | None = None, template: bool = True) -> dict:
    return {
        "key": key, "label": label, "kind": "text", "default": default,
        "group": group, "help": help, "template": template,
    }


def _area(key: str, label: str, default: Any = "", *, group: str = "Content",
          help: str | None = None) -> dict:
    return {
        "key": key, "label": label, "kind": "textarea", "default": default,
        "group": group, "help": help, "template": True,
    }


def _color(key: str, label: str, default: Any = "black", *, group: str = STYLE_GROUP,
           allow_none: bool = False) -> dict:
    return {
        "key": key, "label": label, "kind": "color", "default": default,
        "group": group, "options": COLORS, "allow_none": allow_none,
    }


def _select(key: str, label: str, options: list, default: Any, *,
            group: str = STYLE_GROUP) -> dict:
    return {
        "key": key, "label": label, "kind": "select", "default": default,
        "group": group, "options": options,
    }


def _bool(key: str, label: str, default: bool = False, *,
          group: str = "Advanced") -> dict:
    return {"key": key, "label": label, "kind": "bool", "default": default, "group": group}


def _object(key: str, label: str, emit_key: str, fields: list[dict], *,
            group: str = AXES_GROUP) -> dict:
    """A nested option object such as a plot axis.

    The value is `None` (switched off, omitted) or a dict of sub-properties.
    Home Assistant treats an empty dict as off too, so `emit_key` is emitted
    when every sub-property is at its default.
    """
    return {
        "key": key, "label": label, "kind": "object", "default": None,
        "group": group, "fields": fields, "emit_key": emit_key,
    }


# ---------------------------------------------------------------------------
# Element types
# ---------------------------------------------------------------------------

ELEMENT_TYPES: list[dict] = [
    {
        "type": "text",
        "label": "Text",
        "icon": "mdi:format-text",
        "category": "Content",
        "geometry": {"kind": "point", "x": "x", "y": "y", "size": "size",
                     "text": "value", "char_width": 0.58, "line_height": 1.25},
        "fields": [
            _area("value", "Text", "Hello World!"),
            _num("x", "X", 0),
            _num("y", "Y", 0),
            _num("size", "Font size", 20, group=STYLE_GROUP, min=1),
            _select("font", "Font", FONTS, "ppb.ttf"),
            _color("color", "Color", "black"),
            _select("anchor", "Anchor", ANCHORS, "lt"),
            _num("max_width", "Max width", None, group="Advanced", min=0),
            _num("spacing", "Line spacing", 5, group="Advanced"),
            _num("stroke_width", "Stroke width", 0, group="Advanced", min=0),
            _color("stroke_fill", "Stroke color", "white", group="Advanced"),
            _num("y_padding", "Y padding", 10, group="Advanced"),
            _select("align", "Align lines", ["left", "center", "right"], "left",
                    group="Advanced"),
            _bool("parse_colors", "Parse [color] markup"),
            _bool("truncate", "Truncate with ellipsis"),
            VISIBLE,
        ],
    },
    {
        "type": "multiline",
        "label": "Multiline text",
        "icon": "mdi:format-align-left",
        "category": "Content",
        "geometry": {"kind": "point", "x": "x", "y": "y", "size": "size",
                     "text": "value", "char_width": 0.58, "line_height": 1.25,
                     "split": "delimiter", "line_step": "offset_y"},
        "fields": [
            _area("value", "Text (delimiter separated)", "Line 1|Line 2|Line 3"),
            _text("delimiter", "Delimiter", "|", group="Content"),
            _num("x", "X", 0),
            _num("y", "Y", 0),
            _num("offset_y", "Line offset", 20, group=POSITION_GROUP, min=1),
            _num("size", "Font size", 20, group=STYLE_GROUP, min=1),
            _select("font", "Font", FONTS, "ppb.ttf"),
            _color("color", "Color", "black"),
            # HA anchors every line at "lm" (left-middle) unless told otherwise.
            _select("anchor", "Anchor", ANCHORS, "lm"),
            _num("spacing", "Extra spacing", 0, group="Advanced"),
            _bool("parse_colors", "Parse [color] markup"),
            VISIBLE,
        ],
    },
    {
        "type": "icon",
        "label": "Icon",
        "icon": "mdi:emoticon-happy-outline",
        "category": "Content",
        "geometry": {"kind": "point", "x": "x", "y": "y", "size": "size",
                     "square": True},
        "fields": [
            _text("value", "Icon name", "mdi:emoticon-happy"),
            _num("x", "X", 0),
            _num("y", "Y", 0),
            _num("size", "Size", 50, group=STYLE_GROUP, min=1),
            _color("fill", "Color", "black"),
            _select("anchor", "Anchor", ANCHORS, "la"),
            VISIBLE,
        ],
    },
    {
        "type": "icon_sequence",
        "label": "Icon sequence",
        "icon": "mdi:dots-horizontal",
        "category": "Content",
        "geometry": {"kind": "point", "x": "x", "y": "y", "size": "size",
                     "sequence": "icons", "spacing": "spacing"},
        "fields": [
            {"key": "icons", "label": "Icons", "kind": "iconlist",
             "default": ["mdi:home", "mdi:arrow-right", "mdi:office-building"],
             "group": "Content"},
            _num("x", "X", 0),
            _num("y", "Y", 0),
            _num("size", "Icon size", 24, group=STYLE_GROUP, min=1),
            _select("direction", "Direction", ["right", "left", "up", "down"], "right"),
            _num("spacing", "Spacing", None, group=STYLE_GROUP, min=0),
            _color("fill", "Color", "black"),
            _select("anchor", "Anchor", ANCHORS, "la"),
            VISIBLE,
        ],
    },
    {
        "type": "qrcode",
        "label": "QR code",
        "icon": "mdi:qrcode",
        "category": "Content",
        "geometry": {"kind": "point", "x": "x", "y": "y", "size": "boxsize",
                     "qr": True},
        "fields": [
            _text("data", "Data", "https://openepaperlink.de"),
            _num("x", "X", 0),
            _num("y", "Y", 0),
            _num("boxsize", "Box size", 2, group=STYLE_GROUP, min=1),
            _num("border", "Border", 1, group=STYLE_GROUP, min=0),
            _color("color", "Foreground", "black"),
            _color("bgcolor", "Background", "white"),
            VISIBLE,
        ],
    },
    {
        "type": "dlimg",
        "label": "Image",
        "icon": "mdi:image-outline",
        "category": "Content",
        "geometry": {"kind": "point", "x": "x", "y": "y",
                     "w": "xsize", "h": "ysize"},
        "fields": [
            _text("url", "URL / path", "https://example.com/image.png"),
            _num("x", "X", 0),
            _num("y", "Y", 0),
            _num("xsize", "Width", 120, group=STYLE_GROUP, min=1),
            _num("ysize", "Height", 120, group=STYLE_GROUP, min=1),
            _select("resize_method", "Resize method",
                    ["stretch", "crop", "cover", "contain"], "stretch"),
            _num("rotate", "Rotate", 0, group="Advanced"),
            VISIBLE,
        ],
    },
    {
        "type": "line",
        "label": "Line",
        "icon": "mdi:minus",
        "category": "Shapes",
        "geometry": {"kind": "box", "x_start": "x_start", "y_start": "y_start",
                     "x_end": "x_end", "y_end": "y_end", "line": True},
        "fields": [
            _num("x_start", "X start", 0),
            _num("x_end", "X end", 200),
            _num("y_start", "Y start", 0),
            _num("y_end", "Y end", 0),
            _color("fill", "Color", "black"),
            _num("width", "Thickness", 1, group=STYLE_GROUP, min=1),
            _bool("dashed", "Dashed"),
            _num("dash_length", "Dash length", 5, group="Advanced", min=1),
            _num("space_length", "Space length", 3, group="Advanced", min=1),
            _num("y_padding", "Y padding", 0, group="Advanced"),
            VISIBLE,
        ],
    },
    {
        "type": "rectangle",
        "label": "Rectangle",
        "icon": "mdi:rectangle-outline",
        "category": "Shapes",
        "geometry": {"kind": "box", "x_start": "x_start", "y_start": "y_start",
                     "x_end": "x_end", "y_end": "y_end"},
        "fields": [
            _num("x_start", "X start", 0),
            _num("x_end", "X end", 100),
            _num("y_start", "Y start", 0),
            _num("y_end", "Y end", 50),
            _color("fill", "Fill", None, allow_none=True),
            _color("outline", "Outline", "black"),
            _num("width", "Border width", 1, group=STYLE_GROUP, min=0),
            _num("radius", "Corner radius", 0, group=STYLE_GROUP, min=0),
            _select("corners", "Rounded corners", CORNERS, "all"),
            VISIBLE,
        ],
    },
    {
        "type": "rectangle_pattern",
        "label": "Rectangle pattern",
        "icon": "mdi:grid",
        "category": "Shapes",
        "geometry": {"kind": "pattern", "x_start": "x_start", "y_start": "y_start",
                     "x_size": "x_size", "y_size": "y_size",
                     "x_offset": "x_offset", "y_offset": "y_offset",
                     "x_repeat": "x_repeat", "y_repeat": "y_repeat"},
        "fields": [
            _num("x_start", "X start", 5),
            _num("x_size", "Cell width", 35, group=STYLE_GROUP, min=1),
            _num("x_offset", "X spacing", 10, group=STYLE_GROUP),
            _num("y_start", "Y start", 28),
            _num("y_size", "Cell height", 18, group=STYLE_GROUP, min=1),
            _num("y_offset", "Y spacing", 2, group=STYLE_GROUP),
            _num("x_repeat", "Repeat X", 1, group=STYLE_GROUP, min=1),
            _num("y_repeat", "Repeat Y", 4, group=STYLE_GROUP, min=1),
            _color("fill", "Fill", None, allow_none=True),
            _color("outline", "Outline", "black"),
            _num("width", "Border width", 1, group=STYLE_GROUP, min=0),
            _num("radius", "Corner radius", 0, group=STYLE_GROUP, min=0),
            _select("corners", "Rounded corners", CORNERS, "all"),
            VISIBLE,
        ],
    },
    {
        "type": "polygon",
        "label": "Polygon",
        "icon": "mdi:vector-polygon",
        "category": "Shapes",
        "geometry": {"kind": "points", "points": "points"},
        "fields": [
            {"key": "points", "label": "Points", "kind": "points",
             "default": [[10, 10], [50, 10], [50, 50], [10, 50]], "group": "Position"},
            _color("fill", "Fill", None, allow_none=True),
            _color("outline", "Outline", "black"),
            _num("width", "Border width", 1, group=STYLE_GROUP, min=0),
            VISIBLE,
        ],
    },
    {
        "type": "circle",
        "label": "Circle",
        "icon": "mdi:circle-outline",
        "category": "Shapes",
        "geometry": {"kind": "point", "x": "x", "y": "y", "radius": "radius",
                     "centered": True},
        "fields": [
            _num("x", "Center X", 50),
            _num("y", "Center Y", 50),
            _num("radius", "Radius", 20, group=STYLE_GROUP, min=1),
            _color("fill", "Fill", None, allow_none=True),
            _color("outline", "Outline", "black"),
            _num("width", "Border width", 1, group=STYLE_GROUP, min=0),
            VISIBLE,
        ],
    },
    {
        "type": "ellipse",
        "label": "Ellipse",
        "icon": "mdi:ellipse-outline",
        "category": "Shapes",
        "geometry": {"kind": "box", "x_start": "x_start", "y_start": "y_start",
                     "x_end": "x_end", "y_end": "y_end"},
        "fields": [
            _num("x_start", "X start", 50),
            _num("x_end", "X end", 100),
            _num("y_start", "Y start", 50),
            _num("y_end", "Y end", 100),
            _color("fill", "Fill", None, allow_none=True),
            _color("outline", "Outline", "black"),
            _num("width", "Border width", 1, group=STYLE_GROUP, min=0),
            VISIBLE,
        ],
    },
    {
        "type": "arc",
        "label": "Arc / pie slice",
        "icon": "mdi:chart-donut",
        "category": "Shapes",
        "geometry": {"kind": "point", "x": "x", "y": "y", "radius": "radius",
                     "centered": True},
        "fields": [
            _num("x", "Center X", 100),
            _num("y", "Center Y", 75),
            _num("radius", "Radius", 50, group=STYLE_GROUP, min=1),
            _num("start_angle", "Start angle", 0, group=STYLE_GROUP),
            _num("end_angle", "End angle", 90, group=STYLE_GROUP),
            _color("fill", "Fill (pie slice)", None, allow_none=True),
            _color("outline", "Outline", "black"),
            _num("width", "Border width", 1, group=STYLE_GROUP, min=0),
            VISIBLE,
        ],
    },
    {
        "type": "progress_bar",
        "label": "Progress bar",
        "icon": "mdi:progress-bar",
        "category": "Data",
        "geometry": {"kind": "box", "x_start": "x_start", "y_start": "y_start",
                     "x_end": "x_end", "y_end": "y_end"},
        "fields": [
            _num("x_start", "X start", 10),
            _num("y_start", "Y start", 10),
            _num("x_end", "X end", 280),
            _num("y_end", "Y end", 30),
            _num("progress", "Progress (0-100)", 42, group="Content", min=0, max=100),
            _select("direction", "Direction", ["right", "left", "up", "down"], "right"),
            _color("background", "Background", "white"),
            _color("fill", "Fill", "red"),
            _color("outline", "Outline", "black"),
            _num("width", "Border width", 1, group=STYLE_GROUP, min=0),
            _bool("show_percentage", "Show percentage", False, group="Content"),
            _select("font", "Font", FONTS, "ppb.ttf"),
            VISIBLE,
        ],
    },
    {
        "type": "plot",
        "label": "Plot",
        "icon": "mdi:chart-line",
        "category": "Data",
        "geometry": {"kind": "box", "x_start": "x_start", "y_start": "y_start",
                     "x_end": "x_end", "y_end": "y_end"},
        "fields": [
            {"key": "data", "label": "Entities", "kind": "plotdata",
             "default": [{"entity": "sensor.temperature", "color": "red", "width": 2}],
             "group": "Content"},
            _num("x_start", "X start", 10),
            _num("y_start", "Y start", 20),
            _num("x_end", "X end", 199),
            _num("y_end", "Y end", 119),
            _num("duration", "Duration (s)", 86400, group="Content", min=60),
            _num("low", "Min value", None, group="Content"),
            _num("high", "Max value", None, group="Content"),
            _select("font", "Font", FONTS, "ppb.ttf"),
            _num("size", "Font size", 10, group=STYLE_GROUP, min=1),
            _bool("round_values", "Round values"),
            _bool("debug", "Debug borders"),
            _object("ylegend", "Y legend", "position", [
                _num("width", "Width (-1 = auto)", -1, group=AXES_GROUP),
                _color("color", "Color", "black", group=AXES_GROUP),
                _select("position", "Position", ["left", "right"], "left", group=AXES_GROUP),
                _num("size", "Font size", 10, group=AXES_GROUP, min=1),
            ]),
            _object("yaxis", "Y axis", "width", [
                _num("width", "Line width", 1, group=AXES_GROUP, min=0),
                _color("color", "Color", "black", group=AXES_GROUP),
                _num("tick_length", "Tick length", 4, group=AXES_GROUP, min=0),
                _num("tick_width", "Tick width", 2, group=AXES_GROUP, min=0),
                _num("tick_every", "Tick every", 1, group=AXES_GROUP, step=0.1),
                _bool("grid", "Grid", True, group=AXES_GROUP),
                _color("grid_color", "Grid color", "black", group=AXES_GROUP),
                _select("grid_style", "Grid style", ["dotted", "dashed", "lines"], "dotted",
                        group=AXES_GROUP),
            ]),
            _object("xlegend", "X legend (time labels)", "position", [
                _text("format", "Time format", "%H:%M", group=AXES_GROUP, template=False,
                      help="Python strftime format, e.g. %H:%M"),
                _num("interval", "Interval (s)", None, group=AXES_GROUP, min=1,
                     help="Empty = a quarter of the duration"),
                _bool("snap_to_hours", "Snap to hours", True, group=AXES_GROUP),
                _num("size", "Font size", 10, group=AXES_GROUP, min=1),
                _select("position", "Position", ["bottom", "top"], "bottom", group=AXES_GROUP),
                _color("color", "Color", "black", group=AXES_GROUP),
                _num("height", "Height (-1 = auto, 0 = hidden)", -1, group=AXES_GROUP),
            ]),
            _object("xaxis", "X axis", "width", [
                _num("width", "Line width", 1, group=AXES_GROUP, min=0),
                _color("color", "Color", "black", group=AXES_GROUP),
                _num("tick_length", "Tick length", 4, group=AXES_GROUP, min=0),
                _num("tick_width", "Tick width", 2, group=AXES_GROUP, min=0),
                _bool("grid", "Grid", True, group=AXES_GROUP),
                _color("grid_color", "Grid color", "black", group=AXES_GROUP),
                _select("grid_style", "Grid style", ["dotted", "dashed", "lines"], "dotted",
                        group=AXES_GROUP),
            ]),
            VISIBLE,
        ],
    },
    {
        "type": "debug_grid",
        "label": "Debug grid",
        "icon": "mdi:grid-large",
        "category": "Utility",
        "geometry": {"kind": "full"},
        "fields": [
            _num("spacing", "Spacing", 20, group=STYLE_GROUP, min=1),
            _color("line_color", "Line color", "black"),
            _bool("dashed", "Dashed", True),
            _num("dash_length", "Dash length", 2, group="Advanced", min=1),
            _num("space_length", "Space length", 4, group="Advanced", min=1),
            _bool("show_labels", "Show labels", True),
            _num("label_step", "Label step", 40, group="Advanced", min=1),
            _color("label_color", "Label color", "black"),
            _num("label_font_size", "Label font size", 12, group="Advanced", min=1),
            _select("font", "Font", FONTS, "ppb.ttf"),
            VISIBLE,
        ],
    },
]

ELEMENT_TYPES_BY_NAME = {t["type"]: t for t in ELEMENT_TYPES}

# Fields that are always emitted, even when they match the schema default.
REQUIRED_FIELDS: dict[str, set[str]] = {
    "text": {"value", "x", "y"},
    "multiline": {"value", "delimiter", "x", "offset_y"},
    "icon": {"value", "x", "y", "size"},
    "icon_sequence": {"icons", "x", "y", "size"},
    "qrcode": {"data", "x", "y"},
    "dlimg": {"url", "x", "y", "xsize", "ysize"},
    "line": {"x_start", "x_end"},
    "rectangle": {"x_start", "x_end", "y_start", "y_end"},
    "rectangle_pattern": {
        "x_start", "x_size", "x_offset", "y_start", "y_size", "y_offset",
        "x_repeat", "y_repeat",
    },
    "polygon": {"points"},
    "circle": {"x", "y", "radius"},
    "ellipse": {"x_start", "x_end", "y_start", "y_end"},
    "arc": {"x", "y", "radius", "start_angle", "end_angle"},
    "progress_bar": {"x_start", "y_start", "x_end", "y_end", "progress"},
    "plot": {"data"},
    "debug_grid": set(),
}

# Optional fields whose Home Assistant default is *dynamic* (auto-positioned,
# canvas size, derived from another field …). No schema default can match it,
# so "omit when equal to the default" would silently move the element on the
# display. These are always emitted, exactly like required fields.
ALWAYS_EMIT_FIELDS: dict[str, set[str]] = {
    "multiline": {"y"},                               # HA: last position + y_padding
    "line": {"y_start", "y_end"},                     # HA: auto / = y_start
    "plot": {"x_start", "y_start", "x_end", "y_end"},  # HA: 0 / canvas size
    "debug_grid": {"label_step"},                     # HA: 2 * spacing
}


def emitted_always(element_type: str) -> set[str]:
    """Fields the generator emits regardless of the schema default."""
    return REQUIRED_FIELDS.get(element_type, set()) | ALWAYS_EMIT_FIELDS.get(element_type, set())


# Fields that are purely editor-side and never emitted into the payload.
INTERNAL_FIELDS = {"visible"}

DISPLAY_PRESETS = [
    {"label": "2.9\" BWR (296x128)", "width": 296, "height": 128},
    {"label": "2.9\" BWR (128x296)", "width": 128, "height": 296},
    {"label": "2.13\" BWR (250x122)", "width": 250, "height": 122},
    {"label": "2.13\" BWR (122x250)", "width": 122, "height": 250},
    {"label": "1.54\" BWR (200x200)", "width": 200, "height": 200},
    {"label": "M3 2.6\" BWR (360x184)", "width": 360, "height": 184},
    {"label": "M3 2.6\" BWR(184x360)", "width": 184, "height": 360},
    {"label": "4.2\" BWR (400x300)", "width": 400, "height": 300},
    {"label": "7.5\" BWR (800x480)", "width": 800, "height": 480},
    {"label": "Custom", "width": 296, "height": 128},
]


def default_props(element_type: str) -> dict:
    """Return the default property bag for an element type."""
    spec = ELEMENT_TYPES_BY_NAME.get(element_type)
    if not spec:
        raise KeyError(element_type)
    props: dict[str, Any] = {}
    for field in spec["fields"]:
        props[field["key"]] = field.get("default")
    return props


def public_schema() -> dict:
    """Schema payload consumed by the frontend."""
    return {
        "types": ELEMENT_TYPES,
        "colors": COLORS,
        "anchors": ANCHORS,
        "fonts": FONTS,
        "displayPresets": DISPLAY_PRESETS,
    }
