from __future__ import annotations

import logging
import math
from copy import deepcopy

from lower_third.motion.motion_ir import MotionIR, ElementDef, AnimationTrack, Keyframe
from lower_third.choreography.brand_resolver import ResolvedBrand

log = logging.getLogger(__name__)

SAFETY_MARGIN_PX  = 60
FONT_DESCENDER    = 1.5

# Padding applied to label-row text (e.g. "BREAKING NEWS"):
#   LEFT_PADDING   — minimum gap between the badge circle's right edge and the
#                    text's left edge, so the text never crowds the badge.
#   BOTTOM_OFFSET  — number of pixels to shift the centred y upward, so the
#                    visible cap-block has visible breathing room above the
#                    label-row separator line.
LABEL_TEXT_LEFT_PADDING:  int = 16
LABEL_TEXT_BOTTOM_OFFSET: int = 8

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
    ir = _fix_clip_target_dimensions(ir, brand)    # ensure clip rects have non-zero h
    ir = _fix_circle_badge_position(ir, brand)     # guard circle cy/cx before ticker injection
    ir = _fix_badge_text_position(ir, brand)       # enforce badge text y centred in circle
    ir = _fix_label_text_position(ir, brand)       # enforce label text vertical centering
    ir = _fix_ticker_row_position(ir, brand)       # correct ticker rect y before scroll-bar injection
    ir = _ensure_separator_line(ir, brand)         # guarantee 2px dark line between rows
    ir = _ensure_ticker_scroll_bar(ir, brand)   # must run before draw-order sort
    ir = _fix_timing_consistency(ir)
    ir = _fix_track_uniqueness(ir)
    ir = _fix_initial_visibility(ir, brand)
    ir = _fix_loop_placeholder_content(ir)
    ir = _fix_draw_order(ir)
    return ir


_TICKER_DARK_FILL  = "#1A1A3A"
_SCROLL_BAR_FILL   = "#FFFFFF"
_SCROLL_BAR_ID     = "scroll_bar"
_UPPER_BAR_ID      = "upper_bar_bg"
_BADGE_WIDTH       = 120.0   # badge cx=60, rx=60 → right edge at x=120


