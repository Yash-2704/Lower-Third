from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from lower_third.motion.interpolation_engine import DrawState

_CANVAS_W = 1920
_CANVAS_H = 1080


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    try:
        h = hex_color.lstrip("#")
        if len(h) != 6:
            return (0, 0, 0)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return (0, 0, 0)


def _build_bounds_map(elements: list[dict]) -> dict[str, tuple[float, float, float, float]]:
    return {
        el["id"]: (el.get("x", 0.0), el.get("y", 0.0), el.get("w", 0.0), el.get("h", 0.0))
        for el in elements
        if "id" in el
    }


def draw_frame(state: DrawState, out_path: Path) -> None:
    canvas = Image.new("RGBA", (_CANVAS_W, _CANVAS_H), (0, 0, 0, 0))
    bounds_map = _build_bounds_map(state.elements)

    for el in state.elements:
        el_type = el.get("type")
        x = int(el.get("x", 0.0))
        y = int(el.get("y", 0.0))
        w = int(el.get("w", 0.0))
        h = int(el.get("h", 0.0))
        opacity = el.get("opacity", 1.0)
        fill = el.get("fill", "#000000")
        font_size = el.get("font_size") or 32
        font_weight = el.get("font_weight", "regular")
        content = el.get("content")
        repeat_content = el.get("repeat_content", False)
        text_x_offset = int(el.get("text_x_offset", 0.0))
        clip_to = el.get("clip_to")

        alpha = int(opacity * 255)
        r, g, b = _hex_to_rgb(fill)
        fill_rgba = (r, g, b, alpha)

        layer = Image.new("RGBA", (_CANVAS_W, _CANVAS_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)

        if el_type == "rect" and w > 0 and h > 0:
            draw.rectangle([x, y, x + w, y + h], fill=fill_rgba)

        elif el_type == "text" and content is not None:
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
                    if font_weight == "bold"
                    else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
                    size=font_size,
                )
            except (IOError, OSError):
                font = ImageFont.load_default()

            text_to_draw = content
            if repeat_content:
                try:
                    bbox = draw.textbbox((0, 0), content, font=font)
                    text_w = bbox[2] - bbox[0]
                except AttributeError:
                    text_w = font_size * len(content) // 2
                if text_w > 0:
                    import math
                    repeat_count = math.ceil((_CANVAS_W + text_w) / text_w) + 1
                    text_to_draw = content * repeat_count
            draw.text((x + text_x_offset, y), text_to_draw, font=font, fill=fill_rgba)

        if clip_to and clip_to in bounds_map:
            bx, by, bw, bh = bounds_map[clip_to]
            clip_mask = Image.new("L", (_CANVAS_W, _CANVAS_H), 0)
            clip_draw = ImageDraw.Draw(clip_mask)
            clip_draw.rectangle(
                [int(bx), int(by), int(bx + bw), int(by + bh)], fill=255
            )
            canvas.paste(layer, mask=clip_mask)
        else:
            canvas.paste(layer, mask=layer.split()[3])

    canvas.save(str(out_path), "PNG")


def render_frames(state_iter, output_dir: Path, fps: int = 30) -> Path:
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for i, state in state_iter:
        draw_frame(state, frames_dir / f"frame_{i:06d}.png")
    return frames_dir
