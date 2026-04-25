import pytest
from lower_third.motion.motion_ir import (
    MotionIR, ElementDef, AnimationTrack, Keyframe,
    EasingConfig, EasingType, LoopConfig, ShapeIntent, ShapeKind,
)
from lower_third.choreography.brand_resolver import resolve_brand
from lower_third.motion.geometry_corrector import (
    apply_geometric_corrections,
    _fix_circle_badge_position,
    _fix_clip_boundaries,
    _fix_timing_consistency,
    _fix_track_uniqueness,
)


def _brand():
    return resolve_brand({}, estimated_lines=1)


def _bar(bar_y=960, bar_h=60):
    return ElementDef(
        id="bar", type="rect",
        x=0, y=bar_y, w=1920, h=bar_h, fill="#1A1A2E"
    )


def _text(y=960, clip_to="bar", content="Iran blocks Strait of Hormuz"):
    return ElementDef(
        id="t1", type="text", content=content,
        x=24, y=y, fill="#FFFFFF", font_size=32,
        clip_to=clip_to
    )


def _y_track(elem_id="t1", keyframes=None, offset=0):
    kfs = keyframes or [
        Keyframe(t_ms=0, value=1025.0),
        Keyframe(t_ms=400, value=972.0)
    ]
    return AnimationTrack(
        element_id=elem_id, property="y",
        start_offset_ms=offset, keyframes=kfs
    )


# ── Clip boundary corrections ─────────────────────────────────────────────────

def test_exit_above_keyframe_corrected():
    # bar_y=960, font_size=32
    # exit keyframe at y=940 — only 20px above bar, not enough
    # should be corrected to at least 960 - (32*1.5) - 60 = 852
    brand = _brand()
    bar = _bar()
    text = _text(y=972)
    track = _y_track(keyframes=[
        Keyframe(t_ms=0, value=1025.0),
        Keyframe(t_ms=400, value=972.0),
        Keyframe(t_ms=5400, value=972.0),
        Keyframe(t_ms=5800, value=940.0),   # too close to bar_y=960
    ])
    ir = MotionIR(elements=[bar, text], tracks=[track], total_ms=5800)
    corrected = _fix_clip_boundaries(ir, brand)
    exit_kf = next(t for t in corrected.tracks if t.element_id == "t1").keyframes[-1]
    assert exit_kf.value <= 960 - (32 * 1.5) - 60


def test_entry_below_keyframe_corrected():
    # Entry starts at bar_y + bar_h + 5 = 1025 — too close
    # Should be corrected to at least 960 + 60 + 60 = 1080
    brand = _brand()
    bar = _bar()
    text = _text()
    track = _y_track(keyframes=[
        Keyframe(t_ms=0, value=1025.0),   # only 5px below bar bottom
        Keyframe(t_ms=400, value=972.0),
    ])
    ir = MotionIR(elements=[bar, text], tracks=[track], total_ms=1000)
    corrected = _fix_clip_boundaries(ir, brand)
    entry_kf = next(t for t in corrected.tracks if t.element_id == "t1").keyframes[0]
    assert entry_kf.value >= 960 + 60 + 60


def test_correct_keyframes_not_modified():
    # Already correct: entry=1100 (well below), exit=800 (well above)
    brand = _brand()
    bar = _bar()
    text = _text()
    track = _y_track(keyframes=[
        Keyframe(t_ms=0, value=1100.0),
        Keyframe(t_ms=400, value=972.0),
        Keyframe(t_ms=5400, value=972.0),
        Keyframe(t_ms=5800, value=800.0),
    ])
    ir = MotionIR(elements=[bar, text], tracks=[track], total_ms=5800)
    corrected = _fix_clip_boundaries(ir, brand)
    kfs = next(t for t in corrected.tracks if t.element_id == "t1").keyframes
    assert kfs[0].value == 1100.0   # unchanged
    assert kfs[-1].value == 800.0   # unchanged


def test_element_without_clip_to_not_modified():
    brand = _brand()
    bar = _bar()
    text = ElementDef(
        id="t1", type="text", content="Test",
        x=24, y=972, fill="#FFFFFF", font_size=32,
        clip_to=None   # no clip
    )
    track = _y_track(keyframes=[
        Keyframe(t_ms=0, value=1025.0),
        Keyframe(t_ms=400, value=972.0),
    ])
    ir = MotionIR(elements=[bar, text], tracks=[track], total_ms=1000)
    corrected = _fix_clip_boundaries(ir, brand)
    kfs = next(t for t in corrected.tracks).keyframes
    assert kfs[0].value == 1025.0   # unchanged — no clip, no correction


