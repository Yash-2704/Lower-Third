import logging
from pathlib import Path
from lower_third.motion.interpolation_engine import DrawState

log = logging.getLogger(__name__)


def render(state_iter, output_dir: Path, fps: int = 30) -> Path:
    """
    Dispatcher: tries Cairo renderer, falls back to Pillow on ImportError.
    Returns the frames directory path.
    """
    try:
        from lower_third.renderer.cairo_renderer import render_frames
        log.info("Using Cairo renderer")
    except (ImportError, OSError) as e:
        log.warning("Cairo unavailable (%s) — falling back to Pillow renderer", e)
        from lower_third.renderer.pillow_renderer import render_frames
    return render_frames(state_iter, output_dir, fps)
