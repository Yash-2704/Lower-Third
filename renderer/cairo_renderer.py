import math
from pathlib import Path
from typing import Sequence
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


def _svg_arc(
    ctx: cairo.Context,
    rx: float, ry: float,
    x_rotation: float,
    large_arc: int, sweep: int,
    x1: float, y1: float,
    x2: float, y2: float,
) -> None:
    """Convert an SVG elliptical arc (endpoint form) to Cairo arc calls."""
    if rx == 0.0 or ry == 0.0:
        ctx.line_to(x2, y2)
        return

    phi = math.radians(x_rotation)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    dx = (x1 - x2) / 2.0
    dy = (y1 - y2) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy

    rx = abs(rx)
    ry = abs(ry)
    x1p2 = x1p * x1p
    y1p2 = y1p * y1p
    rx2 = rx * rx
    ry2 = ry * ry

    lam = x1p2 / rx2 + y1p2 / ry2
    if lam > 1.0:
        lam_sqrt = math.sqrt(lam)
        rx = lam_sqrt * rx
        ry = lam_sqrt * ry
        rx2 = rx * rx
        ry2 = ry * ry

    num = rx2 * ry2 - rx2 * y1p2 - ry2 * x1p2
    den = rx2 * y1p2 + ry2 * x1p2
    sq = math.sqrt(max(0.0, num / den)) if den != 0.0 else 0.0
    if large_arc == sweep:
        sq = -sq

    cxp = sq * rx * y1p / ry
    cyp = -sq * ry * x1p / rx

    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2.0

    ux = (x1p - cxp) / rx
    uy = (y1p - cyp) / ry
    vx = (-x1p - cxp) / rx
    vy = (-y1p - cyp) / ry

    start_angle = math.atan2(uy, ux)

    uv_len = math.sqrt((ux * ux + uy * uy) * (vx * vx + vy * vy))
    cos_da = max(-1.0, min(1.0, (ux * vx + uy * vy) / uv_len)) if uv_len != 0.0 else 1.0
    sweep_angle = math.acos(cos_da)
    if ux * vy - uy * vx < 0.0:
        sweep_angle = -sweep_angle

    if sweep == 0 and sweep_angle > 0.0:
        sweep_angle -= 2.0 * math.pi
    elif sweep == 1 and sweep_angle < 0.0:
        sweep_angle += 2.0 * math.pi

    end_angle = start_angle + sweep_angle

    ctx.save()
    ctx.translate(cx, cy)
    ctx.rotate(phi)
    ctx.scale(rx, ry)
    if sweep == 1:
        ctx.arc(0.0, 0.0, 1.0, start_angle, end_angle)
    else:
        ctx.arc_negative(0.0, 0.0, 1.0, start_angle, end_angle)
    ctx.restore()


def _draw_svg_path(ctx: cairo.Context, d: str) -> None:
    """Parse and draw an SVG path string. Supports M L H V A Z only."""
    tokens = d.split()
    i = 0
    cur_x = 0.0
    cur_y = 0.0

    while i < len(tokens):
        cmd = tokens[i]
        i += 1

        if cmd == "M":
            xy = tokens[i].split(",")
            cur_x, cur_y = float(xy[0]), float(xy[1])
            ctx.move_to(cur_x, cur_y)
            i += 1

        elif cmd == "L":
            xy = tokens[i].split(",")
            cur_x, cur_y = float(xy[0]), float(xy[1])
            ctx.line_to(cur_x, cur_y)
            i += 1

        elif cmd == "H":
            cur_x = float(tokens[i])
            ctx.line_to(cur_x, cur_y)
            i += 1

        elif cmd == "V":
            cur_y = float(tokens[i])
            ctx.line_to(cur_x, cur_y)
            i += 1

        elif cmd == "A":
            rxy = tokens[i].split(",")
            rx, ry = float(rxy[0]), float(rxy[1])
            x_rot = float(tokens[i + 1])
            flags = tokens[i + 2].split(",")
            large_arc, sweep = int(flags[0]), int(flags[1])
            end_xy = tokens[i + 3].split(",")
            x2, y2 = float(end_xy[0]), float(end_xy[1])
            _svg_arc(ctx, rx, ry, x_rot, large_arc, sweep, cur_x, cur_y, x2, y2)
            cur_x, cur_y = x2, y2
            i += 4

        elif cmd == "Z":
            ctx.close_path()

        else:
            raise ValueError(f"Unrecognised SVG path command: {cmd!r}")


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
        gradient_def = el.get("gradient")

        def _set_source(bx: float, by: float, bw: float, bh: float) -> None:
            if gradient_def:
                angle = math.radians(gradient_def.get("angle_deg", 0.0))
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                cx_ = bx + bw / 2.0
                cy_ = by + bh / 2.0
                half_len = (abs(cos_a) * bw + abs(sin_a) * bh) / 2.0
                x0_ = cx_ - cos_a * half_len
                y0_ = cy_ - sin_a * half_len
                x1_ = cx_ + cos_a * half_len
                y1_ = cy_ + sin_a * half_len
                pat = cairo.LinearGradient(x0_, y0_, x1_, y1_)
                sr, sg, sb = _hex_to_rgb_float(gradient_def["start_color"])
                er, eg, eb = _hex_to_rgb_float(gradient_def["end_color"])
                pat.add_color_stop_rgba(0, sr, sg, sb, opacity)
                pat.add_color_stop_rgba(1, er, eg, eb, opacity)
                ctx.set_source(pat)
            else:
                ctx.set_source_rgba(r, g, b, opacity)

        if el_type == "rect":
            _set_source(x, y, w or 1.0, h or 1.0)
            ctx.rectangle(x, y, w, h)
            ctx.fill()

        elif el_type == "path" and el.get("d"):
            _draw_svg_path(ctx, el["d"])
            bx_ = el.get("x", x)
            by_ = el.get("y", y)
            bw_ = el.get("w") or 1.0
            bh_ = el.get("h") or 1.0
            _set_source(bx_, by_, bw_, bh_)
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