# ── Timing consistency ────────────────────────────────────────────────────────

def test_total_ms_extended_when_track_exceeds_it():
    brand = _brand()
    bar = _bar()
    text = _text()
    # Track ends at 0 + 2000 = 2000ms but total_ms is only 1000
    track = _y_track(keyframes=[
        Keyframe(t_ms=0, value=1025.0),
        Keyframe(t_ms=2000, value=972.0),
    ])
    ir = MotionIR(elements=[bar, text], tracks=[track], total_ms=1000)
    corrected = _fix_timing_consistency(ir)
    assert corrected.total_ms == 2000


def test_total_ms_not_reduced_when_already_long_enough():
    brand = _brand()
    bar = _bar()
    text = _text()
    track = _y_track(keyframes=[
        Keyframe(t_ms=0, value=1025.0),
        Keyframe(t_ms=400, value=972.0),
    ])
    ir = MotionIR(elements=[bar, text], tracks=[track], total_ms=5000)
    corrected = _fix_timing_consistency(ir)
    assert corrected.total_ms == 5000   # kept as-is — longer is fine


def test_loop_after_ms_set_when_none():
    # loop_after_ms=None → should be set to true_end_ms (400), not total_ms (5800)
    bar = _bar()
    text = _text()
    track = _y_track()  # ends at t_ms=400, offset=0 → true_end_ms=400
    ir = MotionIR(
        elements=[bar, text], tracks=[track],
        loop=LoopConfig(enabled=True, count=0, loop_after_ms=None),
        total_ms=5800
    )
    corrected = _fix_timing_consistency(ir)
    assert corrected.loop.loop_after_ms == 400


def test_total_ms_not_trimmed_when_loop_after_ms_smaller():
    # loop_after_ms=400 < total_ms=5800 → total_ms must NOT be trimmed;
    # the engine uses frame_index % loop_frames to loop within the full duration.
    bar = _bar()
    text = _text()
    track = _y_track()
    ir = MotionIR(
        elements=[bar, text], tracks=[track],
        loop=LoopConfig(enabled=True, count=0, loop_after_ms=400),
        total_ms=5800
    )
    corrected = _fix_timing_consistency(ir)
    assert corrected.total_ms == 5800
    assert corrected.loop.loop_after_ms == 400


def test_staggered_tracks_total_ms_computed_correctly():
    bar = _bar()
    t1 = _text()
    t2 = ElementDef(id="t2", type="text", content="Oil",
                    x=24, y=972, fill="#FFFFFF", font_size=32, clip_to="bar")
    track1 = _y_track("t1", offset=0,    keyframes=[Keyframe(t_ms=0, value=1025), Keyframe(t_ms=400, value=972)])
    track2 = _y_track("t2", offset=5800, keyframes=[Keyframe(t_ms=0, value=1025), Keyframe(t_ms=400, value=972)])
    # track2 ends at 5800 + 400 = 6200ms
    ir = MotionIR(elements=[bar, t1, t2], tracks=[track1, track2], total_ms=1000)
    corrected = _fix_timing_consistency(ir)
    assert corrected.total_ms == 6200


# ── Track uniqueness ──────────────────────────────────────────────────────────

def test_duplicate_tracks_merged():
    bar = _bar()
    text = _text()
    track1 = AnimationTrack(
        element_id="t1", property="y", start_offset_ms=0,
        keyframes=[Keyframe(t_ms=0, value=1025), Keyframe(t_ms=400, value=972)]
    )
    track2 = AnimationTrack(
        element_id="t1", property="y", start_offset_ms=5800,
        keyframes=[Keyframe(t_ms=0, value=972), Keyframe(t_ms=400, value=800)]
    )
    # Cannot construct MotionIR with duplicates due to validator
    # Test _fix_track_uniqueness directly by bypassing model construction
    from lower_third.motion.geometry_corrector import _fix_track_uniqueness

    ir_mock = MotionIR.__new__(MotionIR)
    object.__setattr__(ir_mock, "elements", [bar, text])
    object.__setattr__(ir_mock, "tracks", [track1, track2])
    object.__setattr__(ir_mock, "loop", LoopConfig())
    object.__setattr__(ir_mock, "total_ms", 6200)
    object.__setattr__(ir_mock, "groups", [])
    object.__setattr__(ir_mock, "__pydantic_fields_set__", set())
    object.__setattr__(ir_mock, "__pydantic_extra__", None)
    object.__setattr__(ir_mock, "__pydantic_private__", None)

    corrected = _fix_track_uniqueness(ir_mock)
    y_tracks = [t for t in corrected.tracks
                if t.element_id == "t1" and t.property == "y"]
    assert len(y_tracks) == 1


