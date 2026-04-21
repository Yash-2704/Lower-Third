import math
from pathlib import Path
import cairocffi as cairo
import pangocffi as pango
import pangocairocffi as pangocairo
from lower_third.motion.interpolation_engine import DrawState

_PANGO_SCALE = 1024

_CANVAS_W = 1920
_CANVAS_H = 1080
_FONT_FAMILY_DEFAULT = "Noto Sans"


def _hex_to_rgb_float(hex_color: str) -> tuple[float, float, float]:
    try:
        h = hex_color.lstrip("#")
        if len(h) != 6:
            return (0.0, 0.0, 0.0)
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        return (r, g, b)
    except Exception:
        return (0.0, 0.0, 0.0)


def _build_bounds_map(elements: list[dict]) -> dict[str, tuple[float, float, float, float]]:
    return {
        el["id"]: (el.get("x", 0.0), el.get("y", 0.0), el.get("w", 0.0), el.get("h", 0.0))
        for el in elements
        if "id" in el
    }


def draw_frame(state: DrawState, out_path: Path) -> None:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, _CANVAS_W, _CANVAS_H)
    ctx = cairo.Context(surface)

    ctx.set_operator(cairo.OPERATOR_CLEAR)
    ctx.paint()
    ctx.set_operator(cairo.OPERATOR_OVER)

    bounds_map = _build_bounds_map(state.elements)

    for el in state.elements:
        el_type = el.get("type")
        x = el.get("x", 0.0)
        y = el.get("y", 0.0)
        w = el.get("w", 0.0)
        h = el.get("h", 0.0)
        opacity = el.get("opacity", 1.0)
        scale_x = el.get("scale_x", 1.0)
        scale_y = el.get("scale_y", 1.0)
        rotation = el.get("rotation", 0.0)
        clip_to = el.get("clip_to")
        fill = el.get("fill", "#000000")
        font_size = el.get("font_size")
        font_weight = el.get("font_weight", "regular")
        content = el.get("content")
        repeat_content = el.get("repeat_content", False)
        text_x_offset = el.get("text_x_offset", 0.0)

        ctx.save()

        if clip_to and clip_to in bounds_map:
            bx, by, bw, bh = bounds_map[clip_to]
            ctx.rectangle(bx, by, bw, bh)
            ctx.clip()

        if scale_x != 1.0 or scale_y != 1.0 or rotation != 0.0:
            cx = x + w / 2.0
            cy = y + h / 2.0
            ctx.translate(cx, cy)
            ctx.rotate(math.radians(rotation))
            ctx.scale(scale_x, scale_y)
            ctx.translate(-cx, -cy)

        r, g, b = _hex_to_rgb_float(fill)

        if el_type == "rect":
            ctx.set_source_rgba(r, g, b, opacity)
            ctx.rectangle(x, y, w, h)
            ctx.fill()

        elif el_type == "text" and content is not None:
            layout = pangocairo.create_layout(ctx)
            fd = pango.FontDescription()
            fd.family = el.get("font_family", _FONT_FAMILY_DEFAULT)
            fd.size = (font_size or 32) * _PANGO_SCALE
            fd.weight = pango.Weight.BOLD if font_weight == "bold" else pango.Weight.NORMAL
            layout.font_description = fd

            if repeat_content:
                layout.text = content
                text_w = layout.get_size()[0] / _PANGO_SCALE
                if text_w > 0:
                    repeat_count = math.ceil((_CANVAS_W + text_w) / text_w) + 1
                else:
                    repeat_count = 2
                layout.text = content * repeat_count
            else:
                layout.text = content

            ctx.set_source_rgba(r, g, b, opacity)
            ctx.move_to(x + text_x_offset, y)
            pangocairo.show_layout(ctx, layout)

        ctx.restore()

    surface.write_to_png(str(out_path))


def render_frames(state_iter, output_dir: Path, fps: int = 30) -> Path:
    frames_dir = output_dir / "frames"
    if frames_dir.exists():
        for old in frames_dir.glob("frame_*.png"):
            old.unlink()
    frames_dir.mkdir(parents=True, exist_ok=True)
    for i, state in state_iter:
        draw_frame(state, frames_dir / f"frame_{i:06d}.png")
    return frames_dir
