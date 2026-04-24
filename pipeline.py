import logging
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from lower_third.choreography.brand_resolver import resolve_brand
from lower_third.parser.llm_parser import parse_prompt
from lower_third.motion.shape_resolver import resolve_shapes
from lower_third.motion.geometry_corrector import apply_geometric_corrections
from lower_third.motion.ticker_corrector import correct_ticker_widths
from lower_third.motion.interpolation_engine import InterpolationEngine
from lower_third.renderer import render
from lower_third.renderer.ffmpeg_encoder import encode_to_webm
from lower_third.cache.template_cache import cache_hit, cache_write
from lower_third.qc.validator import validate
from lower_third.output.manifest_writer import write_manifest

log = logging.getLogger(__name__)


def generate_lower_third(
    user_prompt: str,
    upstream_signals: dict,
    output_dir: Path,
    project_fps: int = 30,
    total_duration_ms: int | None = None,
    tts_timestamps: dict | None = None,
    instance_id: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
    timecode_in: str | None = None,
    timecode_out: str | None = None,
) -> dict:
    def _progress(stage: str) -> None:
        if progress_callback:
            progress_callback(stage)
    # Step 1 — Setup
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 2 — Brand resolver (runs BEFORE LLM)
    brand = resolve_brand(upstream_signals, estimated_lines=2)
    log.info("Brand resolved: bar_y=%d, bar_h=%d", brand.bar_y, brand.bar_h)
    _progress("brand_resolve")

    # Step 3 — LLM parse
    spec = parse_prompt(user_prompt, brand)
    spec.instance_id = instance_id or f"lt_{uuid.uuid4().hex[:8]}"
    log.info("Spec parsed: instance_id=%s", spec.instance_id)
    _progress("llm_parse")

    # Step 3b — Apply user-specified total duration (overrides LLM value)
    if total_duration_ms is not None and total_duration_ms > 0:
        spec.motion = spec.motion.model_copy(
            update={"total_ms": total_duration_ms}
        )
        log.info("User-specified total_duration_ms applied: %d ms", total_duration_ms)

    # Step 4 — TTS anchor (optional)
    if tts_timestamps:
        try:
            from lower_third.choreography.tts_anchor import anchor_tracks_to_tts
            element_words = {
                el.id: el.content.split()[0]
                for el in spec.motion.elements
                if el.type == "text" and el.content
            }
            spec.motion = anchor_tracks_to_tts(spec.motion, tts_timestamps, element_words)
            log.info("TTS anchor applied")
        except (ImportError, Exception) as e:
            log.warning("TTS anchor skipped: %s", e)

    # Step 5 — Cache check
    cached_path = cache_hit(spec)
    _progress("cache_check")
    if cached_path:
        log.info("Cache hit for %s", spec.instance_id)
        video_path = output_dir / f"{spec.instance_id}.webm"
        shutil.copy(cached_path, video_path)
        _progress("geometry")
        _progress("interpolation")
        _progress("render")
        _progress("encode")
        qc_report = validate(video_path, spec, project_fps)
        _progress("qc")
        manifest = write_manifest(
            spec, video_path, qc_report, output_dir,
            timecode_in=timecode_in,
            timecode_out=timecode_out,
        )
        _progress("manifest")
        return {"video_path": video_path, "manifest": manifest,
                "qc_report": qc_report, "cache_hit": True}

    # Step 5b — Geometric corrections then shape resolver
    # Shape resolver runs AFTER corrections so corrected shape_intent produces correct path d.
    log.info("Applying geometric corrections")
    spec.motion = apply_geometric_corrections(spec.motion, brand)
    log.info("Geometric corrections applied")
    spec.motion = resolve_shapes(spec.motion)
    log.info("Shape resolver applied")

    # Step 5c — Ticker width correction (must run after geometry, before render)
    spec.motion = correct_ticker_widths(spec.motion)
    log.info("Ticker widths corrected")
    _progress("geometry")

    # Step 6 — Interpolation engine
    engine = InterpolationEngine(spec.motion, fps=project_fps)
    log.info("Engine ready: %d frames", engine.total_frames)
    _progress("interpolation")

    # Step 7 — Render
    state_iter = [(i, engine.get_frame(i)) for i in range(engine.total_frames)]
    frames_dir = render(state_iter, output_dir, project_fps)
    log.info("Rendered %d frames to %s", engine.total_frames, frames_dir)
    _progress("render")

    # Step 8 — Encode
    video_path = encode_to_webm(frames_dir, output_dir, project_fps)
    log.info("Encoded: %s", video_path)
    _progress("encode")

    # Step 9 — Cache write
    cache_write(spec, video_path)

    # Step 10 — QC
    qc_report = validate(video_path, spec, project_fps, frames_dir=frames_dir)
    if qc_report.warnings:
        log.warning("QC warnings: %s", qc_report.warnings)
    _progress("qc")

    # Step 11 — Manifest
    manifest = write_manifest(
        spec, video_path, qc_report, output_dir,
        timecode_in=timecode_in,
        timecode_out=timecode_out,
    )
    _progress("manifest")

    # Step 12 — Return
    log.info("Pipeline complete: %s", spec.instance_id)
    return {"video_path": video_path, "manifest": manifest,
            "qc_report": qc_report, "cache_hit": False}
