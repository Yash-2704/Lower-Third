from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from lower_third.motion.motion_ir import MotionIR


class ContentMode(str, Enum):
    person_chyron = "person_chyron"
    news_ticker = "news_ticker"


class LowerThirdSpec(BaseModel):
    schema_version: str = Field(default="2.0", exclude=True)
    instance_id: str | None = Field(default=None, exclude=True)
    content_mode: ContentMode = ContentMode.news_ticker
    broadcast_safe: bool = True
    language_dir: Literal["ltr", "rtl"] = "ltr"
    bar_color: str = "#1A1A2E"
    text_color: str = "#FFFFFF"
    font_family: str = "Noto Sans"
    motion: MotionIR

    @field_validator("bar_color", "text_color")
    @classmethod
    def color_must_be_hex(cls, v: str) -> str:
        if len(v) != 7 or v[0] != "#" or not all(c in "0123456789ABCDEFabcdef" for c in v[1:]):
            raise ValueError("Color must be a 7-character hex string starting with '#'")
        return v
