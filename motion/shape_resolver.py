from __future__ import annotations

import math

from lower_third.motion.motion_ir import ElementDef, MotionIR, ShapeIntent, ShapeKind


def resolve_shapes(ir: MotionIR) -> MotionIR:
    new_elements = [_resolve_element(el) for el in ir.elements]
    return ir.model_copy(update={"elements": new_elements})


def _resolve_element(el: ElementDef) -> ElementDef:
    if el.type != "path":
        return el
    if el.d is not None:
        return el
    if el.shape_intent is None:
        return el
    d = _compute_d(el.shape_intent)
    return el.model_copy(update={"d": d})


def _r(v: float) -> float:
    return round(v, 2)


def _compute_d(intent: ShapeIntent) -> str:
    kind = intent.kind
    if kind == ShapeKind.circle or kind == ShapeKind.ellipse:
        return _circle_path(intent)
    if kind == ShapeKind.triangle:
        return _triangle_path(intent)
    if kind == ShapeKind.diamond:
        return _diamond_path(intent)
    if kind == ShapeKind.star:
        return _star_path(intent)
    if kind == ShapeKind.pill:
        return _pill_path(intent)
    if kind == ShapeKind.chevron:
        return _chevron_path(intent)
    if kind == ShapeKind.pentagon:
        return _regular_polygon(intent, 5)
    if kind == ShapeKind.hexagon:
        return _regular_polygon(intent, 6)
    raise ValueError(f"Unknown ShapeKind: {kind}")


def _circle_path(intent: ShapeIntent) -> str:
    cx, cy, rx, ry = intent.cx, intent.cy, intent.rx, intent.ry
    x0 = _r(cx - rx)
    x1 = _r(cx + rx)
    cy_ = _r(cy)
    return (
        f"M {x0},{cy_} "
        f"A {_r(rx)},{_r(ry)} 0 1,0 {x1},{cy_} "
        f"A {_r(rx)},{_r(ry)} 0 1,0 {x0},{cy_} Z"
    )


def _triangle_path(intent: ShapeIntent) -> str:
    cx, cy, rx, ry = intent.cx, intent.cy, intent.rx, intent.ry
    return (
        f"M {_r(cx)},{_r(cy - ry)} "
        f"L {_r(cx + rx)},{_r(cy + ry)} "
        f"L {_r(cx - rx)},{_r(cy + ry)} Z"
    )


def _diamond_path(intent: ShapeIntent) -> str:
    cx, cy, rx, ry = intent.cx, intent.cy, intent.rx, intent.ry
    return (
        f"M {_r(cx)},{_r(cy - ry)} "
        f"L {_r(cx + rx)},{_r(cy)} "
        f"L {_r(cx)},{_r(cy + ry)} "
        f"L {_r(cx - rx)},{_r(cy)} Z"
    )


def _star_path(intent: ShapeIntent) -> str:
    cx, cy, rx = intent.cx, intent.cy, intent.rx
    n = intent.points
    outer_r = rx
    inner_r = rx * 0.45
    parts: list[str] = []
    for i in range(2 * n):
        angle = -math.pi / 2 + i * math.pi / n
        r = outer_r if i % 2 == 0 else inner_r
        x = _r(cx + r * math.cos(angle))
        y = _r(cy + r * math.sin(angle))
        parts.append(f"{'M' if i == 0 else 'L'} {x},{y}")
    parts.append("Z")
    return " ".join(parts)


def _pill_path(intent: ShapeIntent) -> str:
    cx, cy, rx, ry = intent.cx, intent.cy, intent.rx, intent.ry
    r = min(intent.corner_r, rx, ry)
    left = _r(cx - rx)
    right = _r(cx + rx)
    top = _r(cy - ry)
    bottom = _r(cy + ry)
    r_ = _r(r)
    return (
        f"M {_r(left + r)},{top} "
        f"L {_r(right - r)},{top} "
        f"A {r_},{r_} 0 0,1 {right},{_r(top + r)} "
        f"L {right},{_r(bottom - r)} "
        f"A {r_},{r_} 0 0,1 {_r(right - r)},{bottom} "
        f"L {_r(left + r)},{bottom} "
        f"A {r_},{r_} 0 0,1 {left},{_r(bottom - r)} "
        f"L {left},{_r(top + r)} "
        f"A {r_},{r_} 0 0,1 {_r(left + r)},{top} Z"
    )


def _chevron_path(intent: ShapeIntent) -> str:
    cx, cy, rx, ry = intent.cx, intent.cy, intent.rx, intent.ry
    notch = _r(rx * 0.2)
    return (
        f"M {_r(cx - rx)},{_r(cy - ry)} "
        f"L {_r(cx + rx - notch)},{_r(cy - ry)} "
        f"L {_r(cx + rx)},{_r(cy)} "
        f"L {_r(cx + rx - notch)},{_r(cy + ry)} "
        f"L {_r(cx - rx)},{_r(cy + ry)} "
        f"L {_r(cx - rx + notch)},{_r(cy)} Z"
    )


def _regular_polygon(intent: ShapeIntent, n: int) -> str:
    cx, cy, rx, ry = intent.cx, intent.cy, intent.rx, intent.ry
    parts: list[str] = []
    for i in range(n):
        angle = -math.pi / 2 + i * 2 * math.pi / n
        x = _r(cx + rx * math.cos(angle))
        y = _r(cy + ry * math.sin(angle))
        parts.append(f"{'M' if i == 0 else 'L'} {x},{y}")
    parts.append("Z")
    return " ".join(parts)