def test_non_duplicate_tracks_preserved():
    bar = _bar()
    text = _text()
    y_track  = _y_track("t1", keyframes=[Keyframe(t_ms=0, value=1025), Keyframe(t_ms=400, value=972)])
    op_track = AnimationTrack(
        element_id="t1", property="opacity", start_offset_ms=0,
        keyframes=[Keyframe(t_ms=0, value=0.0), Keyframe(t_ms=400, value=1.0)]
    )
    ir = MotionIR(elements=[bar, text], tracks=[y_track, op_track], total_ms=1000)
    corrected = _fix_track_uniqueness(ir)
    assert len(corrected.tracks) == 2


# ── Full pipeline correction ──────────────────────────────────────────────────

def test_apply_geometric_corrections_returns_motion_ir():
    brand = _brand()
    bar = _bar()
    text = _text()
    track = _y_track()
    ir = MotionIR(elements=[bar, text], tracks=[track], total_ms=1000)
    result = apply_geometric_corrections(ir, brand)
    assert isinstance(result, MotionIR)


def test_apply_geometric_corrections_does_not_raise_on_empty_tracks():
    brand = _brand()
    bar = _bar()
    ir = MotionIR(elements=[bar], tracks=[], total_ms=1000)
    result = apply_geometric_corrections(ir, brand)
    assert isinstance(result, MotionIR)


def test_x_branch_uses_proportional_width():
    """Verify CHARS_TO_PX_RATIO flat estimate is gone: WWW and iii produce different estimated_w."""
    try:
        import cairocffi  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("cairocffi not installed")

    brand = _brand()
    bar = _bar()

    wide_text = ElementDef(
        id="tw", type="text", content="WWWWWWWWWW",
        x=24, y=960, fill="#FFFFFF", font_size=32, clip_to="bar"
    )
    narrow_text = ElementDef(
        id="tn", type="text", content="iiiiiiiiii",
        x=24, y=960, fill="#FFFFFF", font_size=32, clip_to="bar"
    )

    def _x_track(elem_id: str) -> AnimationTrack:
        return AnimationTrack(
            element_id=elem_id, property="x",
            keyframes=[
                Keyframe(t_ms=0, value=-5.0),
                Keyframe(t_ms=400, value=24.0),
            ]
        )

    ir_wide = MotionIR(elements=[bar, wide_text], tracks=[_x_track("tw")], total_ms=1000)
    ir_narrow = MotionIR(elements=[bar, narrow_text], tracks=[_x_track("tn")], total_ms=1000)

    result_wide = _fix_clip_boundaries(ir_wide, brand)
    result_narrow = _fix_clip_boundaries(ir_narrow, brand)

    wide_kf0_v = result_wide.tracks[0].keyframes[0].value
    narrow_kf0_v = result_narrow.tracks[0].keyframes[0].value

    assert wide_kf0_v != narrow_kf0_v, (
        "CHARS_TO_PX_RATIO flat ratio is still in use — WWW and iii produced same estimated_w"
    )


def test_motion_ir_rejects_duplicate_tracks():
    bar = _bar()
    text = _text()
    track1 = AnimationTrack(
        element_id="t1", property="y", start_offset_ms=0,
        keyframes=[Keyframe(t_ms=0, value=1025), Keyframe(t_ms=400, value=972)]
    )
    track2 = AnimationTrack(
        element_id="t1", property="y", start_offset_ms=5800,
        keyframes=[Keyframe(t_ms=0, value=972), Keyframe(t_ms=400, value=800)]
    )
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="Duplicate track"):
        MotionIR(elements=[bar, text], tracks=[track1, track2], total_ms=6200)


# ── Circle badge position corrections ────────────────────────────────────────
# _brand() gives: bar_y=944, bar_h=136, canvas_h=1080, canvas_w=1920
# expected_cy = 944 + (1080 - 944) // 2 = 1012
# max_cy      = 1080 - 60 - 2 = 1018  → corrected_cy = min(1012, 1018) = 1012


