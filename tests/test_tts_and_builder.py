import pytest
from lower_third.motion.motion_ir import (
    MotionIR, ElementDef, AnimationTrack, Keyframe,
    EasingConfig, EasingType, LoopConfig
)
from lower_third.choreography.brand_resolver import resolve_brand, ResolvedBrand
from lower_third.choreography.tts_anchor import anchor_tracks_to_tts, build_element_words
from lower_third.motion.ir_builder import build_simple_bar_ir


def _brand() -> ResolvedBrand:
    return resolve_brand({}, estimated_lines=2)


def _text_elem(elem_id, content):
    return ElementDef(
        id=elem_id, type="text", content=content,
        x=24, y=972, fill="#FFFFFF", font_size=32, clip_to="bar"
    )


def _bar_elem():
    return ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")


def _y_track(elem_id, offset=0):
    return AnimationTrack(
        element_id=elem_id, property="y",
        start_offset_ms=offset,
        keyframes=[Keyframe(t_ms=0, value=980.0), Keyframe(t_ms=400, value=930.0)]
    )


def _opacity_track(elem_id, offset=0):
    return AnimationTrack(
        element_id=elem_id, property="opacity",
        start_offset_ms=offset,
        keyframes=[Keyframe(t_ms=0, value=0.0), Keyframe(t_ms=400, value=1.0)]
    )


def _ir_with_tracks(*tracks):
    elems = [_bar_elem(),
             _text_elem("h1", "Iran blocks Hormuz"),
             _text_elem("h2", "Oil prices rise")]
    total = max(t.start_offset_ms + t.keyframes[-1].t_ms for t in tracks) if tracks else 1000
    return MotionIR(elements=elems, tracks=list(tracks), total_ms=total)


# ── TTS anchor ────────────────────────────────────────────────────────────────

def test_empty_timestamps_returns_ir_unchanged():
    ir = _ir_with_tracks(_y_track("h1"), _y_track("h2", 5800))
    original_total = ir.total_ms
    result = anchor_tracks_to_tts(ir, {}, {"h1": "Iran", "h2": "Oil"})
    assert result.total_ms == original_total
    assert result.tracks[0].start_offset_ms == 0


def test_anchor_updates_y_track_start_offset():
    ir = _ir_with_tracks(_y_track("h1", 0))
    result = anchor_tracks_to_tts(ir, {"Iran": 3200}, {"h1": "Iran"})
    h1_track = next(t for t in result.tracks if t.element_id == "h1")
    assert h1_track.start_offset_ms == 3200


def test_anchor_prefers_y_track_over_opacity():
    ir = _ir_with_tracks(_y_track("h1", 0), _opacity_track("h1", 0))
    result = anchor_tracks_to_tts(ir, {"Iran": 1500}, {"h1": "Iran"})
    y_track = next(t for t in result.tracks
                   if t.element_id == "h1" and t.property == "y")
    op_track = next(t for t in result.tracks
                    if t.element_id == "h1" and t.property == "opacity")
    assert y_track.start_offset_ms == 1500
    assert op_track.start_offset_ms == 0    # opacity track unchanged


def test_anchor_falls_back_to_opacity_when_no_y_track():
    ir = _ir_with_tracks(_opacity_track("h1", 0))
    result = anchor_tracks_to_tts(ir, {"Iran": 2800}, {"h1": "Iran"})
    op_track = next(t for t in result.tracks
                    if t.element_id == "h1" and t.property == "opacity")
    assert op_track.start_offset_ms == 2800


def test_anchor_skips_element_with_no_matching_track():
    ir = _ir_with_tracks(_y_track("h1", 0))
    result = anchor_tracks_to_tts(ir, {"Oil": 5000}, {"h2": "Oil"})
    # h2 has no track — should not raise, h1 track unchanged
    h1_track = next(t for t in result.tracks if t.element_id == "h1")
    assert h1_track.start_offset_ms == 0


def test_anchor_skips_word_not_in_timestamps():
    ir = _ir_with_tracks(_y_track("h1", 0))
    result = anchor_tracks_to_tts(ir, {"UnrelatedWord": 1000}, {"h1": "Iran"})
    h1_track = next(t for t in result.tracks if t.element_id == "h1")
    assert h1_track.start_offset_ms == 0


def test_anchor_recomputes_total_ms():
    ir = _ir_with_tracks(_y_track("h1", 0))
    # track: start=0, last keyframe t_ms=400 → end=400
    # after anchor: start=9000, last keyframe t_ms=400 → end=9400
    result = anchor_tracks_to_tts(ir, {"Iran": 9000}, {"h1": "Iran"})
    assert result.total_ms == 9400


def test_anchor_total_ms_unchanged_when_no_tracks():
    elems = [_bar_elem(), _text_elem("h1", "Iran blocks Hormuz")]
    ir = MotionIR(elements=elems, tracks=[], total_ms=5000)
    result = anchor_tracks_to_tts(ir, {"Iran": 1000}, {"h1": "Iran"})
    assert result.total_ms == 5000


