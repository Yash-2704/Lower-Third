import pytest
from lower_third.motion.motion_ir import (
    MotionIR, ElementDef, AnimationTrack, Keyframe,
    EasingConfig, EasingType, LoopConfig
)
from lower_third.parser.prompt_schema import LowerThirdSpec, ContentMode
from pydantic import ValidationError


def _bar():
    return ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")


def _text():
    return ElementDef(id="t1", type="text", content="Hello", x=24, y=972, fill="#FFFFFF", font_size=32)


def _track(elem_id="bar", prop="x"):
    return AnimationTrack(
        element_id=elem_id,
        property=prop,
        keyframes=[Keyframe(t_ms=0, value=0.0), Keyframe(t_ms=1000, value=100.0)]
    )


def test_valid_motion_ir_constructs():
    ir = MotionIR(elements=[_bar()], tracks=[], total_ms=5000)
    assert ir.total_ms == 5000


def test_unknown_track_element_raises():
    with pytest.raises(ValidationError, match="unknown element_id"):
        MotionIR(elements=[_bar()], tracks=[_track("nonexistent")], total_ms=1000)


def test_unknown_clip_to_raises():
    elem = ElementDef(id="t1", type="text", content="x", x=0, y=0,
                      fill="#FFFFFF", font_size=32, clip_to="nonexistent")
    with pytest.raises(ValidationError, match="unknown element_id"):
        MotionIR(elements=[_bar(), elem], tracks=[], total_ms=1000)


def test_valid_clip_to_passes():
    elem = ElementDef(id="t1", type="text", content="x", x=0, y=0,
                      fill="#FFFFFF", font_size=32, clip_to="bar")
    ir = MotionIR(elements=[_bar(), elem], tracks=[], total_ms=1000)
    assert ir.elements[1].clip_to == "bar"


def test_total_ms_zero_raises():
    with pytest.raises(ValidationError):
        MotionIR(elements=[_bar()], tracks=[], total_ms=0)


def test_empty_elements_raises():
    with pytest.raises(ValidationError):
        MotionIR(elements=[], tracks=[], total_ms=1000)


def test_invalid_hex_fill_raises():
    with pytest.raises(ValidationError):
        ElementDef(id="bar", type="rect", fill="red")


def test_valid_hex_fill_passes():
    e = ElementDef(id="bar", type="rect", fill="#FF0000")
    assert e.fill == "#FF0000"


def test_opacity_out_of_range_raises():
    with pytest.raises(ValidationError):
        ElementDef(id="bar", type="rect", fill="#000000", opacity=1.5)


def test_easing_config_defaults():
    ec = EasingConfig()
    assert ec.type == EasingType.ease_out_cubic
    assert ec.spring_stiffness == 150.0


def test_bezier_points_wrong_length_raises():
    with pytest.raises(ValidationError):
        EasingConfig(type=EasingType.cubic_bezier, bezier_points=[0.1, 0.2])


def test_keyframe_negative_t_raises():
    with pytest.raises(ValidationError):
        Keyframe(t_ms=-1, value=0.0)


def test_lower_third_spec_constructs():
    ir = MotionIR(elements=[_bar(), _text()],
                  tracks=[_track("bar", "x"), _track("t1", "y")],
                  total_ms=8000)
    spec = LowerThirdSpec(motion=ir)
    assert spec.schema_version == "2.0"
    assert spec.instance_id is None


def test_instance_id_excluded_from_llm_serialisation():
    ir = MotionIR(elements=[_bar()], tracks=[], total_ms=1000)
    spec = LowerThirdSpec(motion=ir, instance_id="lt_abc123")
    dumped = spec.model_dump(exclude={"instance_id", "schema_version"})
    assert "instance_id" not in dumped
    assert "schema_version" not in dumped


def test_content_mode_enum_values():
    assert ContentMode.person_chyron == "person_chyron"
    assert ContentMode.news_ticker == "news_ticker"
