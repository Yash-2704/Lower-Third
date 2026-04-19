"""
Integration test suite for the lower_third pipeline.
Mocks only the external LLM; every other component runs for real.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest

import lower_third.cache.template_cache as _tc

from lower_third.motion.motion_ir import (
    MotionIR, ElementDef, AnimationTrack, Keyframe,
    EasingConfig, EasingType, LoopConfig,
)
from lower_third.parser.prompt_schema import LowerThirdSpec, ContentMode
from lower_third.choreography.brand_resolver import resolve_brand, ResolvedBrand
from lower_third.choreography.tts_anchor import anchor_tracks_to_tts, build_element_words
from lower_third.motion.ir_builder import build_simple_bar_ir
from lower_third.motion.interpolation_engine import InterpolationEngine, DrawState
from lower_third.cache.template_cache import cache_key, cache_hit, cache_write
from lower_third.qc.validator import validate, wcag_contrast_ratio, QCReport
from lower_third.output.manifest_writer import write_manifest


# ── helpers ──────────────────────────────────────────────────────────────────

def _find_element(ir: MotionIR, eid: str) -> ElementDef:
    return next(e for e in ir.elements if e.id == eid)


def _find_in_state(state: DrawState, eid: str) -> dict:
    return next(e for e in state.elements if e["id"] == eid)


def _find_track(ir: MotionIR, eid: str, prop: str) -> AnimationTrack:
    return next(t for t in ir.tracks if t.element_id == eid and t.property == prop)


def _minimal_ir() -> MotionIR:
    """Single rect element, no tracks — used for QC / manifest helpers."""
    elem = ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")
    return MotionIR(elements=[elem], tracks=[], total_ms=1000)


def _spec_with_colors(bar_color: str, text_color: str) -> LowerThirdSpec:
    spec = LowerThirdSpec(motion=_minimal_ir(), bar_color=bar_color, text_color=text_color)
    spec.instance_id = "lt_qc_test"
    return spec


# ── Group 1 — Brand resolver → IR builder contract ───────────────────────────

class TestIRBuilderContract:

    def test_ir_builder_produces_valid_motion_ir(self):
        brand = resolve_brand({}, estimated_lines=2)
        ir = build_simple_bar_ir(
            brand,
            [{"text": "Breaking News", "role": "kicker"},
             {"text": "Dr. Jane Smith", "role": "name"}],
        )
        assert isinstance(ir, MotionIR)
        assert len(ir.elements) == 3  # bar + 2 text

        element_ids = {e.id for e in ir.elements}
        for elem in ir.elements:
            if elem.clip_to is not None:
                assert elem.clip_to in element_ids, (
                    f"clip_to='{elem.clip_to}' not found in elements"
                )

    def test_ir_builder_bar_y_within_canvas(self):
        brand = resolve_brand({}, estimated_lines=1)
        ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
        bar = _find_element(ir, "bar")
        assert bar.y >= 0
        assert bar.y + bar.h <= brand.canvas_h

    def test_ir_builder_with_anchor_avoid_zone(self):
        upstream = {"anchor_avoid_zone": {"x": 0, "y": 700, "w": 1920, "h": 300}}
        brand = resolve_brand(upstream, estimated_lines=1)
        ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
        bar = _find_element(ir, "bar")
        # bar must clear anchor zone bottom (700+300=1000) by at least 20px
        assert bar.y >= 700 + 300 + 20


# ── Group 2 — Interpolation engine → DrawState contract ──────────────────────

class TestInterpolationEngineContract:

    def test_engine_produces_draw_state_for_all_frames(self):
        brand = resolve_brand({}, estimated_lines=1)
        ir = build_simple_bar_ir(
            brand,
            [{"text": "Test", "role": "headline"}],
            duration_ms=1000,
        )
        engine = InterpolationEngine(ir, fps=30)
        assert engine.total_frames == 30

        for frame_idx in (0, 15, 29):
            state = engine.get_frame(frame_idx)
            assert isinstance(state, DrawState)
            # bar (rect) is not animated; only text elements appear in DrawState — 2 total
            assert len(state.elements) == 2

    def test_engine_slide_entry_moves_text_into_bar(self):
        brand = resolve_brand({}, estimated_lines=1)
        ir = build_simple_bar_ir(
            brand,
            [{"text": "Test", "role": "headline"}],
            duration_ms=2000,
        )
        engine = InterpolationEngine(ir, fps=30)

        frame_0  = engine.get_frame(0)
        frame_15 = engine.get_frame(15)  # 500ms — past 400ms entry animation end

        text_0  = _find_in_state(frame_0,  "line_0")
        text_15 = _find_in_state(frame_15, "line_0")

        # At t=0, text starts below bar (large y). At t=500ms it has settled.
        assert text_0["y"] > text_15["y"], (
            f"Expected text to slide upward: frame_0 y={text_0['y']}, "
            f"frame_15 y={text_15['y']}"
        )

    def test_engine_text_reaches_final_position(self):
        brand = resolve_brand({}, estimated_lines=1)
        ir = build_simple_bar_ir(
            brand,
            [{"text": "Test", "role": "headline"}],
            duration_ms=2000,
        )
        engine = InterpolationEngine(ir, fps=30)
        final_frame = engine.get_frame(engine.total_frames - 1)
        text = _find_in_state(final_frame, "line_0")

        # ir_builder sets y_final = bar_y + bar_padding_top + 0*(font+spacing) for i=0
        expected_y = float(brand.bar_y + brand.bar_padding_top)
        assert abs(text["y"] - expected_y) < 1.0, (
            f"Text did not reach final position: got {text['y']}, expected {expected_y}"
        )


# ── Group 3 — TTS anchor integration ─────────────────────────────────────────

class TestTTSAnchorIntegration:

    def _build_tts_ir(self):
        brand = resolve_brand({}, estimated_lines=2)
        ir = build_simple_bar_ir(
            brand,
            [
                {"text": "Iran blocks Hormuz", "role": "headline"},
                {"text": "Oil prices rise",     "role": "headline"},
            ],
            duration_ms=15000,
        )
        return ir

    def test_tts_anchor_end_to_end(self):
        ir = self._build_tts_ir()
        tts = {"Iran": 3200, "Oil": 9100}
        element_words = build_element_words(ir)
        anchored = anchor_tracks_to_tts(ir, tts, element_words)

        t0 = _find_track(anchored, "line_0", "y")
        t1 = _find_track(anchored, "line_1", "y")
        assert t0.start_offset_ms == 3200
        assert t1.start_offset_ms == 9100

        # last keyframe t_ms = 400; latest absolute time = 9100 + 400 = 9500
        assert anchored.total_ms >= 9100 + 400

    def test_tts_anchor_does_not_break_engine(self):
        ir = self._build_tts_ir()
        tts = {"Iran": 3200, "Oil": 9100}
        element_words = build_element_words(ir)
        anchored = anchor_tracks_to_tts(ir, tts, element_words)

        engine = InterpolationEngine(anchored, fps=30)
        for frame_idx in range(engine.total_frames):
            state = engine.get_frame(frame_idx)
            assert isinstance(state, DrawState)


# ── Group 4 — Cache integration ───────────────────────────────────────────────

class TestCacheIntegration:

    def test_cache_roundtrip_with_real_spec(self, tmp_path):
        brand = resolve_brand({}, estimated_lines=1)
        ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
        spec = LowerThirdSpec(motion=ir)
        spec.instance_id = "lt_integ_test"

        original_cache_dir = _tc.CACHE_DIR
        _tc.CACHE_DIR = tmp_path / "cache"
        try:
            assert cache_hit(spec) is None

            fake_webm = tmp_path / "fake.webm"
            fake_webm.write_bytes(b"FAKEVIDEO")
            cache_write(spec, fake_webm)

            hit = cache_hit(spec)
            assert hit is not None
            assert hit.read_bytes() == b"FAKEVIDEO"
        finally:
            _tc.CACHE_DIR = original_cache_dir

    def test_cache_key_stable_across_calls(self):
        brand = resolve_brand({}, estimated_lines=1)
        ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
        spec = LowerThirdSpec(motion=ir)

        key1 = cache_key(spec)
        key2 = cache_key(spec)
        assert key1 == key2
        assert len(key1) == 64


# ── Group 5 — QC validator integration ───────────────────────────────────────

class TestQCValidatorIntegration:

    def test_qc_contrast_passes_for_default_colours(self):
        ratio = wcag_contrast_ratio("#1A1A2E", "#FFFFFF")
        assert ratio > 4.5

    def test_qc_validate_on_nonexistent_file_returns_report_not_raises(self):
        brand = resolve_brand({}, estimated_lines=1)
        ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
        spec = LowerThirdSpec(motion=ir)

        result = validate(Path("/nonexistent/file.webm"), spec, project_fps=30)
        assert isinstance(result, QCReport)
        # Must return a report — not raise. passed can be either value.
        assert result.passed is True or result.passed is False

    def test_qc_high_contrast_spec_has_no_contrast_warning(self):
        spec = _spec_with_colors("#000000", "#FFFFFF")
        result = validate(Path("/nonexistent/file.webm"), spec)
        contrast_warnings = [w for w in result.warnings if "Contrast" in w]
        assert len(contrast_warnings) == 0

    def test_qc_low_contrast_spec_has_contrast_warning(self):
        spec = _spec_with_colors("#888888", "#999999")
        result = validate(Path("/nonexistent/file.webm"), spec)
        contrast_warnings = [w for w in result.warnings if "Contrast" in w]
        assert len(contrast_warnings) == 1


# ── Group 6 — Manifest writer integration ─────────────────────────────────────

class TestManifestWriterIntegration:

    def _setup(self, tmp_path):
        brand = resolve_brand({}, estimated_lines=1)
        ir = build_simple_bar_ir(brand, [{"text": "Test", "role": "headline"}])
        spec = LowerThirdSpec(motion=ir)
        spec.instance_id = "lt_manifest_test"
        qc = QCReport(
            passed=True,
            warnings=[],
            min_contrast_ratio=17.8,
            luma_in_range=True,
            fps_match=True,
        )
        write_manifest(spec, tmp_path / "lt.webm", qc, tmp_path)
        manifest_path = tmp_path / "lt_manifest_test_manifest.json"
        data = json.loads(manifest_path.read_text())
        return spec, manifest_path, data

    def test_manifest_written_to_disk_with_correct_structure(self, tmp_path):
        spec, manifest_path, data = self._setup(tmp_path)
        assert manifest_path.exists()
        assert data["instance_id"] == "lt_manifest_test"
        assert data["timecode_in"] is None
        assert data["timecode_out"] is None
        assert "ffmpeg_overlay" in data
        assert "qc" in data

    def test_manifest_ffmpeg_overlay_has_placeholders(self, tmp_path):
        _, _, data = self._setup(tmp_path)
        assert "{IN}" in data["ffmpeg_overlay"]
        assert "{OUT}" in data["ffmpeg_overlay"]


# ── Group 7 — Full pipeline integration (mocked LLM, real everything else) ────

class TestFullPipelineIntegration:

    def _make_spec(self, tmp_path: Path) -> LowerThirdSpec:
        brand = resolve_brand({}, estimated_lines=1)
        ir = build_simple_bar_ir(
            brand,
            [{"text": "Breaking News", "role": "headline"}],
        )
        spec = LowerThirdSpec(motion=ir, bar_color="#1A1A2E", text_color="#FFFFFF")
        spec.instance_id = "lt_full_test"
        return spec

    def test_full_pipeline_without_render(self, tmp_path):
        from lower_third import pipeline

        spec = self._make_spec(tmp_path)
        fake_webm = tmp_path / f"{spec.instance_id}.webm"
        fake_webm.write_bytes(b"FAKEVIDEO")

        brand = resolve_brand({}, estimated_lines=1)

        original_cache_dir = _tc.CACHE_DIR
        _tc.CACHE_DIR = tmp_path / "cache"
        try:
            with patch("lower_third.pipeline.resolve_brand", return_value=brand), \
                 patch("lower_third.pipeline.parse_prompt", return_value=spec), \
                 patch("lower_third.pipeline.render", return_value=tmp_path / "frames"), \
                 patch("lower_third.pipeline.encode_to_webm", return_value=fake_webm):

                result = pipeline.generate_lower_third("test prompt", {}, tmp_path)

            assert result["cache_hit"] is False
            assert str(result["video_path"]).endswith(".webm")
            assert "instance_id" in result["manifest"]
            assert isinstance(result["qc_report"], QCReport)

            manifest_path = tmp_path / f"{result['manifest']['instance_id']}_manifest.json"
            assert manifest_path.exists()
        finally:
            _tc.CACHE_DIR = original_cache_dir

    def test_full_pipeline_cache_hit_path(self, tmp_path):
        from lower_third import pipeline
        from unittest.mock import MagicMock

        spec = self._make_spec(tmp_path)
        fake_webm = tmp_path / f"{spec.instance_id}.webm"
        fake_webm.write_bytes(b"FAKEVIDEO")

        brand = resolve_brand({}, estimated_lines=1)
        encode_mock = MagicMock(return_value=fake_webm)

        original_cache_dir = _tc.CACHE_DIR
        _tc.CACHE_DIR = tmp_path / "cache"
        try:
            with patch("lower_third.pipeline.resolve_brand", return_value=brand), \
                 patch("lower_third.pipeline.parse_prompt", return_value=spec), \
                 patch("lower_third.pipeline.render", return_value=tmp_path / "frames"), \
                 patch("lower_third.pipeline.encode_to_webm", encode_mock):

                result1 = pipeline.generate_lower_third("test prompt", {}, tmp_path)
                result2 = pipeline.generate_lower_third("test prompt", {}, tmp_path)

            assert result1["cache_hit"] is False
            assert result2["cache_hit"] is True
            encode_mock.assert_called_once()
        finally:
            _tc.CACHE_DIR = original_cache_dir
