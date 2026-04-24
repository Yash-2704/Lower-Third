from __future__ import annotations

import logging

log = logging.getLogger(__name__)

PANGO_SCALE = 1024
SCROLL_SPEED_PX_S = 150.0


def measure_text_width(
    text: str | None,
    font_family: str = "Noto Sans",
    font_size: int = 32,
    font_weight: str = "regular",
) -> float:
    if text is None:
        text = ""
    if not text:
        return 0.0
    if font_size <= 0:
        raise ValueError("font_size must be > 0")

    try:
        return _measure_cairo(text, font_family, font_size, font_weight)
    except (ImportError, OSError):
        return _measure_pillow(text, font_family, font_size)


def _measure_cairo(
    text: str,
    font_family: str,
    font_size: int,
    font_weight: str,
) -> float:
    import cairocffi as cairo
    import pangocffi as pango
    import pangocairocffi as pangocairo

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
    ctx = cairo.Context(surface)

    layout = pangocairo.create_layout(ctx)
    fd = pango.FontDescription()
    fd.family = font_family
    fd.size = font_size * PANGO_SCALE
    fd.weight = pango.Weight.BOLD if font_weight == "bold" else pango.Weight.NORMAL
    layout.font_description = fd
    layout.text = text

    ink, _logical = layout.get_extents()
    width = float(ink.width) / PANGO_SCALE + 4.0

    del layout
    del ctx
    surface.finish()

    return round(width, 2)


def _measure_pillow(text: str, font_family: str, font_size: int) -> float:
    from PIL import ImageFont

    font_file_candidates = [
        f"{font_family}.ttf",
        f"{font_family.replace(' ', '')}.ttf",
        "NotoSans-Regular.ttf",
    ]
    font = None
    for candidate in font_file_candidates:
        try:
            font = ImageFont.truetype(candidate, font_size)
            break
        except (OSError, IOError):
            continue

    if font is None:
        font = ImageFont.load_default()

    try:
        width = float(font.getlength(text))
    except AttributeError:
        bbox = font.getbbox(text)
        width = float(bbox[2] - bbox[0])

    return round(width + 4.0, 2)
