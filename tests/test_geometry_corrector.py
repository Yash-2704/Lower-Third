import pytest
from lower_third.motion.motion_ir import (
    MotionIR, ElementDef, AnimationTrack, Keyframe,
    EasingConfig, EasingType, LoopConfig
)
from lower_third.choreography.brand_resolver import resolve_brand
from lower_third.motion.geometry_corrector import (
    apply_geometric_corrections,
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
