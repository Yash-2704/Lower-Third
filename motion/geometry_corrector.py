from __future__ import annotations

import logging
import math
from copy import deepcopy

from lower_third.motion.motion_ir import MotionIR, ElementDef, AnimationTrack, Keyframe
from lower_third.choreography.brand_resolver import ResolvedBrand

log = logging.getLogger(__name__)

SAFETY_MARGIN_PX  = 60
CHARS_TO_PX_RATIO = 15
FONT_DESCENDER    = 1.5

# Safety ceiling for loop renders when no explicit user duration is set.
# The LLM emits total_ms=3_600_000 as a sentinel for "loop forever"; we cap
# that to a sane render budget.  Values the user explicitly selects (e.g.
# 300_000 for 5 minutes) are always below this threshold so they pass through
# untouched.
_LOOP_SENTINEL_THRESHOLD_MS = 1_800_000   # 30 minutes — anything larger is a sentinel
_LOOP_SENTINEL_CAP_MS       =   120_000   # 2 minutes  — what we render instead

PLACEHOLDER_PATTERNS = [
    "first headline here",
    "second headline here",
    "main headline",
    "subtext here",
    "additional text",
    "headline goes here",
    "__headline",
]


def apply_geometric_corrections(ir: MotionIR, brand: ResolvedBrand) -> MotionIR:
    ir = _fix_clip_boundaries(ir, brand)
    ir = _fix_timing_consistency(ir)
    ir = _fix_track_uniqueness(ir)
    ir = _fix_initial_visibility(ir, brand)
    ir = _fix_loop_placeholder_content(ir)
    return ir


def _fix_clip_boundaries(ir: MotionIR, brand: ResolvedBrand) -> MotionIR:
    elem_map: dict[str, ElementDef] = {e.id: e for e in ir.elements}

    new_tracks = []
    for track in ir.tracks:
        elem = elem_map.get(track.element_id)
        if elem is None or elem.clip_to is None:
            new_tracks.append(track)
            continue

        clip_elem = elem_map.get(elem.clip_to)
        if clip_elem is None:
            new_tracks.append(track)
            continue

        clip_x = clip_elem.x
        clip_y = clip_elem.y
        clip_w = clip_elem.w or 0.0
        clip_h = clip_elem.h or 0.0

        font_size = elem.font_size or brand.font_size_headline
        full_glyph_height = font_size * FONT_DESCENDER

        new_keyframes = list(track.keyframes)

        if track.property == "y":
            corrected_kfs = []
            for kf in new_keyframes:
                v = kf.value
                if v < clip_y:
                    min_exit = clip_y - full_glyph_height - SAFETY_MARGIN_PX
                    if v > min_exit:
                        log.info(
                            "Corrected exit-above keyframe for %s: %f → %f",
                            track.element_id, v, min_exit,
                        )
                        kf = kf.model_copy(update={"value": min_exit})
                elif v > clip_y + clip_h:
                    min_entry = clip_y + clip_h + SAFETY_MARGIN_PX
                    if v < min_entry:
                        log.info(
                            "Corrected entry-below keyframe for %s: %f → %f",
                            track.element_id, v, min_entry,
                        )
                        kf = kf.model_copy(update={"value": min_entry})
                corrected_kfs.append(kf)
            track = track.model_copy(update={"keyframes": corrected_kfs})

        elif track.property == "x":
            estimated_w = len(elem.content or "") * CHARS_TO_PX_RATIO
            corrected_kfs = []
            for kf in new_keyframes:
                v = kf.value
                if v < clip_x:
                    max_left = clip_x - estimated_w - SAFETY_MARGIN_PX
                    if v > max_left:
                        kf = kf.model_copy(update={"value": max_left})
                elif v > clip_x + clip_w:
                    min_right = clip_x + clip_w + SAFETY_MARGIN_PX
                    if v < min_right:
                        kf = kf.model_copy(update={"value": min_right})
                corrected_kfs.append(kf)
            track = track.model_copy(update={"keyframes": corrected_kfs})

        new_tracks.append(track)

    return ir.model_copy(update={"tracks": new_tracks})


