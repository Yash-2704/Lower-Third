from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

STYLE_COLOUR_MAP: dict[str, str] = {
    "minimal_dark_bar": "#1A1A2E",
    "bold_red_bar":     "#CC0000",
    "bold_blue_bar":    "#0A2463",
    "bold_green_bar":   "#1B4332",
}
DEFAULT_BAR_COLOUR  = "#1A1A2E"
DEFAULT_TEXT_COLOUR = "#FFFFFF"

_CONSTANTS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "module_constants.json"
)


@dataclass
class ResolvedBrand:
    canvas_w:           int
    canvas_h:           int
    bar_y:              int
    bar_h:              int
    bar_color:          str
    text_color:         str
    bar_padding_left:   int
    bar_padding_top:    int
    inter_line_spacing: int
    font_size_headline: int
    font_size_kicker:   int
    font_size_name:     int
    font_size_title:    int


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    if not (isinstance(hex_color, str) and len(hex_color) == 7 and hex_color.startswith("#")):
        raise ValueError(f"Invalid hex colour: {hex_color!r}")
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return r, g, b


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def clamp_to_broadcast_safe(hex_color: str) -> str:
    try:
        r, g, b = _hex_to_rgb(hex_color)
    except (ValueError, TypeError):
        return DEFAULT_BAR_COLOUR

    with open(_CONSTANTS_PATH) as fh:
        constants = json.load(fh)

    luma_min: int = constants["broadcast_luma_min"]
    luma_max: int = constants["broadcast_luma_max"]
    scale = luma_max - luma_min

    def _clamp(ch: int) -> int:
        return int(luma_min + (ch / 255) * scale)

    return _rgb_to_hex(_clamp(r), _clamp(g), _clamp(b))


def resolve_brand(
    upstream_signals: dict,
    estimated_lines: int = 2,
) -> ResolvedBrand:
    with open(_CONSTANTS_PATH) as fh:
        constants = json.load(fh)

    canvas_w: int = constants["canvas_width"]
    canvas_h: int = constants["canvas_height"]

    avoid = upstream_signals.get("anchor_avoid_zone", {"x": 0, "y": 0, "w": 0, "h": 0})
    anchor_avoid_zone_bottom = int(avoid.get("y", 0)) + int(avoid.get("h", 0))

    bar_h = (
        constants["bar_base_height_px"]
        + (estimated_lines - 1) * constants["bar_height_per_line"]
    )

    bar_y = max(
        canvas_h - bar_h - constants["bar_bottom_margin"],
        anchor_avoid_zone_bottom + 20,
    )

    style = upstream_signals.get("lower_third_style")
    raw_bar_color = STYLE_COLOUR_MAP.get(style, DEFAULT_BAR_COLOUR)

    bar_color  = clamp_to_broadcast_safe(raw_bar_color)
    text_color = clamp_to_broadcast_safe(DEFAULT_TEXT_COLOUR)

    return ResolvedBrand(
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        bar_y=bar_y,
        bar_h=bar_h,
        bar_color=bar_color,
        text_color=text_color,
        bar_padding_left=constants["bar_padding_left"],
        bar_padding_top=constants["bar_padding_top"],
        inter_line_spacing=constants["inter_line_spacing_px"],
        font_size_headline=constants["font_size_headline"],
        font_size_kicker=constants["font_size_kicker"],
        font_size_name=constants["font_size_name"],
        font_size_title=constants["font_size_title"],
    )