def _circle_path(cx=500.0, cy=1010.0, rx=60.0, ry=60.0, kind=ShapeKind.circle):
    return ElementDef(
        id="badge", type="path",
        shape_intent=ShapeIntent(kind=kind, cx=cx, cy=cy, rx=rx, ry=ry),
        fill="#1A3A8F",
    )


def _ir_with(*elements, tracks=None):
    return MotionIR(
        elements=list(elements),
        tracks=tracks or [],
        total_ms=1000,
    )


def test_circle_badge_cy_corrected_when_too_low():
    brand = _brand()
    badge = _circle_path(cy=1079.0, rx=60.0, ry=60.0)
    ir = _ir_with(badge)
    result = _fix_circle_badge_position(ir, brand)
    badge_out = next(e for e in result.elements if e.id == "badge")
    assert badge_out.shape_intent is not None
    corrected_cy = badge_out.shape_intent.cy
    corrected_ry = badge_out.shape_intent.ry
    assert corrected_cy < 1079.0
    assert corrected_cy + corrected_ry <= brand.canvas_h - 2
    assert badge_out.d is None


def test_circle_badge_cx_corrected_to_flush_left():
    brand = _brand()
    badge = _circle_path(cx=500.0)
    ir = _ir_with(badge)
    result = _fix_circle_badge_position(ir, brand)
    badge_out = next(e for e in result.elements if e.id == "badge")
    assert badge_out.shape_intent.cx == 60.0


def test_circle_badge_rx_ry_enforced():
    brand = _brand()
    badge = _circle_path(rx=30.0, ry=30.0)
    ir = _ir_with(badge)
    result = _fix_circle_badge_position(ir, brand)
    badge_out = next(e for e in result.elements if e.id == "badge")
    assert badge_out.shape_intent.rx == 60.0
    assert badge_out.shape_intent.ry == 60.0
    assert badge_out.d is None


def test_non_circle_path_unchanged():
    brand = _brand()
    chevron = ElementDef(
        id="chev", type="path",
        shape_intent=ShapeIntent(kind=ShapeKind.chevron, cx=200.0, cy=990.0, rx=50.0, ry=30.0),
        fill="#CC0000",
    )
    ir = _ir_with(chevron)
    result = _fix_circle_badge_position(ir, brand)
    chev_out = next(e for e in result.elements if e.id == "chev")
    assert chev_out.shape_intent.cx == 200.0
    assert chev_out.shape_intent.cy == 990.0
    assert chev_out.shape_intent.rx == 50.0
    assert chev_out.shape_intent.ry == 30.0


def test_no_path_elements_returns_ir_unchanged():
    brand = _brand()
    bar = _bar()
    text = _text()
    ir = _ir_with(bar, text)
    result = _fix_circle_badge_position(ir, brand)
    assert result is not ir  # model_copy always returns new object
    assert [e.id for e in result.elements] == [e.id for e in ir.elements]


# ── Separator line tests ──────────────────────────────────────────────────────

from lower_third.motion.geometry_corrector import _ensure_separator_line


def test_ensure_separator_line_adds_rect():
    brand = _brand()
    bar = _bar()
    ir = _ir_with(bar)
    result = _ensure_separator_line(ir, brand)
    separator = next((e for e in result.elements if e.id == "separator"), None)
    assert separator is not None
    assert separator.type == "rect"
    assert separator.y == brand.bar_y_ticker
    assert separator.h == 2
    assert separator.w == brand.canvas_w


def test_ensure_separator_line_idempotent():
    brand = _brand()
    bar = _bar()
    ir = _ir_with(bar)
    result1 = _ensure_separator_line(ir, brand)
    result2 = _ensure_separator_line(result1, brand)
    separators = [e for e in result2.elements if e.id == "separator"]
    assert len(separators) == 1


def test_ensure_separator_line_dark_fill():
    brand = _brand()
    bar = _bar()
    ir = _ir_with(bar)
    result = _ensure_separator_line(ir, brand)
    separator = next(e for e in result.elements if e.id == "separator")
    r = int(separator.fill[1:3], 16)
    g = int(separator.fill[3:5], 16)
    b = int(separator.fill[5:7], 16)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    assert luminance < 128, f"Separator fill {separator.fill!r} is too light (luminance={luminance:.1f})"


# ── Badge text position tests ────────────────────────────────────────────────

from lower_third.motion.geometry_corrector import (
    _fix_badge_text_position,
    _fix_label_text_position,
)