def _fix_timing_consistency(ir: MotionIR) -> MotionIR:
    if not ir.tracks:
        return ir

    true_end_ms = max(
        track.start_offset_ms + track.keyframes[-1].t_ms
        for track in ir.tracks
    )

    total_ms = ir.total_ms
    loop = ir.loop

    if total_ms < true_end_ms:
        log.info("Extended total_ms from %d to %d to cover all tracks", total_ms, true_end_ms)
        total_ms = true_end_ms

    if loop.enabled:
        if loop.loop_after_ms is None:
            # Use the actual animation span as the loop period so the engine
            # wraps correctly. Setting it to total_ms would make loop_frames ==
            # total_frames, i.e. no wrap ever occurs within the video.
            loop = loop.model_copy(update={"loop_after_ms": true_end_ms})
            log.info("Set loop_after_ms from keyframe span: %d ms", true_end_ms)
        elif loop.loop_after_ms > total_ms:
            log.info(
                "Clamped loop_after_ms from %d to %d (total_ms)",
                loop.loop_after_ms, total_ms,
            )
            loop = loop.model_copy(update={"loop_after_ms": total_ms})
        # When loop_after_ms < total_ms the engine already handles wrapping via
        # frame_index % loop_frames — do NOT trim total_ms here.

        # If total_ms looks like the LLM's "loop forever" sentinel (very large),
        # cap it to a manageable render budget rounded to whole cycles.
        # User-chosen durations (e.g. 600_000 for 10 min) are below the
        # threshold and pass through unchanged.
        lap = loop.loop_after_ms
        if lap and lap > 0 and total_ms > _LOOP_SENTINEL_THRESHOLD_MS:
            cycles = math.ceil(_LOOP_SENTINEL_CAP_MS / lap)
            capped = cycles * lap
            log.info(
                "Capped sentinel total_ms from %d to %d ms (%d complete loop cycles)",
                total_ms, capped, cycles,
            )
            total_ms = capped

    return ir.model_copy(update={"total_ms": total_ms, "loop": loop})


def _fix_track_uniqueness(ir: MotionIR) -> MotionIR:
    seen: dict[tuple[str, str], AnimationTrack] = {}

    for track in ir.tracks:
        key = (track.element_id, track.property)
        if key not in seen:
            seen[key] = track
        else:
            existing = seen[key]
            log.info("Merged duplicate track for %s.%s", track.element_id, track.property)

            # Normalise both tracks to absolute t_ms, merge, then re-relativise
            base_offset = min(existing.start_offset_ms, track.start_offset_ms)

            def abs_kfs(t: AnimationTrack) -> list[Keyframe]:
                delta = t.start_offset_ms - base_offset
                return [kf.model_copy(update={"t_ms": kf.t_ms + delta}) for kf in t.keyframes]

            merged_kfs = sorted(
                abs_kfs(existing) + abs_kfs(track),
                key=lambda kf: kf.t_ms,
            )
            # Deduplicate by t_ms (keep last)
            deduped: dict[int, Keyframe] = {}
            for kf in merged_kfs:
                deduped[kf.t_ms] = kf
            merged_kfs = sorted(deduped.values(), key=lambda kf: kf.t_ms)

            seen[key] = existing.model_copy(update={
                "start_offset_ms": base_offset,
                "keyframes": merged_kfs,
            })

    return ir.model_copy(update={"tracks": list(seen.values())})


def _fix_initial_visibility(ir: MotionIR, brand: ResolvedBrand) -> MotionIR:
    elem_map: dict[str, ElementDef] = {e.id: e for e in ir.elements}
    animated_ids = {track.element_id for track in ir.tracks}

    for elem in ir.elements:
        if elem.type != "text" or elem.clip_to is None:
            continue
        clip_elem = elem_map.get(elem.clip_to)
        if clip_elem is None:
            continue

        clip_y = clip_elem.y
        clip_h = clip_elem.h or 0.0
        inside = clip_y <= elem.y <= clip_y + clip_h

        elem_tracks = [t for t in ir.tracks if t.element_id == elem.id]

        if not elem_tracks:
            if inside:
                log.debug(
                    "Element %s is static and inside clip boundary — always visible",
                    elem.id,
                )
            continue

        has_y_track = any(t.property == "y" for t in elem_tracks)
        if not has_y_track and inside:
            log.warning(
                "Element %s is inside clip boundary at frame 0 with no y track "
                "— will be visible immediately",
                elem.id,
            )

    return ir


def _fix_loop_placeholder_content(ir: MotionIR) -> MotionIR:
    for elem in ir.elements:
        if elem.type != "text" or not elem.content:
            continue
        lower = elem.content.lower()
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern in lower:
                log.warning(
                    "Element '%s' may contain placeholder content: '%s'",
                    elem.id, elem.content,
                )
                break
    return ir
