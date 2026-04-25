import pytest
from pathlib import Path
import tempfile
from lower_third.motion.motion_ir import (
    MotionIR, ElementDef, AnimationTrack, Keyframe, EasingConfig, LoopConfig
)
from lower_third.motion.interpolation_engine import InterpolationEngine, DrawState


def _make_state(elements_override=None) -> DrawState:
    elements = elements_override or [
        {
            "id": "bar", "type": "rect",
            "x": 0.0, "y": 960.0, "w": 1920.0, "h": 60.0,
            "opacity": 1.0, "fill": "#1A1A2E",
            "scale_x": 1.0, "scale_y": 1.0, "rotation": 0.0,
            "clip_to": None, "clip_x": 0.0, "clip_y": 960.0,
            "clip_w": 1920.0, "clip_h": 60.0,
            "content": None, "repeat_content": False,
            "font_size": None, "font_weight": "regular",
            "text_x_offset": 0.0,
        },
        {
            "id": "t1", "type": "text",
            "content": "Iran blocks Strait of Hormuz",
            "x": 24.0, "y": 972.0, "w": 0.0, "h": 0.0,
            "opacity": 1.0, "fill": "#FFFFFF",
            "scale_x": 1.0, "scale_y": 1.0, "rotation": 0.0,
            "clip_to": "bar",
            "clip_x": 0.0, "clip_y": 960.0, "clip_w": 1920.0, "clip_h": 60.0,
            "content": "Iran blocks Strait of Hormuz",
            "repeat_content": False,
            "font_size": 32, "font_weight": "bold",
            "text_x_offset": 0.0,
        }
    ]
    return DrawState(elements=elements)


def test_draw_frame_creates_png():
    try:
        from lower_third.renderer.cairo_renderer import draw_frame
    except (ImportError, OSError):
        pytest.skip("Cairo not installed")
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "frame_000000.png"
        draw_frame(_make_state(), out)
        assert out.exists()
        assert out.stat().st_size > 0


def test_draw_frame_output_is_1920x1080():
    try:
        from lower_third.renderer.cairo_renderer import draw_frame
        import cairo
    except (ImportError, OSError):
        pytest.skip("Cairo not installed")
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "frame_000000.png"
        draw_frame(_make_state(), out)
        surface = cairo.ImageSurface.create_from_png(str(out))
        assert surface.get_width()  == 1920
        assert surface.get_height() == 1080


def test_draw_frame_is_rgba():
    try:
        from lower_third.renderer.cairo_renderer import draw_frame
        import cairo
    except (ImportError, OSError):
        pytest.skip("Cairo not installed")
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "frame_000000.png"
        draw_frame(_make_state(), out)
        surface = cairo.ImageSurface.create_from_png(str(out))
        assert surface.get_format() == cairo.FORMAT_ARGB32


def test_transparent_frame_has_alpha():
    try:
        from lower_third.renderer.cairo_renderer import draw_frame
        import cairo
    except (ImportError, OSError):
        pytest.skip("Cairo not installed")
    transparent_elements = [{
        "id": "bar", "type": "rect",
        "x": 0.0, "y": 960.0, "w": 1920.0, "h": 60.0,
        "opacity": 0.0, "fill": "#1A1A2E",
        "scale_x": 1.0, "scale_y": 1.0, "rotation": 0.0,
        "clip_to": None, "clip_x": 0.0, "clip_y": 960.0,
        "clip_w": 1920.0, "clip_h": 60.0,
        "content": None, "repeat_content": False,
        "font_size": None, "font_weight": "regular",
        "text_x_offset": 0.0,
    }]
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "frame_000000.png"
        draw_frame(DrawState(elements=transparent_elements), out)
        assert out.exists()


