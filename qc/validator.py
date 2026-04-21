import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from lower_third.parser.prompt_schema import LowerThirdSpec

log = logging.getLogger(__name__)
_CONSTANTS_PATH = Path(__file__).resolve().parent.parent / "config" / "module_constants.json"


@dataclass
class QCReport:
    passed: bool
    warnings: list[str]
    min_contrast_ratio: float
    luma_in_range: bool
    fps_match: bool


def wcag_contrast_ratio(hex_a: str, hex_b: str) -> float:
    def relative_luminance(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        channels = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255.0
            linear = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            channels.append(linear)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    l1 = relative_luminance(hex_a)
    l2 = relative_luminance(hex_b)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def validate(webm_path: Path, spec: LowerThirdSpec, project_fps: int = 30) -> QCReport:
    constants = json.loads(_CONSTANTS_PATH.read_text())
    broadcast_luma_min = constants["broadcast_luma_min"]
    broadcast_luma_max = constants["broadcast_luma_max"]
    min_contrast_ratio = constants["min_contrast_ratio"]

    warnings: list[str] = []
    fps_ok = True
    luma_ok = True

    cap = cv2.VideoCapture(str(webm_path))

    rendered_fps = cap.get(cv2.CAP_PROP_FPS)
    if rendered_fps == 0 or abs(rendered_fps - project_fps) > 0.5:
        if rendered_fps != 0:
            warnings.append(
                f"FPS mismatch: rendered={rendered_fps:.1f}, expected={project_fps}"
            )
            fps_ok = False

    # Luma check — sample 5 evenly spaced frames
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    luma_min = broadcast_luma_min
    luma_max = broadcast_luma_max

    sample_indices = [0, total // 4, total // 2, 3 * total // 4, max(0, total - 1)]

    for frame_idx in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        # Convert to grayscale (works on both BGR and BGRA frames)
        if frame.ndim == 3 and frame.shape[2] == 4:
            # BGRA — mask out fully transparent pixels
            alpha = frame[:, :, 3]
            bgr   = frame[:, :, :3]
            gray  = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            # Only measure pixels where alpha > 10 (not transparent background)
            mask  = alpha > 10
        else:
            # BGR — exclude pure black pixels (transparent background in VP9)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Exclude pixels that are all-zero across all channels (transparent bg)
            mask = np.any(frame > 0, axis=2)

        if not mask.any():
            # Fully transparent frame — skip, not a luma violation
            continue

        lo = int(gray[mask].min())
        hi = int(gray[mask].max())

        if lo < luma_min or hi > luma_max:
            warnings.append(
                f"Frame {frame_idx}: luma out of range [{lo}, {hi}] "
                f"(allowed {luma_min}–{luma_max})"
            )
            luma_ok = False

    cap.release()

    ratio = wcag_contrast_ratio(spec.bar_color, spec.text_color)
    if ratio < min_contrast_ratio:
        warnings.append(
            f"Contrast {ratio:.2f}:1 below minimum {min_contrast_ratio}:1"
        )

    return QCReport(
        passed=len(warnings) == 0,
        warnings=warnings,
        min_contrast_ratio=ratio,
        luma_in_range=luma_ok,
        fps_match=fps_ok,
    )
