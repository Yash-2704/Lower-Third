import math
from dataclasses import dataclass
from lower_third.motion.motion_ir import MotionIR, EasingConfig, EasingType


@dataclass
class DrawState:
    elements: list[dict]


class InterpolationEngine:

    def __init__(self, ir: MotionIR, fps: int = 30):
        self.ir = ir
        self.fps = fps
        self.total_frames = int(ir.total_ms / 1000 * fps)
        self._index = self._build_index()

    def _build_index(self) -> dict:
        index = {}
        for track in self.ir.tracks:
            key = (track.element_id, track.property)
            entries = []
            for kf in track.keyframes:
                abs_t = kf.t_ms + track.start_offset_ms
                entries.append((abs_t, kf.value, kf.easing))
            entries.sort(key=lambda e: e[0])
            index[key] = entries
        return index

    def get_frame(self, frame_index: int) -> DrawState:
        effective = self._apply_loop(frame_index)
        t_ms = effective / self.fps * 1000

        result = []
        for elem in self.ir.elements:
            x = self._resolve(elem.id, "x", t_ms, elem.x)
            y = self._resolve(elem.id, "y", t_ms, elem.y)
            w = self._resolve(elem.id, "w", t_ms, elem.w if elem.w is not None else 0.0)
            h = self._resolve(elem.id, "h", t_ms, elem.h if elem.h is not None else 0.0)
            opacity = self._resolve(elem.id, "opacity", t_ms, elem.opacity)
            scale_x = self._resolve(elem.id, "scale_x", t_ms, elem.scale_x)
            scale_y = self._resolve(elem.id, "scale_y", t_ms, elem.scale_y)
            rotation = self._resolve(elem.id, "rotation", t_ms, elem.rotation)
            text_x_offset = self._resolve(elem.id, "text_x_offset", t_ms, 0.0)

            clip_x_default = elem.clip_x if elem.clip_x is not None else x
            clip_y_default = elem.clip_y if elem.clip_y is not None else y
            clip_w_default = elem.clip_w if elem.clip_w is not None else w
            clip_h_default = elem.clip_h if elem.clip_h is not None else h

            clip_x = self._resolve(elem.id, "clip_x", t_ms, clip_x_default)
            clip_y = self._resolve(elem.id, "clip_y", t_ms, clip_y_default)
            clip_w = self._resolve(elem.id, "clip_w", t_ms, clip_w_default)
            clip_h = self._resolve(elem.id, "clip_h", t_ms, clip_h_default)

            gradient_dict = None
            if elem.gradient is not None:
                gradient_dict = {
                    "start_color": elem.gradient.start_color,
                    "end_color": elem.gradient.end_color,
                    "angle_deg": elem.gradient.angle_deg,
                }
            result.append({
                "id": elem.id,
                "type": elem.type,
                "content": elem.content,
                "repeat_content": elem.repeat_content,
                "clip_to": elem.clip_to,
                "fill": elem.fill,
                "gradient": gradient_dict,
                "d": elem.d,
                "font_size": elem.font_size,
                "font_weight": elem.font_weight,
                "font_family": elem.font_family,
                "x": x,
                "y": y,
                "w": w,
                "h": h,
                "opacity": opacity,
                "scale_x": scale_x,
                "scale_y": scale_y,
                "rotation": rotation,
                "text_x_offset": text_x_offset,
                "clip_x": clip_x,
                "clip_y": clip_y,
                "clip_w": clip_w,
                "clip_h": clip_h,
            })

        return DrawState(elements=result)

    def _resolve(self, element_id: str, prop: str, t_ms: float, default: float) -> float:
        key = (element_id, prop)
        entries = self._index.get(key)
        if not entries:
            return default

        if t_ms <= entries[0][0]:
            return entries[0][1]

        if t_ms >= entries[-1][0]:
            return entries[-1][1]

        # Binary search for surrounding keyframes
        lo, hi = 0, len(entries) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if entries[mid][0] <= t_ms:
                lo = mid
            else:
                hi = mid

        t0, v0, easing = entries[lo]
        t1, v1, _ = entries[hi]

        span = t1 - t0
        progress = (t_ms - t0) / span if span > 0 else 1.0
        eased = self._ease(progress, easing)
        return v0 + (v1 - v0) * eased

    def _apply_loop(self, frame_index: int) -> int:
        if not self.ir.loop.enabled:
            return max(0, min(frame_index, self.total_frames))

        if self.ir.loop.loop_after_ms is not None:
            loop_frames = int(self.ir.loop.loop_after_ms / 1000 * self.fps)
        else:
            loop_frames = self.total_frames

        if loop_frames <= 0:
            return 0

        if self.ir.loop.type == "restart":
            return frame_index % loop_frames
        else:  # ping_pong
            cycle = frame_index % (2 * loop_frames)
            if cycle < loop_frames:
                return cycle
            else:
                return 2 * loop_frames - cycle

    def _ease(self, progress: float, easing: EasingConfig) -> float:
        p = progress
        t = easing.type

        if t == EasingType.linear:
            return p

        if t == EasingType.ease_in:
            return p ** 2

        if t == EasingType.ease_out:
            return 1 - (1 - p) ** 2

        if t == EasingType.ease_in_out:
            return p * p * (3 - 2 * p)

        if t == EasingType.ease_in_cubic:
            return p ** 3

        if t == EasingType.ease_out_cubic:
            return 1 - (1 - p) ** 3

        if t == EasingType.spring:
            k = easing.spring_stiffness
            c = easing.spring_damping
            m = easing.spring_mass
            omega = math.sqrt(k / m)
            zeta = c / (2 * math.sqrt(k * m))
            t_val = p * (6 / omega)
            if zeta < 1.0:
                omega_d = omega * math.sqrt(1 - zeta ** 2)
                result = 1 - math.exp(-zeta * omega * t_val) * (
                    math.cos(omega_d * t_val) +
                    (zeta / math.sqrt(1 - zeta ** 2)) * math.sin(omega_d * t_val)
                )
            else:
                r1 = -omega * (zeta + math.sqrt(zeta ** 2 - 1))
                r2 = -omega * (zeta - math.sqrt(zeta ** 2 - 1))
                if abs(r1 - r2) < 1e-10:
                    result = 1 - math.exp(r1 * t_val) * (1 + r1 * t_val)
                else:
                    c2 = r1 / (r1 - r2)
                    c1 = 1 - c2
                    result = 1 - (c1 * math.exp(r1 * t_val) + c2 * math.exp(r2 * t_val))
            return max(-0.5, min(1.5, result))

        if t == EasingType.bounce:
            n = easing.bounce_count
            for i in range(n):
                seg_start = i / n
                seg_end = (i + 1) / n
                if seg_start <= p <= seg_end:
                    local = (p - seg_start) * n
                    decay = (n - i) / n
                    return (1 - (2 * local - 1) ** 2) * decay
            return 1.0

        if t == EasingType.step:
            return 1.0 if p >= 0.5 else 0.0

        if t == EasingType.cubic_bezier:
            if easing.bezier_points is None or len(easing.bezier_points) < 4:
                return p
            x1, y1, x2, y2 = easing.bezier_points[:4]
            t_guess = p
            for _ in range(8):
                bx = (3 * (1 - t_guess) ** 2 * t_guess * x1 +
                      3 * (1 - t_guess) * t_guess ** 2 * x2 +
                      t_guess ** 3)
                dx = (3 * (1 - t_guess) ** 2 * x1 +
                      6 * (1 - t_guess) * t_guess * (x2 - x1) +
                      3 * t_guess ** 2 * (1 - x2))
                if abs(dx) < 1e-10:
                    break
                t_guess -= (bx - p) / dx
                t_guess = max(0.0, min(1.0, t_guess))
            by = (3 * (1 - t_guess) ** 2 * t_guess * y1 +
                  3 * (1 - t_guess) * t_guess ** 2 * y2 +
                  t_guess ** 3)
            return by

        return p