def test_render_frames_creates_frame_files():
    try:
        from lower_third.renderer.cairo_renderer import render_frames
    except (ImportError, OSError):
        pytest.skip("Cairo not installed")
    ir = MotionIR(
        elements=[ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")],
        tracks=[], total_ms=100
    )
    engine = InterpolationEngine(ir, fps=30)
    state_iter = [(i, engine.get_frame(i)) for i in range(3)]
    with tempfile.TemporaryDirectory() as tmpdir:
        frames_dir = render_frames(state_iter, Path(tmpdir), fps=30)
        pngs = list(frames_dir.glob("frame_*.png"))
        assert len(pngs) == 3


def test_render_frames_returns_frames_dir():
    try:
        from lower_third.renderer.cairo_renderer import render_frames
    except (ImportError, OSError):
        pytest.skip("Cairo not installed")
    ir = MotionIR(
        elements=[ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")],
        tracks=[], total_ms=100
    )
    engine = InterpolationEngine(ir, fps=30)
    state_iter = [(i, engine.get_frame(i)) for i in range(2)]
    with tempfile.TemporaryDirectory() as tmpdir:
        result = render_frames(state_iter, Path(tmpdir), fps=30)
        assert result.name == "frames"
        assert result.is_dir()


def test_dispatcher_returns_path():
    from lower_third.renderer import render
    ir = MotionIR(
        elements=[ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")],
        tracks=[], total_ms=100
    )
    engine = InterpolationEngine(ir, fps=30)
    state_iter = [(i, engine.get_frame(i)) for i in range(2)]
    with tempfile.TemporaryDirectory() as tmpdir:
        result = render(state_iter, Path(tmpdir), fps=30)
        assert result is not None
        assert result.is_dir()


def test_pillow_fallback_creates_png():
    from lower_third.renderer.pillow_renderer import draw_frame
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "frame_000000.png"
        draw_frame(_make_state(), out)
        assert out.exists()
        assert out.stat().st_size > 0


def test_pillow_fallback_output_is_1920x1080():
    from lower_third.renderer.pillow_renderer import draw_frame
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "frame_000000.png"
        draw_frame(_make_state(), out)
        img = Image.open(out)
        assert img.size == (1920, 1080)


def test_pillow_fallback_is_rgba():
    from lower_third.renderer.pillow_renderer import draw_frame
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "frame_000000.png"
        draw_frame(_make_state(), out)
        img = Image.open(out)
        assert img.mode == "RGBA"


def _make_path_state(d: str | None) -> DrawState:
    el: dict = {
        "id": "shape1", "type": "path",
        "x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0,
        "opacity": 1.0, "fill": "#E63946",
        "scale_x": 1.0, "scale_y": 1.0, "rotation": 0.0,
        "clip_to": None, "clip_x": None, "clip_y": None,
        "clip_w": None, "clip_h": None,
        "content": None, "repeat_content": False,
        "font_size": None, "font_weight": "regular",
        "text_x_offset": 0.0,
    }
    if d is not None:
        el["d"] = d
    return DrawState(elements=[el])


def _cairo_skip() -> None:
    """Skip the test if cairocffi / libcairo is absent on this machine."""
    try:
        import cairocffi  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("Cairo not installed")


def test_draw_frame_with_circle_path_creates_png():
    _cairo_skip()
    from lower_third.renderer.cairo_renderer import draw_frame
    circle_d = "M 880.0,540.0 A 40.0,40.0 0 1,0 960.0,540.0 A 40.0,40.0 0 1,0 880.0,540.0 Z"
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "circle.png"
        draw_frame(_make_path_state(circle_d), out)
        assert out.exists()
        assert out.stat().st_size > 0


def test_draw_frame_with_chevron_path_creates_png():
    _cairo_skip()
    from lower_third.renderer.cairo_renderer import draw_frame
    chevron_d = "M 860.0,490.0 L 940.0,490.0 L 960.0,540.0 L 940.0,590.0 L 860.0,590.0 L 880.0,540.0 Z"
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "chevron.png"
        draw_frame(_make_path_state(chevron_d), out)
        assert out.exists()
        assert out.stat().st_size > 0


def test_draw_frame_with_path_d_none_does_not_crash():
    _cairo_skip()
    from lower_third.renderer.cairo_renderer import draw_frame
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "skip.png"
        draw_frame(_make_path_state(None), out)
        assert out.exists()


def test_draw_svg_path_unknown_command_raises():
    _cairo_skip()
    import cairocffi as cairo
    from lower_third.renderer.cairo_renderer import _draw_svg_path
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 100, 100)
    ctx = cairo.Context(surface)
    with pytest.raises(ValueError, match="Unrecognised SVG path command"):
        _draw_svg_path(ctx, "M 0,0 Q 50,50 100,0 Z")


def test_ffmpeg_encoder_stub_raises_not_implemented():
    from lower_third.renderer.ffmpeg_encoder import encode_to_webm
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(NotImplementedError):
            encode_to_webm(Path(tmpdir), Path(tmpdir), fps=30)


# ── Gradient rendering ────────────────────────────────────────────────────────

def _make_gradient_state(angle_deg: float = 0.0) -> DrawState:
    return DrawState(elements=[{
        "id": "bar", "type": "rect",
        "x": 0.0, "y": 960.0, "w": 1920.0, "h": 60.0,
        "opacity": 1.0, "fill": "#000000",
        "gradient": {
            "start_color": "#FF0000",
            "end_color": "#0000FF",
            "angle_deg": angle_deg,
        },
        "scale_x": 1.0, "scale_y": 1.0, "rotation": 0.0,
        "clip_to": None, "clip_x": None, "clip_y": None,
        "clip_w": None, "clip_h": None,
        "content": None, "repeat_content": False,
        "font_size": None, "font_weight": "regular",
        "text_x_offset": 0.0, "d": None,
    }])


def test_gradient_rect_creates_png():
    _cairo_skip()
    from lower_third.renderer.cairo_renderer import draw_frame
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "gradient.png"
        draw_frame(_make_gradient_state(), out)
        assert out.exists()
        assert out.stat().st_size > 0


def test_gradient_rect_left_pixel_differs_from_right():
    """Left edge should be red-ish, right edge should be blue-ish for 0° gradient."""
    _cairo_skip()
    from lower_third.renderer.cairo_renderer import draw_frame
    import cairocffi as cairo
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "gradient.png"
        draw_frame(_make_gradient_state(angle_deg=0.0), out)
        surface = cairo.ImageSurface.create_from_png(str(out))
        import struct
        data = surface.get_data()
        stride = surface.get_stride()
        row = 970  # inside the bar
        def pixel(col: int) -> tuple[int, int, int]:
            offset = row * stride + col * 4
            b, g, r, a = data[offset], data[offset+1], data[offset+2], data[offset+3]
            return r, g, b
        left_r, left_g, left_b = pixel(10)
        right_r, right_g, right_b = pixel(1910)
        assert left_r > left_b, "left pixel should be red-dominant"
        assert right_b > right_r, "right pixel should be blue-dominant"


def test_gradient_pillow_rect_creates_png():
    from lower_third.renderer.pillow_renderer import draw_frame
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "gradient_pil.png"
        draw_frame(_make_gradient_state(), out)
        assert out.exists()
        img = Image.open(out)
        assert img.size == (1920, 1080)


def test_draw_frame_text_align_center_renders():
    _cairo_skip()
    from lower_third.renderer.cairo_renderer import draw_frame
    state = DrawState(elements=[{
        "id": "badge_text", "type": "text",
        "content": "LIVE",
        "x": 0.0, "y": 960.0, "w": 120.0, "h": 60.0,
        "opacity": 1.0, "fill": "#FFFFFF",
        "scale_x": 1.0, "scale_y": 1.0, "rotation": 0.0,
        "clip_to": None,
        "content": "LIVE",
        "repeat_content": False,
        "font_size": 24, "font_weight": "bold",
        "text_x_offset": 0.0,
        "text_align": "center",
    }])
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "center.png"
        draw_frame(state, out)
        assert out.exists()
        assert out.stat().st_size > 0


def test_draw_frame_text_align_left_default_renders():
    _cairo_skip()
    from lower_third.renderer.cairo_renderer import draw_frame
    state = DrawState(elements=[{
        "id": "label", "type": "text",
        "content": "BREAKING NEWS",
        "x": 140.0, "y": 948.0, "w": 0.0, "h": 0.0,
        "opacity": 1.0, "fill": "#FFFFFF",
        "scale_x": 1.0, "scale_y": 1.0, "rotation": 0.0,
        "clip_to": None,
        "repeat_content": False,
        "font_size": 32, "font_weight": "bold",
        "text_x_offset": 0.0,
    }])
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "left.png"
        draw_frame(state, out)
        assert out.exists()
        assert out.stat().st_size > 0
