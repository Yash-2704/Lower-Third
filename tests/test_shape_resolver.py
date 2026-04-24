import pytest
from pydantic import ValidationError

from lower_third.motion.motion_ir import (
    ElementDef, MotionIR, ShapeIntent, ShapeKind,
)
from lower_third.motion.shape_resolver import resolve_shapes


# ── helpers ──────────────────────────────────────────────────────────────────

def _bar() -> ElementDef:
    return ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")


def _path_el(kind: ShapeKind, cx: float = 960, cy: float = 540,
             rx: float = 50, ry: float = 50, **kwargs) -> ElementDef:
    intent = ShapeIntent(kind=kind, cx=cx, cy=cy, rx=rx, ry=ry, **kwargs)
    return ElementDef(id=f"shape_{kind.value}", type="path", shape_intent=intent, fill="#E63946")


def _ir(*extra: ElementDef) -> MotionIR:
    return MotionIR(elements=[_bar(), *extra], tracks=[], total_ms=1000)


# ── per-kind resolve tests ────────────────────────────────────────────────────

def _assert_resolved(kind: ShapeKind, **path_el_kwargs):
    el = _path_el(kind, **path_el_kwargs)
    ir = _ir(el)
    result = resolve_shapes(ir)

    assert isinstance(result, MotionIR)
    resolved_el = next(e for e in result.elements if e.id == el.id)
    assert resolved_el.d is not None
    assert len(resolved_el.d) > 0
    assert resolved_el.d.startswith("M ")
    assert resolved_el.d.endswith("Z")
    assert resolved_el.shape_intent is not None


def test_resolve_circle():
    _assert_resolved(ShapeKind.circle)


def test_resolve_ellipse():
    _assert_resolved(ShapeKind.ellipse, rx=80, ry=40)


def test_resolve_triangle():
    _assert_resolved(ShapeKind.triangle)


def test_resolve_diamond():
    _assert_resolved(ShapeKind.diamond)


def test_resolve_star():
    _assert_resolved(ShapeKind.star, points=5)


def test_resolve_pill():
    _assert_resolved(ShapeKind.pill, rx=120, ry=30, corner_r=30)  # corner_r forwarded via **path_el_kwargs → ShapeIntent


def test_resolve_chevron():
    _assert_resolved(ShapeKind.chevron)


def test_resolve_pentagon():
    _assert_resolved(ShapeKind.pentagon)


def test_resolve_hexagon():
    _assert_resolved(ShapeKind.hexagon)


# ── pass-through tests ────────────────────────────────────────────────────────

def test_rect_passes_through_unchanged():
    bar = _bar()
    ir = _ir()
    result = resolve_shapes(ir)
    assert result.elements[0].d is None


def test_text_passes_through_unchanged():
    text = ElementDef(id="t1", type="text", content="Hello", x=0, y=0, fill="#FFFFFF")
    ir = _ir(text)
    result = resolve_shapes(ir)
    text_out = next(e for e in result.elements if e.id == "t1")
    assert text_out.d is None


def test_path_with_d_already_set_not_overwritten():
    existing_d = "M 0,0 L 100,0 L 50,100 Z"
    el = ElementDef(id="manual", type="path", d=existing_d, fill="#123456")
    ir = _ir(el)
    result = resolve_shapes(ir)
    out = next(e for e in result.elements if e.id == "manual")
    assert out.d == existing_d


# ── validation error tests ────────────────────────────────────────────────────

def test_path_with_no_intent_and_no_d_raises():
    with pytest.raises(ValidationError):
        ElementDef(id="bad", type="path", fill="#000000")


def test_shape_intent_on_rect_raises():
    intent = ShapeIntent(kind=ShapeKind.circle, cx=100, cy=100, rx=20, ry=20)
    with pytest.raises(ValidationError):
        ElementDef(id="bad", type="rect", shape_intent=intent, fill="#000000")


def test_rx_zero_raises():
    with pytest.raises(ValidationError):
        ShapeIntent(kind=ShapeKind.circle, cx=100, cy=100, rx=0, ry=20)


def test_points_two_raises():
    with pytest.raises(ValidationError):
        ShapeIntent(kind=ShapeKind.star, cx=100, cy=100, rx=50, ry=50, points=2)