def _is_light_color(hex_color: str) -> bool:
    """Return True if the color has high luminance (light / not readable on white)."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) > 128
    except (ValueError, AttributeError, IndexError):
        return False


def _fix_circle_badge_position(ir: MotionIR, brand: ResolvedBrand) -> MotionIR:
    """Enforce circle badge position regardless of LLM coordinate choices.

    Always sets cx=rx=60, ry=60, and cy to the vertical centre of the full
    lower-third zone (bar_y to canvas bottom).  Clears d so the shape resolver
    recomputes the path from the corrected intent.
    """
    expected_rx: float = 60.0
    expected_ry: float = 60.0
    expected_cx: float = expected_rx  # flush left: cx == rx

    corrected = []
    for el in ir.elements:
        if el.type == "path" and el.shape_intent is not None:
            intent = el.shape_intent
            if intent.kind.value in ("circle", "ellipse"):
                expected_cy = float(
                    brand.bar_y + (brand.canvas_h - brand.bar_y) // 2
                )
                max_cy = float(brand.canvas_h - expected_ry - 2)
                corrected_cy = min(expected_cy, max_cy)

                new_intent = intent.model_copy(update={
                    "cx": expected_cx,
                    "cy": corrected_cy,
                    "rx": expected_rx,
                    "ry": expected_ry,
                })
                el = el.model_copy(update={"shape_intent": new_intent, "d": None})
                log.info(
                    "Circle badge corrected: cx=%d cy=%d rx=%d ry=%d",
                    expected_cx, corrected_cy, expected_rx, expected_ry,
                )
        corrected.append(el)
    return ir.model_copy(update={"elements": corrected})


def _fix_badge_text_position(ir: MotionIR, brand: ResolvedBrand) -> MotionIR:
    """Enforce badge text element y so LIVE/NEWS sit centred in the circle.

    Identifies badge text elements via id substring "badge" OR (no clip_to AND
    y is within the circle's vertical extent). Requires exactly two such
    elements; otherwise logs a warning and returns ir unchanged.
    """
    cy = brand.circle_cy
    rx = brand.circle_rx
    cx = brand.circle_cx

    badge_texts: list[ElementDef] = []
    for el in ir.elements:
        if el.type != "text":
            continue
        id_match = "badge" in el.id.lower()
        # Badge text always sits in the leftmost circle column (x ≈ 0..120).
        # The LLM frequently misplaces it vertically, so we identify by x
        # rather than y to remain robust to wrong y values.
        in_circle_column = (
            el.clip_to is None
            and float(el.x) < (cx + rx)
        )
        if id_match or in_circle_column:
            badge_texts.append(el)

    if len(badge_texts) != 2:
        if badge_texts:
            log.warning(
                "Badge text correction skipped: expected 2 elements, found %d",
                len(badge_texts),
            )
        return ir

    sorted_texts = sorted(badge_texts, key=lambda e: e.y)
    line1, line2 = sorted_texts[0], sorted_texts[1]

    fs1 = line1.font_size or 16
    fs2 = line2.font_size or 16
    targets: dict[str, dict] = {
        line1.id: {
            "y": float(cy - fs1),
            "x": float(cx - rx),
            "w": float(rx * 2),
            "text_align": "center",
        },
        line2.id: {
            "y": float(cy + 4),
            "x": float(cx - rx),
            "w": float(rx * 2),
            "text_align": "center",
        },
    }

    new_elements = []
    for el in ir.elements:
        if el.id in targets:
            updates = targets[el.id]
            log.info(
                "Badge text '%s' y corrected: %d → %d",
                el.content or el.id, int(el.y), int(updates["y"]),
            )
            el = el.model_copy(update=updates)
        new_elements.append(el)

    return ir.model_copy(update={"elements": new_elements})


def _fix_label_text_position(ir: MotionIR, brand: ResolvedBrand) -> MotionIR:
    """Vertically centre label-row text (e.g. BREAKING NEWS) within the label row."""
    new_elements = []
    for el in ir.elements:
        if (
            el.type == "text"
            and brand.bar_y <= el.y <= brand.bar_y_ticker
            and "badge" not in el.id.lower()
            and not el.repeat_content
        ):
            font_size = el.font_size or 28
            # Pango's show_layout treats (x, y) as the layout top-left.
            # For Noto Sans Bold:   ascent ≈ 0.92·fs,  cap_height ≈ 0.72·fs.
            # We want the visible cap-block centred in the label row, i.e.
            #   cap_center = bar_center
            #   layout_top + ascent - cap_h/2 = bar_y + row_h/2
            # → layout_top = bar_y + row_h/2 - (0.92 - 0.36)·fs
            #              = bar_y + row_h/2 - 0.56·fs
            # Then nudge upward by LABEL_TEXT_BOTTOM_OFFSET so the glyphs leave
            # visible breathing room above the label-row separator.
            centred_y = (
                brand.bar_y
                + brand.label_row_h // 2
                - int(font_size * 0.56)
                - LABEL_TEXT_BOTTOM_OFFSET
            )
            # Enforce a left padding so the text never crowds the badge circle.
            min_x = int(brand.circle_cx + brand.circle_rx + LABEL_TEXT_LEFT_PADDING)
            new_x = max(int(el.x), min_x)
            if int(el.y) != centred_y or int(el.x) != new_x:
                log.info(
                    "Label text '%s' corrected: x=%d→%d y=%d→%d",
                    el.id, int(el.x), new_x, int(el.y), centred_y,
                )
                el = el.model_copy(update={"x": float(new_x), "y": float(centred_y)})
        new_elements.append(el)
    return ir.model_copy(update={"elements": new_elements})


def _fix_ticker_row_position(ir: MotionIR, brand: ResolvedBrand) -> MotionIR:
    """Move a misplaced ticker background rect from the upper bar row to the lower row.

    When the LLM places the ticker clip rect at bar_y instead of bar_y+bar_h//2,
    the white ticker rect overlaps the coloured label bar creating a white streak.
    This corrector repositions it before _ensure_ticker_scroll_bar runs so that
    the scroll-bar injection can find and normalise it rather than orphaning the
    misplaced rect.
    """
    ticker_elements = [
        el for el in ir.elements
        if el.type == "text" and (
            (el.ticker_items and len(el.ticker_items) > 0) or el.repeat_content
        )
    ]
    if not ticker_elements:
        return ir

    scroll_y = float(brand.bar_y_ticker)
    element_map = {el.id: el for el in ir.elements}
    new_elements = list(ir.elements)

    for ticker_el in ticker_elements:
        if not ticker_el.clip_to:
            continue
        ticker_rect = element_map.get(ticker_el.clip_to)
        if ticker_rect is None or ticker_rect.type != "rect":
            continue
        # Already in or below the lower row — nothing to fix.
        if float(ticker_rect.y or 0) >= scroll_y - 5:
            continue
        # Full-height bar: leave it for _ensure_ticker_scroll_bar to handle.
        if float(ticker_rect.h or 0) > brand.ticker_row_h + 5:
            continue

        # Label row rect: the topmost non-ticker rect in the bar zone.
        bar_rects = [
            el for el in ir.elements
            if el.type == "rect"
            and el.id != ticker_rect.id
            and el.y is not None
            and brand.bar_y - 5 <= float(el.y) < brand.bar_y + brand.bar_h
        ]
        if not bar_rects:
            continue

        label_rect = min(bar_rects, key=lambda el: float(el.y))
        if float(ticker_rect.y or 0) <= float(label_rect.y or 0):
            old_y = float(ticker_rect.y or 0)
            new_y = float(label_rect.y or 0) + float(label_rect.h or brand.bar_h // 2)
            log.info(
                "Corrected ticker rect '%s' y from %.0f to %.0f",
                ticker_rect.id, old_y, new_y,
            )
            fixed = ticker_rect.model_copy(update={"y": new_y})
            new_elements = [fixed if e.id == ticker_rect.id else e for e in new_elements]
            element_map = {el.id: el for el in new_elements}

    return ir.model_copy(update={"elements": new_elements})


_SEPARATOR_ID   = "separator"
_SEPARATOR_FILL = "#1A1A2E"
_SEPARATOR_H    = 2


def _ensure_separator_line(ir: MotionIR, brand: ResolvedBrand) -> MotionIR:
    """Guarantee a 2px dark separator line exists at bar_y_ticker spanning full canvas width."""
    if any(el.id == _SEPARATOR_ID for el in ir.elements):
        return ir

    separator = ElementDef(
        id=_SEPARATOR_ID,
        type="rect",
        x=0,
        y=float(brand.bar_y_ticker),
        w=float(brand.canvas_w),
        h=float(_SEPARATOR_H),
        fill=_SEPARATOR_FILL,
        opacity=1.0,
    )
    log.info("Inserted separator line at y=%d", brand.bar_y_ticker)
    return ir.model_copy(update={"elements": list(ir.elements) + [separator]})


def _ensure_ticker_scroll_bar(ir: MotionIR, brand: ResolvedBrand) -> MotionIR:
    """Guarantee every scrolling ticker element has a pure-white scroll bar.

    The LLM sometimes skips the white background rect entirely, or generates it
    with the wrong fill/position.  This step is deterministic: it always produces
    the correct white strip and wires up the ticker's clip_to reference to it.

    Invariants enforced:
    * A rect element with id=scroll_bar exists at y=bar_y+bar_h//2, h=bar_h//2,
      x=0, w=canvas_w, fill=#FFFFFF, opacity=1.0.
    * Every ticker text element (has ticker_items or repeat_content) has
      clip_to pointing to that scroll_bar.
    * Every ticker text element has a dark fill so text is legible on white.
    """
    ticker_elements = [
        el for el in ir.elements
        if el.type == "text" and (
            (el.ticker_items and len(el.ticker_items) > 0) or el.repeat_content
        )
    ]
    if not ticker_elements:
        return ir

    scroll_y = float(brand.bar_y_ticker)
    scroll_h = float(brand.ticker_row_h)

    element_map: dict[str, ElementDef] = {el.id: el for el in ir.elements}
    new_elements = list(ir.elements)

    # Find any existing rect near the expected scroll-bar position.
    # Use a tight tolerance (5px) so we don't accidentally match the label/accent
    # rects that sit just above the scroll bar.
    existing_sb: ElementDef | None = None
    for el in ir.elements:
        if el.type != "rect" or el.y is None:
            continue
        if abs(float(el.y) - scroll_y) <= 5:
            existing_sb = el
            break

    if existing_sb is not None:
        # Fix fill / opacity / position in-place and normalise id.
        expected_w = float(brand.canvas_w) - _BADGE_WIDTH
        updates: dict = {}
        if existing_sb.fill != _SCROLL_BAR_FILL:
            updates["fill"] = _SCROLL_BAR_FILL
        if existing_sb.opacity != 1.0:
            updates["opacity"] = 1.0
        if existing_sb.id != _SCROLL_BAR_ID:
            updates["id"] = _SCROLL_BAR_ID
        if (existing_sb.x or 0.0) < _BADGE_WIDTH:
            updates["x"] = _BADGE_WIDTH
            updates["w"] = expected_w
        if (existing_sb.h or 0.0) != scroll_h:
            updates["h"] = scroll_h
        if updates:
            fixed = existing_sb.model_copy(update=updates)
            new_elements = [fixed if e.id == existing_sb.id else e for e in new_elements]
            log.info(
                "Fixed scroll_bar '%s': %s", existing_sb.id,
                {k: v for k, v in updates.items()},
            )
    else:
        # Inject a brand-new white scroll bar, offset past the badge circle.
        # Badge occupies x=[0, _BADGE_WIDTH]; start the scroll bar after it.
        sb = ElementDef(
            id=_SCROLL_BAR_ID, type="rect",
            x=_BADGE_WIDTH, y=scroll_y,
            w=float(brand.canvas_w) - _BADGE_WIDTH, h=scroll_h,
            fill=_SCROLL_BAR_FILL, opacity=1.0,
        )
        new_elements.append(sb)
        log.info(
            "Injected white scroll_bar at x=%.0f y=%.0f w=%.0f h=%.0f",
            _BADGE_WIDTH, scroll_y, float(brand.canvas_w) - _BADGE_WIDTH, scroll_h,
        )

    # Ensure the upper half of the bar (above the scroll_bar) has a full-width
    # background rect. When the LLM only generates narrow label+accent elements
    # (e.g. 400px + 300px), the rest of the upper row is transparent and looks
    # disconnected from the full-width white scroll_bar below.
    upper_y = float(brand.bar_y)
    upper_h = float(brand.label_row_h)
    upper_w = float(brand.canvas_w) - _BADGE_WIDTH
    has_upper_bg = any(
        e.type == "rect"
        and e.id != _SCROLL_BAR_ID
        and e.y is not None
        and abs(float(e.y) - upper_y) <= 5
        for e in new_elements
    )
    if not has_upper_bg:
        upper_bg = ElementDef(
            id=_UPPER_BAR_ID, type="rect",
            x=_BADGE_WIDTH, y=upper_y,
            w=upper_w, h=upper_h,
            fill=brand.bar_color, opacity=1.0,
        )
        # Insert at position 0 so it paints behind everything else
        new_elements = [upper_bg] + new_elements
        log.info(
            "Injected upper_bar_bg at x=%.0f y=%.0f w=%.0f h=%.0f fill=%s",
            _BADGE_WIDTH, upper_y, upper_w, upper_h, brand.bar_color,
        )
    else:
        # A full-width rect covers the upper row — trim any full-height bar to
        # upper_h so the white scroll_bar renders cleanly in the lower half
        # without creating a visible white stripe through the coloured rect.
        for i, el in enumerate(new_elements):
            if (
                el.type == "rect"
                and el.id != _SCROLL_BAR_ID
                and el.y is not None
                and abs(float(el.y) - upper_y) <= 5
                and (el.w or 0) >= upper_w * 0.9
                and (el.h or 0) > upper_h + 5
            ):
                log.info(
                    "Trimmed '%s' h: %.0f → %.0f (upper half only, scroll_bar owns lower half)",
                    el.id, el.h, upper_h,
                )
                new_elements[i] = el.model_copy(update={"h": upper_h})

    # Wire every ticker element to the (now-guaranteed) scroll_bar.
    scroll_bar_top_y = scroll_y + brand.bar_padding_top  # text TOP within scroll_bar
    updated_ids = {_SCROLL_BAR_ID}  # already handled above
    for ticker_el in ticker_elements:
        t_updates: dict = {}
        if ticker_el.clip_to != _SCROLL_BAR_ID:
            t_updates["clip_to"] = _SCROLL_BAR_ID
            # When rewiring from a different clip region, y may be in the upper half.
            # Move it into the scroll_bar so the text is actually visible.
            if ticker_el.y < scroll_y:
                t_updates["y"] = scroll_bar_top_y
                log.info(
                    "Ticker '%s': y %.0f → %.0f (moved into scroll_bar)",
                    ticker_el.id, ticker_el.y, scroll_bar_top_y,
                )
        if ticker_el.fill and _is_light_color(ticker_el.fill):
            t_updates["fill"] = _TICKER_DARK_FILL
            log.info(
                "Ticker '%s': fill %s → %s (dark text on white bg)",
                ticker_el.id, ticker_el.fill, _TICKER_DARK_FILL,
            )
        if t_updates:
            updated = ticker_el.model_copy(update=t_updates)
            new_elements = [updated if e.id == ticker_el.id else e for e in new_elements]

    return ir.model_copy(update={"elements": new_elements})


def _fix_clip_target_dimensions(ir: MotionIR, brand: ResolvedBrand) -> MotionIR:
    """Ensure every rect used as a clip_to target has non-zero width and height.

    The LLM sometimes omits ``h`` (and occasionally ``w``) on label / accent
    rects.  When h is None the renderer sees a zero-height clip box and all
    text inside becomes invisible.  We patch the dimension to a sensible
    default derived from the brand geometry:
      • Full-width rects (w ≥ 90 % of canvas) → full bar height
      • Narrow rects (label, accent, …)        → upper half of the bar
    """
    clip_ids = {el.clip_to for el in ir.elements if el.clip_to}
    if not clip_ids:
        return ir

    half_h = float(brand.label_row_h)
    full_h = float(brand.bar_h)

    new_elements = list(ir.elements)
    for i, el in enumerate(new_elements):
        if el.id not in clip_ids or el.type != "rect":
            continue

        updates: dict = {}
        if not el.h:
            el_w = el.w or 0.0
            h = full_h if el_w >= brand.canvas_w * 0.9 else half_h
            updates["h"] = h
            log.info(
                "Clip target '%s': h was None/0, set to %.0f px (inferred from geometry)",
                el.id, h,
            )
        if not el.w:
            updates["w"] = float(brand.canvas_w)
            log.info(
                "Clip target '%s': w was None/0, set to %d px", el.id, brand.canvas_w,
            )

        if updates:
            new_elements[i] = el.model_copy(update=updates)

    return ir.model_copy(update={"elements": new_elements})


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
            from lower_third.renderer.text_measurer import measure_text_width
            estimated_w = measure_text_width(
                text=elem.content or "",
                font_family=getattr(elem, "font_family", "Noto Sans"),
                font_size=elem.font_size or 32,
                font_weight=getattr(elem, "font_weight", "regular"),
            )
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


def _fix_draw_order(ir: MotionIR) -> MotionIR:
    """Enforce correct draw order: rect → path → text.

    The LLM sometimes generates elements in the wrong order, e.g. scroll_bar
    (rect) after the badge (path), causing the white bar to paint over the badge.
    Sorting rect→path→text ensures:
      - Background rects (scroll_bar, label) render first
      - Badge circles (path) render next, sitting on top of rects
      - All text elements render last, so badge texts appear on top of the badge
        circle and ticker text appears on top of the white scroll bar
    """
    # rect → path → text: backgrounds paint first, then badge shapes, then all
    # text layers on top. This ensures badge texts (type=text) always render
    # after the badge circle (type=path), so LIVE/NEWS text is visible.
    type_order = {"rect": 0, "path": 1, "text": 2}
    original_order = {el.id: i for i, el in enumerate(ir.elements)}

    sorted_elements = sorted(
        ir.elements,
        key=lambda el: (type_order.get(el.type, 1), original_order[el.id]),
    )

    if [el.id for el in sorted_elements] != [el.id for el in ir.elements]:
        log.info(
            "Reordered elements for correct draw order: %s",
            [el.id for el in sorted_elements],
        )
        return ir.model_copy(update={"elements": sorted_elements})
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
