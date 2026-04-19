import logging
import shutil
import uuid
from pathlib import Path

from lower_third.choreography.brand_resolver import resolve_brand
from lower_third.parser.llm_parser import parse_prompt
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
    tts_timestamps: dict | None = None,
    instance_id: str | None = None,
) -> dict:
    # Step 1 — Setup
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 2 — Brand resolver (runs BEFORE LLM)
    brand = resolve_brand(upstream_signals, estimated_lines=2)
    log.info("Brand resolved: bar_y=%d, bar_h=%d", brand.bar_y, brand.bar_h)

    # Step 3 — LLM parse
    spec = parse_prompt(user_prompt, brand)
    spec.instance_id = instance_id or f"lt_{uuid.uuid4().hex[:8]}"
    log.info("Spec parsed: instance_id=%s", spec.instance_id)

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
    if cached_path:
        log.info("Cache hit for %s", spec.instance_id)
        video_path = output_dir / f"{spec.instance_id}.webm"
        shutil.copy(cached_path, video_path)
        qc_report = validate(video_path, spec, project_fps)
        manifest = write_manifest(spec, video_path, qc_report, output_dir)
        return {"video_path": video_path, "manifest": manifest,
                "qc_report": qc_report, "cache_hit": True}

    # Step 6 — Interpolation engine
    engine = InterpolationEngine(spec.motion, fps=project_fps)
    log.info("Engine ready: %d frames", engine.total_frames)

    # Step 7 — Render
    state_iter = [(i, engine.get_frame(i)) for i in range(engine.total_frames)]
    frames_dir = render(state_iter, output_dir, project_fps)
    log.info("Rendered %d frames to %s", engine.total_frames, frames_dir)

    # Step 8 — Encode
    video_path = encode_to_webm(frames_dir, output_dir, project_fps)
    log.info("Encoded: %s", video_path)

    # Step 9 — Cache write
    cache_write(spec, video_path)

    # Step 10 — QC
    qc_report = validate(video_path, spec, project_fps)
    if qc_report.warnings:
        log.warning("QC warnings: %s", qc_report.warnings)

    # Step 11 — Manifest
    manifest = write_manifest(spec, video_path, qc_report, output_dir)

    # Step 12 — Return
    log.info("Pipeline complete: %s", spec.instance_id)
    return {"video_path": video_path, "manifest": manifest,
            "qc_report": qc_report, "cache_hit": False}
