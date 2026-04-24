from __future__ import annotations

import logging
import math

from lower_third.motion.motion_ir import AnimationTrack, Keyframe, MotionIR
from lower_third.renderer.text_measurer import SCROLL_SPEED_PX_S, measure_text_width

log = logging.getLogger(__name__)


_CANVAS_W = 1920.0


def _build_ticker_items_content(
    ir: MotionIR,
) -> tuple[MotionIR, dict[str, float]]:
    """Pre-process ticker_items into a measured content string with gap spacers.

    The gap between items must be wide enough so each item has fully cleared the
    visible clip region before the next one enters.  For a clip bar of width B
    and a requested pause of P ms at scroll speed S px/s:

        gap_px = B + S * P / 1000

    The bar_width B ensures the previous item is fully off-screen before the
    next enters; the additional S*P/1000 provides the requested "empty pause".

    Returns (updated_ir, first_item_widths) where first_item_widths maps
    element_id → measured pixel width of the first ticker_item's text.
    Note: first_item_widths is retained for logging but no longer used to
    adjust x — the ticker element always stays anchored at bar_right so that
    every loop restart produces a clean right-to-left entry (train motion).
    """
    element_map = {el.id: el for el in ir.elements}
    new_elements = list(ir.elements)
    first_item_widths: dict[str, float] = {}
    changed = False
    for i, el in enumerate(ir.elements):
        if not el.ticker_items:
            continue

        # Measure first item width for x-alignment at loop start
        first_item_widths[el.id] = measure_text_width(
            text=el.ticker_items[0].text,
            font_family=el.font_family,
            font_size=el.font_size or 32,
            font_weight=el.font_weight,
        )

        # Determine clip-bar width so we can calculate the true gap
        bar_width = _CANVAS_W
        if el.clip_to and el.clip_to in element_map:
            bar_el = element_map[el.clip_to]
            if bar_el.w is not None:
                bar_width = float(bar_el.w)

        space_px = measure_text_width(
            text=" ",
            font_family=el.font_family,
            font_size=el.font_size or 32,
            font_weight=el.font_weight,
        )
        if space_px <= 0:
            space_px = (el.font_size or 32) * 0.3

        parts: list[str] = []
        for item in el.ticker_items:
            parts.append(item.text)
            if item.pause_after_ms > 0:
                # bar_width clears the screen; pause adds extra empty time
                gap_px = bar_width + SCROLL_SPEED_PX_S * (item.pause_after_ms / 1000.0)
                n_spaces = max(1, math.ceil(gap_px / space_px))
                parts.append(" " * n_spaces)
        assembled = "".join(parts)
        new_elements[i] = el.model_copy(update={
            "content": assembled,
            "repeat_content": True,
            "ticker_items": None,
        })
        changed = True
        log.info(
            "Ticker '%s': built content from %d ticker_items (bar_width=%.0fpx), "
            "total length %d chars",
            el.id, len(el.ticker_items), bar_width, len(assembled),
        )
    if not changed:
        return ir, first_item_widths
    return ir.model_copy(update={"elements": new_elements}), first_item_widths


def correct_ticker_widths(ir: MotionIR) -> MotionIR:
    ir, first_item_widths = _build_ticker_items_content(ir)

    ticker_elements = [
        el for el in ir.elements
        if el.repeat_content is True
        and el.type == "text"
        and el.content is not None
    ]

    if not ticker_elements:
        return ir

    element_map = {el.id: el for el in ir.elements}
    track_map: dict[tuple[str, str], AnimationTrack] = {
        (t.element_id, t.property): t for t in ir.tracks
    }

    new_tracks = list(ir.tracks)
    new_elements = list(ir.elements)
    new_loop = ir.loop

    for el in ticker_elements:
        true_width = measure_text_width(
            text=el.content,
            font_family=el.font_family,
            font_size=el.font_size or 32,
            font_weight=el.font_weight,
        )

        track_key = (el.id, "text_x_offset")
        track = track_map.get(track_key)

        scroll_ms = max(1000, int((true_width / SCROLL_SPEED_PX_S) * 1000))

        if track is None:
            log.warning(
                "Ticker '%s': no text_x_offset track found — synthesizing one (%.1fpx, %dms)",
                el.id, true_width, scroll_ms,
            )
            from lower_third.motion.motion_ir import AnimationTrack, Keyframe, EasingConfig, EasingType
            synth_track = AnimationTrack(
                element_id=el.id,
                property="text_x_offset",
                start_offset_ms=0,
                keyframes=[
                    Keyframe(t_ms=0, value=0.0, easing=EasingConfig(type=EasingType.linear)),
                    Keyframe(t_ms=scroll_ms, value=-true_width, easing=EasingConfig(type=EasingType.linear)),
                ],
            )
            new_tracks.append(synth_track)
        else:
            log.info(
                "Ticker '%s': LLM width estimate replaced with measured %.1fpx. scroll_ms=%d",
                el.id, true_width, scroll_ms,
            )

            sorted_kfs = sorted(track.keyframes, key=lambda kf: kf.t_ms)
            last_kf = sorted_kfs[-1]
            patched_last = last_kf.model_copy(update={"value": -true_width, "t_ms": scroll_ms})
            patched_kfs = sorted_kfs[:-1] + [patched_last]

            patched_track = track.model_copy(update={"keyframes": patched_kfs})

            new_tracks = [
                patched_track if t.element_id == el.id and t.property == "text_x_offset" else t
                for t in new_tracks
            ]

        new_loop = new_loop.model_copy(update={"loop_after_ms": scroll_ms})

        # For ticker_items elements: place x so the first item's right edge is
        # at bar_right when offset=0 — the first item is immediately visible on
        # loop restart with no empty-bar gap.
        # For continuous tickers (no ticker_items): anchor at bar_right so the
        # seamless repeat_content second copy aligns correctly.
        clip_id = el.clip_to
        if clip_id and clip_id in element_map:
            bar_el = element_map[clip_id]
            if bar_el.w is not None:
                bar_right = float(bar_el.x + bar_el.w)
                # Always anchor at bar_right so items enter from the right edge on
                # every loop restart — this produces the train-car motion the user
                # expects (L1→L2→L3→L1…) with no abrupt jump.
                new_x = bar_right
                if abs(el.x - new_x) > 0.5:
                    log.info(
                        "Ticker '%s': adjusting x from %.1f to %.1f (bar_right=%.1f)",
                        el.id, el.x, new_x, bar_right,
                    )
                    updated_el = el.model_copy(update={"x": new_x})
                    new_elements = [
                        updated_el if e.id == el.id else e for e in new_elements
                    ]

    return ir.model_copy(update={"tracks": new_tracks, "elements": new_elements, "loop": new_loop})
