from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class EasingType(str, Enum):
    linear = "linear"
    ease_in = "ease_in"
    ease_out = "ease_out"
    ease_in_out = "ease_in_out"
    ease_in_cubic = "ease_in_cubic"
    ease_out_cubic = "ease_out_cubic"
    spring = "spring"
    bounce = "bounce"
    step = "step"
    cubic_bezier = "cubic_bezier"


class EasingConfig(BaseModel):
    type: EasingType = EasingType.ease_out_cubic
    spring_stiffness: float = 150.0
    spring_damping: float = 20.0
    spring_mass: float = 1.0
    bounce_count: int = 3
    bezier_points: list[float] | None = None

    @field_validator("bezier_points")
    @classmethod
    def bezier_must_have_four_points(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and len(v) != 4:
            raise ValueError("bezier_points must have exactly 4 elements")
        return v


class Keyframe(BaseModel):
    t_ms: int = Field(..., ge=0)
    value: float
    easing: EasingConfig = Field(default_factory=EasingConfig)


class AnimationTrack(BaseModel):
    element_id: str
    property: Literal[
        "x", "y", "w", "h", "opacity",
        "scale_x", "scale_y", "rotation",
        "clip_x", "clip_y", "clip_w", "clip_h",
        "text_x_offset",
    ]
    keyframes: list[Keyframe] = Field(..., min_length=1)
    start_offset_ms: int = Field(default=0, ge=0)


class SequenceGroup(BaseModel):
    mode: Literal["parallel", "sequential", "staggered"]
    track_ids: list[str]
    stagger_ms: int = 0


class LoopConfig(BaseModel):
    enabled: bool = False
    count: int = 0
    type: Literal["restart", "ping_pong"] = "restart"
    loop_after_ms: int | None = None


class ElementDef(BaseModel):
    id: str
    type: Literal["rect", "text"]
    content: str | None = None
    clip_to: str | None = None
    repeat_content: bool = False
    x: float = 0.0
    y: float = 0.0
    w: float | None = None
    h: float | None = None
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0
    fill: str = "#000000"
    font_size: int | None = None
    font_weight: Literal["regular", "bold"] = "regular"
    font_family: str = "Noto Sans"
    clip_x: float | None = None
    clip_y: float | None = None
    clip_w: float | None = None
    clip_h: float | None = None

    @field_validator("fill")
    @classmethod
    def fill_must_be_hex(cls, v: str) -> str:
        if len(v) != 7 or v[0] != "#" or not all(c in "0123456789ABCDEFabcdef" for c in v[1:]):
            raise ValueError("fill must be a 7-character hex string starting with '#'")
        return v


class MotionIR(BaseModel):
    elements: list[ElementDef] = Field(..., min_length=1)
    tracks: list[AnimationTrack]
    groups: list[SequenceGroup] = []
    loop: LoopConfig = Field(default_factory=LoopConfig)
    total_ms: int = Field(..., gt=0)

    @model_validator(mode="after")
    def validate_track_element_ids(self) -> "MotionIR":
        known_ids = {e.id for e in self.elements}
        for track in self.tracks:
            if track.element_id not in known_ids:
                raise ValueError(f"Track references unknown element_id: {track.element_id}")
        return self

    @model_validator(mode="after")
    def validate_clip_to_ids(self) -> "MotionIR":
        known_ids = {e.id for e in self.elements}
        for element in self.elements:
            if element.clip_to is not None and element.clip_to not in known_ids:
                raise ValueError(f"Element clip_to references unknown element_id: {element.clip_to}")
        return self

    @model_validator(mode="after")
    def validate_track_uniqueness(self) -> "MotionIR":
        seen = {}
        for track in self.tracks:
            key = (track.element_id, track.property)
            if key in seen:
                raise ValueError(
                    f"Duplicate track: element '{track.element_id}' property "
                    f"'{track.property}'. Combine into one track with all keyframes."
                )
            seen[key] = True
        return self
