import pytest
from lower_third.motion.motion_ir import (
    MotionIR, ElementDef, AnimationTrack, Keyframe,
    EasingConfig, EasingType, LoopConfig
)
from lower_third.motion.interpolation_engine import InterpolationEngine, DrawState

def _bar():
    return ElementDef(id="bar", type="rect", x=0, y=960,
                      w=1920, h=60, fill="#1A1A2E", opacity=1.0)

def _text():
    return ElementDef(id="t1", type="text", content="Hello",
                      x=24, y=972, fill="#FFFFFF", font_size=32)

def _track(elem_id, prop, kfs, offset=0):
    return AnimationTrack(
        element_id=elem_id, property=prop,
        start_offset_ms=offset,
        keyframes=[
            Keyframe(t_ms=k[0], value=k[1],
                     easing=EasingConfig(type=EasingType(k[2])) if len(k) > 2
                     else EasingConfig())
            for k in kfs
        ]
    )

def _simple_ir(loop=None):
    track = _track("bar", "x", [(0, 0.0, "linear"), (1000, 100.0, "linear")])
    return MotionIR(elements=[_bar(), _text()], tracks=[track],
                    loop=loop or LoopConfig(), total_ms=1000)

def test_draw_state_has_all_keys():
    engine = InterpolationEngine(_simple_ir(), fps=30)
    state = engine.get_frame(0)
    assert isinstance(state, DrawState)
    required = {"id","type","content","repeat_content","clip_to","fill",
                "font_size","font_weight","x","y","w","h","opacity",
                "scale_x","scale_y","rotation","text_x_offset",
                "clip_x","clip_y","clip_w","clip_h"}
    for el in state.elements:
        assert required.issubset(set(el.keys()))

def test_linear_interpolation_midpoint():
    engine = InterpolationEngine(_simple_ir(), fps=30)
    bar = next(e for e in engine.get_frame(15).elements if e["id"] == "bar")
    assert abs(bar["x"] - 50.0) < 0.5

def test_before_first_keyframe_returns_first_value():
    track = _track("bar", "x", [(500, 99.0, "linear"), (1000, 200.0, "linear")])
    ir = MotionIR(elements=[_bar()], tracks=[track], total_ms=1000)
    bar = next(e for e in InterpolationEngine(ir).get_frame(0).elements if e["id"] == "bar")
    assert bar["x"] == 99.0

def test_after_last_keyframe_returns_last_value():
    bar = next(e for e in InterpolationEngine(_simple_ir()).get_frame(999).elements if e["id"] == "bar")
    assert bar["x"] == 100.0

def test_no_track_returns_element_default():
    ir = MotionIR(elements=[_bar()], tracks=[], total_ms=1000)
    bar = InterpolationEngine(ir).get_frame(15).elements[0]
    assert bar["y"] == 960.0

def test_start_offset_ms_delays_track():
    track = _track("bar", "x", [(0, 0.0, "linear"), (1000, 100.0, "linear")], offset=500)
    ir = MotionIR(elements=[_bar()], tracks=[track], total_ms=2000)
    bar = InterpolationEngine(ir).get_frame(7).elements[0]
    assert bar["x"] == 0.0

def test_loop_restart():
    loop = LoopConfig(enabled=True, count=0, type="restart", loop_after_ms=1000)
    engine = InterpolationEngine(_simple_ir(loop=loop), fps=30)
    bar_0  = next(e for e in engine.get_frame(0).elements  if e["id"] == "bar")
    bar_30 = next(e for e in engine.get_frame(30).elements if e["id"] == "bar")
    assert abs(bar_0["x"] - bar_30["x"]) < 0.5

def test_loop_ping_pong():
    loop = LoopConfig(enabled=True, count=0, type="ping_pong", loop_after_ms=1000)
    engine = InterpolationEngine(_simple_ir(loop=loop), fps=30)
    f15 = next(e for e in engine.get_frame(15).elements if e["id"] == "bar")
    f45 = next(e for e in engine.get_frame(45).elements if e["id"] == "bar")
    assert abs(f15["x"] - f45["x"]) < 2.0

def test_ease_out_cubic_at_midpoint():
    track = _track("bar", "opacity", [(0, 0.0, "ease_out_cubic"), (1000, 1.0, "ease_out_cubic")])
    ir = MotionIR(elements=[_bar()], tracks=[track], total_ms=1000)
    bar = InterpolationEngine(ir).get_frame(15).elements[0]
    assert abs(bar["opacity"] - 0.875) < 0.01

def test_spring_easing_overshoots():
    track = AnimationTrack(
        element_id="bar", property="x",
        keyframes=[
            Keyframe(t_ms=0, value=0.0,
                     easing=EasingConfig(type=EasingType.spring,
                                         spring_stiffness=300, spring_damping=8, spring_mass=1.0)),
            Keyframe(t_ms=1000, value=100.0)
        ]
    )
    ir = MotionIR(elements=[_bar()], tracks=[track], total_ms=2000)
    engine = InterpolationEngine(ir, fps=30)
    values = [next(e for e in engine.get_frame(i).elements if e["id"] == "bar")["x"] for i in range(30)]
    assert max(values) > 100.0

def test_step_easing():
    track = _track("bar", "opacity", [(0, 0.0, "step"), (1000, 1.0, "step")])
    ir = MotionIR(elements=[_bar()], tracks=[track], total_ms=1000)
    engine = InterpolationEngine(ir, fps=30)
    assert engine.get_frame(12).elements[0]["opacity"] == 0.0
    assert engine.get_frame(18).elements[0]["opacity"] == 1.0

def test_text_x_offset_defaults_to_zero():
    ir = MotionIR(elements=[_text()], tracks=[], total_ms=1000)
    assert InterpolationEngine(ir).get_frame(0).elements[0]["text_x_offset"] == 0.0

def test_total_frames_computed_correctly():
    ir = MotionIR(elements=[_bar()], tracks=[], total_ms=2000)
    assert InterpolationEngine(ir, fps=30).total_frames == 60

def test_out_of_bounds_frame_clamped():
    ir = MotionIR(elements=[_bar()], tracks=[], total_ms=1000)
    assert InterpolationEngine(ir).get_frame(99999) is not None

def test_element_order_preserved():
    ir = MotionIR(elements=[_bar(), _text()], tracks=[], total_ms=1000)
    state = InterpolationEngine(ir).get_frame(0)
    assert state.elements[0]["id"] == "bar"
    assert state.elements[1]["id"] == "t1"
