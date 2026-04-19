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
    except ImportError:
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
    except ImportError:
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
    except ImportError:
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
    except ImportError:
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
    except ImportError:
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
    except ImportError:
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


def test_ffmpeg_encoder_stub_raises_not_implemented():
    from lower_third.renderer.ffmpeg_encoder import encode_to_webm
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(NotImplementedError):
            encode_to_webm(Path(tmpdir), Path(tmpdir), fps=30)
