from __future__ import annotations

from lower_third.choreography.brand_resolver import ResolvedBrand
from lower_third.motion.motion_ir import (
    AnimationTrack,
    EasingConfig,
    EasingType,
    ElementDef,
    Keyframe,
    LoopConfig,
    MotionIR,
)

_FONT_SIZE_MAP = {
    "kicker":   lambda b: b.font_size_kicker,
    "name":     lambda b: b.font_size_name,
    "title":    lambda b: b.font_size_title,
    "headline": lambda b: b.font_size_headline,
}

_BOLD_ROLES = {"kicker", "name", "headline"}


def build_simple_bar_ir(
    brand: ResolvedBrand,
    lines: list[dict],
    duration_ms: int = 8000,
    loop: bool = False,
) -> MotionIR:
    elements: list[ElementDef] = [
        ElementDef(
            id="bar",
            type="rect",
            x=0,
            y=brand.bar_y,
            w=brand.canvas_w,
            h=brand.bar_h,
            fill=brand.bar_color,
        )
    ]
    tracks: list[AnimationTrack] = []

    for i, line in enumerate(lines):
        role = line["role"]
        font_size = _FONT_SIZE_MAP[role](brand)
        y_final = brand.bar_y + brand.bar_padding_top + i * (font_size + brand.inter_line_spacing)

        elements.append(
            ElementDef(
                id=f"line_{i}",
                type="text",
                content=line["text"],
                clip_to="bar",
                x=brand.bar_padding_left,
                y=y_final,
                fill=brand.text_color,
                font_size=font_size,
                font_weight="bold" if role in _BOLD_ROLES else "regular",
            )
        )

        tracks.append(
            AnimationTrack(
                element_id=f"line_{i}",
                property="y",
                start_offset_ms=i * 300,
                keyframes=[
                    Keyframe(t_ms=0, value=float(brand.bar_y + brand.bar_h)),
                    Keyframe(
                        t_ms=400,
                        value=float(y_final),
                        easing=EasingConfig(type=EasingType.ease_out_cubic),
                    ),
                ],
            )
        )

    loop_config = LoopConfig(enabled=True, count=0, type="restart") if loop else LoopConfig()

    return MotionIR(
        elements=elements,
        tracks=tracks,
        loop=loop_config,
        total_ms=duration_ms,
    )
