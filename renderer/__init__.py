from pathlib import Path
from lower_third.motion.interpolation_engine import DrawState


def render(state_iter, output_dir: Path, fps: int = 30) -> Path:
    """
    Dispatcher: tries Cairo renderer, falls back to Pillow on ImportError.
    Returns the frames directory path.
    """
    try:
        from lower_third.renderer.cairo_renderer import render_frames
    except ImportError:
        from lower_third.renderer.pillow_renderer import render_frames
    return render_frames(state_iter, output_dir, fps)