def _badge_text(id, y, font_size=16, content="LIVE"):
    return ElementDef(
        id=id, type="text", content=content,
        x=0, y=y, font_size=font_size, fill="#FFFFFF",
    )


def test_badge_text_line1_y_corrected():
    brand = _brand()
    line1 = _badge_text("badge_line1", y=1070, font_size=16, content="LIVE")
    line2 = _badge_text("badge_line2", y=1080, font_size=16, content="NEWS")
    ir = _ir_with(line1, line2)
    result = _fix_badge_text_position(ir, brand)
    out1 = next(e for e in result.elements if e.id == "badge_line1")
    assert out1.y == brand.circle_cy - 16


def test_badge_text_line2_y_corrected():
    brand = _brand()
    line1 = _badge_text("badge_line1", y=1070, font_size=16, content="LIVE")
    line2 = _badge_text("badge_line2", y=1080, font_size=16, content="NEWS")
    ir = _ir_with(line1, line2)
    result = _fix_badge_text_position(ir, brand)
    out2 = next(e for e in result.elements if e.id == "badge_line2")
    assert out2.y == brand.circle_cy + 4


def test_badge_text_text_align_enforced():
    brand = _brand()
    line1 = _badge_text("badge_line1", y=1070, content="LIVE")
    line2 = _badge_text("badge_line2", y=1080, content="NEWS")
    ir = _ir_with(line1, line2)
    result = _fix_badge_text_position(ir, brand)
    for el in result.elements:
        if "badge" in el.id:
            assert el.text_align == "center"


def test_badge_text_w_enforced():
    brand = _brand()
    line1 = _badge_text("badge_line1", y=1070, content="LIVE")
    line2 = _badge_text("badge_line2", y=1080, content="NEWS")
    ir = _ir_with(line1, line2)
    result = _fix_badge_text_position(ir, brand)
    for el in result.elements:
        if "badge" in el.id:
            assert el.w == brand.circle_rx * 2


def test_badge_text_wrong_count_returns_unchanged():
    brand = _brand()
    only = _badge_text("badge_line1", y=1070, content="LIVE")
    ir = _ir_with(only)
    result = _fix_badge_text_position(ir, brand)
    out = next(e for e in result.elements if e.id == "badge_line1")
    assert out.y == 1070


# ── Label text vertical centering tests ──────────────────────────────────────


def test_label_text_y_centred_in_label_row():
    brand = _brand()
    label = ElementDef(
        id="label_text", type="text", content="BREAKING NEWS",
        x=140, y=brand.bar_y, font_size=28, fill="#FFFFFF",
    )
    ir = _ir_with(label)
    result = _fix_label_text_position(ir, brand)
    out = next(e for e in result.elements if e.id == "label_text")
    expected = brand.bar_y + brand.label_row_h // 2 - int(28 * 0.56) - 8
    assert out.y == expected


def test_label_text_x_enforced_with_left_padding():
    brand = _brand()
    # x=50 sits inside the badge column — corrector must push it right
    # to circle_cx + circle_rx + LABEL_TEXT_LEFT_PADDING = 60 + 60 + 16 = 136.
    label = ElementDef(
        id="label_text", type="text", content="BREAKING NEWS",
        x=50, y=brand.bar_y, font_size=28, fill="#FFFFFF",
    )
    ir = _ir_with(label)
    result = _fix_label_text_position(ir, brand)
    out = next(e for e in result.elements if e.id == "label_text")
    expected_x = brand.circle_cx + brand.circle_rx + 16
    assert out.x == expected_x
    assert out.x == 136


def test_badge_text_not_treated_as_label():
    brand = _brand()
    badge = ElementDef(
        id="badge_line1", type="text", content="LIVE",
        x=0, y=brand.bar_y + 5, font_size=16, fill="#FFFFFF",
    )
    ir = _ir_with(badge)
    result = _fix_label_text_position(ir, brand)
    out = next(e for e in result.elements if e.id == "badge_line1")
    assert out.y == brand.bar_y + 5


def test_ticker_text_not_treated_as_label():
    brand = _brand()
    ticker = ElementDef(
        id="ticker", type="text", content="news ticker",
        x=140, y=brand.bar_y + 10, font_size=28, fill="#1A1A3A",
        repeat_content=True,
    )
    ir = _ir_with(ticker)
    result = _fix_label_text_position(ir, brand)
    out = next(e for e in result.elements if e.id == "ticker")
    assert out.y == brand.bar_y + 10
