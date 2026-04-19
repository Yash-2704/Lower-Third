from __future__ import annotations

import logging

from lower_third.motion.motion_ir import MotionIR, AnimationTrack

log = logging.getLogger(__name__)


def anchor_tracks_to_tts(
    ir: MotionIR,
    tts_timestamps: dict[str, int],
    element_words: dict[str, str],
) -> MotionIR:
    if not tts_timestamps:
        return ir

    for element_id, word in element_words.items():
        if word not in tts_timestamps:
            log.debug("Word '%s' not in timestamps, skipping", word)
            continue

        target_ms = tts_timestamps[word]

        element_tracks = [t for t in ir.tracks if t.element_id == element_id]

        track: AnimationTrack | None = None
        for t in element_tracks:
            if t.property == "y":
                track = t
                break
        if track is None:
            for t in element_tracks:
                if t.property == "opacity":
                    track = t
                    break
        if track is None:
            continue

        track.start_offset_ms = target_ms
        log.info(
            "Anchored %s.%s to word '%s' at %dms",
            element_id, track.property, word, target_ms,
        )

    if ir.tracks:
        ir.total_ms = max(
            t.start_offset_ms + t.keyframes[-1].t_ms for t in ir.tracks
        )

    return ir


def build_element_words(ir: MotionIR) -> dict[str, str]:
    return {
        el.id: el.content.split()[0]
        for el in ir.elements
        if el.type == "text" and el.content and el.content.strip()
    }