def test_anchor_multiple_elements():
    ir = _ir_with_tracks(_y_track("h1", 0), _y_track("h2", 0))
    result = anchor_tracks_to_tts(
        ir,
        {"Iran": 2000, "Oil": 8000},
        {"h1": "Iran", "h2": "Oil"}
    )
    h1 = next(t for t in result.tracks if t.element_id == "h1")
    h2 = next(t for t in result.tracks if t.element_id == "h2")
    assert h1.start_offset_ms == 2000
    assert h2.start_offset_ms == 8000


def test_build_element_words_extracts_first_words():
    elems = [_bar_elem(),
             _text_elem("h1", "Iran blocks Hormuz"),
             _text_elem("h2", "Oil prices rise")]
    ir = MotionIR(elements=elems, tracks=[], total_ms=1000)
    result = build_element_words(ir)
    assert result == {"h1": "Iran", "h2": "Oil"}


def test_build_element_words_ignores_rect_elements():
    elems = [_bar_elem(), _text_elem("h1", "Hello world")]
    ir = MotionIR(elements=elems, tracks=[], total_ms=1000)
    result = build_element_words(ir)
    assert "bar" not in result


def test_build_element_words_ignores_empty_content():
    elem = ElementDef(id="t1", type="text", content="",
                      x=0, y=0, fill="#FFFFFF", font_size=32)
    ir = MotionIR(elements=[_bar_elem(), elem], tracks=[], total_ms=1000)
    result = build_element_words(ir)
    assert "t1" not in result


# ── IR builder ────────────────────────────────────────────────────────────────

def test_build_simple_bar_ir_returns_motion_ir():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
    assert isinstance(ir, MotionIR)


def test_build_simple_bar_ir_has_bar_element():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
    bar = next((e for e in ir.elements if e.id == "bar"), None)
    assert bar is not None
    assert bar.type == "rect"


def test_build_simple_bar_ir_bar_uses_brand_geometry():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
    bar = next(e for e in ir.elements if e.id == "bar")
    assert bar.y == brand.bar_y
    assert bar.h == brand.bar_h
    assert bar.fill == brand.bar_color


def test_build_simple_bar_ir_text_element_count():
    brand = _brand()
    lines = [
        {"text": "BREAKING", "role": "kicker"},
        {"text": "Dr. Jane Smith", "role": "name"},
        {"text": "WHO Director", "role": "title"},
    ]
    ir = build_simple_bar_ir(brand, lines)
    text_elems = [e for e in ir.elements if e.type == "text"]
    assert len(text_elems) == 3


def test_build_simple_bar_ir_text_clipped_to_bar():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
    text = next(e for e in ir.elements if e.type == "text")
    assert text.clip_to == "bar"


def test_build_simple_bar_ir_font_size_by_role():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [
        {"text": "LIVE", "role": "kicker"},
        {"text": "Name Here", "role": "name"},
    ])
    kicker = next(e for e in ir.elements if e.id == "line_0")
    name   = next(e for e in ir.elements if e.id == "line_1")
    assert kicker.font_size == brand.font_size_kicker
    assert name.font_size   == brand.font_size_name


def test_build_simple_bar_ir_bold_roles():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [
        {"text": "LIVE", "role": "kicker"},
        {"text": "Dr. Smith", "role": "name"},
        {"text": "Director", "role": "title"},
    ])
    kicker = next(e for e in ir.elements if e.id == "line_0")
    name   = next(e for e in ir.elements if e.id == "line_1")
    title  = next(e for e in ir.elements if e.id == "line_2")
    assert kicker.font_weight == "bold"
    assert name.font_weight   == "bold"
    assert title.font_weight  == "regular"


def test_build_simple_bar_ir_has_y_tracks():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [
        {"text": "Line 1", "role": "headline"},
        {"text": "Line 2", "role": "headline"},
    ])
    y_tracks = [t for t in ir.tracks if t.property == "y"]
    assert len(y_tracks) == 2


def test_build_simple_bar_ir_track_stagger():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [
        {"text": "A", "role": "headline"},
        {"text": "B", "role": "headline"},
    ])
    t0 = next(t for t in ir.tracks if t.element_id == "line_0")
    t1 = next(t for t in ir.tracks if t.element_id == "line_1")
    assert t0.start_offset_ms == 0
    assert t1.start_offset_ms == 300


def test_build_simple_bar_ir_loop_false_by_default():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
    assert ir.loop.enabled is False


def test_build_simple_bar_ir_loop_enabled():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}], loop=True)
    assert ir.loop.enabled is True


def test_build_simple_bar_ir_total_ms():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}],
                              duration_ms=12000)
    assert ir.total_ms == 12000


def test_build_simple_bar_ir_slide_entry_keyframes():
    brand = _brand()
    ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
    track = next(t for t in ir.tracks if t.element_id == "line_0")
    assert len(track.keyframes) == 2
    assert track.keyframes[0].value == brand.bar_y + brand.bar_h
    assert track.keyframes[1].t_ms  == 400
