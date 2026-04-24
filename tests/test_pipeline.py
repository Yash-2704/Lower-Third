import json
import uuid
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from lower_third.motion.motion_ir import MotionIR, ElementDef, LoopConfig
from lower_third.parser.prompt_schema import LowerThirdSpec, ContentMode
from lower_third.qc.validator import QCReport
from lower_third.choreography.brand_resolver import ResolvedBrand


def _minimal_spec(instance_id="lt_test01") -> LowerThirdSpec:
    elem = ElementDef(id="bar", type="rect", x=0, y=960,
                      w=1920, h=60, fill="#1a1a2e")
    ir   = MotionIR(elements=[elem], tracks=[], total_ms=1000)
    spec = LowerThirdSpec(motion=ir, bar_color="#1a1a2e", text_color="#ffffff")
    spec.instance_id = instance_id
    return spec


def _minimal_brand() -> ResolvedBrand:
    return ResolvedBrand(
        canvas_w=1920, canvas_h=1080,
        bar_y=960, bar_h=60,
        bar_color="#1a1a2e", text_color="#ffffff",
        bar_padding_left=24, bar_padding_top=12,
        inter_line_spacing=6,
        font_size_headline=32, font_size_kicker=22,
        font_size_name=38, font_size_title=28,
    )


def _good_qc() -> QCReport:
    return QCReport(passed=True, warnings=[],
                    min_contrast_ratio=17.8,
                    luma_in_range=True, fps_match=True)


# ── Manifest writer ──────────────────────────────────────────────────────────

def test_write_manifest_returns_dict():
    from lower_third.output.manifest_writer import write_manifest
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = write_manifest(spec, Path(tmpdir) / "lt.webm",
                                _good_qc(), Path(tmpdir))
    assert isinstance(result, dict)


def test_write_manifest_required_keys():
    from lower_third.output.manifest_writer import write_manifest
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = write_manifest(spec, Path(tmpdir) / "lt.webm",
                                _good_qc(), Path(tmpdir))
    for key in ["schema_version", "instance_id", "asset", "format",
                "resolution", "fps", "duration_ms", "timecode_in",
                "timecode_out", "loop", "qc", "ffmpeg_overlay", "color_space"]:
        assert key in result, f"Missing key: {key}"


def test_write_manifest_timecodes_are_null():
    from lower_third.output.manifest_writer import write_manifest
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = write_manifest(spec, Path(tmpdir) / "lt.webm",
                                _good_qc(), Path(tmpdir))
    assert result["timecode_in"]  is None
    assert result["timecode_out"] is None


def test_write_manifest_creates_json_file():
    from lower_third.output.manifest_writer import write_manifest
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        write_manifest(spec, tmpdir / "lt.webm", _good_qc(), tmpdir)
        manifest_file = tmpdir / f"{spec.instance_id}_manifest.json"
        assert manifest_file.exists()
        data = json.loads(manifest_file.read_text())
        assert data["instance_id"] == spec.instance_id


def test_write_manifest_json_file_is_valid():
    from lower_third.output.manifest_writer import write_manifest
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        write_manifest(spec, tmpdir / "lt.webm", _good_qc(), tmpdir)
        manifest_file = tmpdir / f"{spec.instance_id}_manifest.json"
        json.loads(manifest_file.read_text())   # must not raise


def test_write_manifest_qc_section():
    from lower_third.output.manifest_writer import write_manifest
    spec = _minimal_spec()
    qc = QCReport(passed=False, warnings=["luma out of range"],
                  min_contrast_ratio=3.1,
                  luma_in_range=False, fps_match=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        result = write_manifest(spec, Path(tmpdir) / "lt.webm",
                                qc, Path(tmpdir))
    assert result["qc"]["passed"] is False
    assert result["qc"]["warnings"] == ["luma out of range"]
    assert result["qc"]["min_contrast_ratio"] == 3.1


def test_write_manifest_ffmpeg_overlay_string():
    from lower_third.output.manifest_writer import write_manifest
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = write_manifest(spec, Path(tmpdir) / "lt.webm",
                                _good_qc(), Path(tmpdir))
    assert "{IN}" in result["ffmpeg_overlay"]
    assert "{OUT}" in result["ffmpeg_overlay"]
    assert "format=auto" in result["ffmpeg_overlay"]


# ── Pipeline orchestrator ────────────────────────────────────────────────────

def _mock_pipeline_deps(mock_video_path: Path):
    """Returns a context manager that patches all external pipeline deps."""
    import contextlib

    spec = _minimal_spec()

    @contextlib.contextmanager
    def _ctx():
        with patch("lower_third.pipeline.resolve_brand",
                   return_value=_minimal_brand()) as m_brand, \
             patch("lower_third.pipeline.parse_prompt",
                   return_value=spec) as m_parse, \
             patch("lower_third.pipeline.cache_hit",
                   return_value=None) as m_hit, \
             patch("lower_third.pipeline.render",
                   return_value=mock_video_path.parent / "frames") as m_render, \
             patch("lower_third.pipeline.encode_to_webm",
                   return_value=mock_video_path) as m_encode, \
             patch("lower_third.pipeline.cache_write") as m_cwrite, \
             patch("lower_third.pipeline.validate",
                   return_value=_good_qc()) as m_validate, \
             patch("lower_third.pipeline.write_manifest",
                   return_value={"instance_id": spec.instance_id}) as m_manifest:
            yield {
                "brand": m_brand, "parse": m_parse,
                "hit": m_hit, "render": m_render,
                "encode": m_encode, "cache_write": m_cwrite,
                "validate": m_validate, "manifest": m_manifest,
            }

    return _ctx()


def test_pipeline_returns_required_keys():
    from lower_third import pipeline
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_webm = Path(tmpdir) / "lower_third.webm"
        fake_webm.write_bytes(b"FAKE")
        with _mock_pipeline_deps(fake_webm):
            result = pipeline.generate_lower_third(
                "test prompt", {}, Path(tmpdir))
    for key in ["video_path", "manifest", "qc_report", "cache_hit"]:
        assert key in result


def test_pipeline_cache_hit_false_on_miss():
    from lower_third import pipeline
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_webm = Path(tmpdir) / "lower_third.webm"
        fake_webm.write_bytes(b"FAKE")
        with _mock_pipeline_deps(fake_webm):
            result = pipeline.generate_lower_third(
                "test prompt", {}, Path(tmpdir))
    assert result["cache_hit"] is False


def test_pipeline_brand_resolver_called_before_parse():
    from lower_third import pipeline
    call_order = []
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_webm = Path(tmpdir) / "lower_third.webm"
        fake_webm.write_bytes(b"FAKE")
        with _mock_pipeline_deps(fake_webm) as mocks:
            mocks["brand"].side_effect = \
                lambda *a, **kw: call_order.append("brand") or _minimal_brand()
            mocks["parse"].side_effect = \
                lambda *a, **kw: call_order.append("parse") or _minimal_spec()
            pipeline.generate_lower_third("test", {}, Path(tmpdir))
    assert call_order.index("brand") < call_order.index("parse")


def test_pipeline_encode_not_called_on_cache_hit():
    from lower_third import pipeline
    with tempfile.TemporaryDirectory() as tmpdir:
        cached_webm = Path(tmpdir) / "cached.webm"
        cached_webm.write_bytes(b"CACHED")
        fake_webm = Path(tmpdir) / "lower_third.webm"
        spec = _minimal_spec()
        with patch("lower_third.pipeline.resolve_brand",
                   return_value=_minimal_brand()), \
             patch("lower_third.pipeline.parse_prompt",
                   return_value=spec), \
             patch("lower_third.pipeline.cache_hit",
                   return_value=cached_webm), \
             patch("lower_third.pipeline.encode_to_webm") as m_encode, \
             patch("lower_third.pipeline.validate",
                   return_value=_good_qc()), \
             patch("lower_third.pipeline.write_manifest",
                   return_value={}):
            result = pipeline.generate_lower_third("test", {}, Path(tmpdir))
    m_encode.assert_not_called()
    assert result["cache_hit"] is True


def test_pipeline_instance_id_assigned():
    from lower_third import pipeline
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_webm = Path(tmpdir) / "lower_third.webm"
        fake_webm.write_bytes(b"FAKE")
        with _mock_pipeline_deps(fake_webm):
            result = pipeline.generate_lower_third("test", {}, Path(tmpdir))
    assert result["manifest"] is not None


def test_pipeline_output_dir_created():
    from lower_third import pipeline
    with tempfile.TemporaryDirectory() as tmpdir:
        new_dir = Path(tmpdir) / "deep" / "output"
        fake_webm = new_dir / "lower_third.webm"
        with _mock_pipeline_deps(fake_webm):
            pipeline.generate_lower_third("test", {}, new_dir)
        assert new_dir.exists()


def test_pipeline_validate_called_with_video_path():
    from lower_third import pipeline
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_webm = Path(tmpdir) / "lower_third.webm"
        fake_webm.write_bytes(b"FAKE")
        with _mock_pipeline_deps(fake_webm) as mocks:
            pipeline.generate_lower_third("test", {}, Path(tmpdir))
        mocks["validate"].assert_called_once()


def test_write_manifest_timecodes_when_provided():
    from lower_third.output.manifest_writer import write_manifest
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = write_manifest(
            spec, Path(tmpdir) / "lt.webm", _good_qc(), Path(tmpdir),
            timecode_in="00:04:32:12",
            timecode_out="00:04:40:12",
        )
    assert result["timecode_in"]  == "00:04:32:12"
    assert result["timecode_out"] == "00:04:40:12"


def test_write_manifest_qc_section_has_loop_seamless():
    from lower_third.output.manifest_writer import write_manifest
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = write_manifest(spec, Path(tmpdir) / "lt.webm", _good_qc(), Path(tmpdir))
    assert "loop_seamless" in result["qc"]


# ── True end-to-end (mocked LLM only) ────────────────────────────────────────

def test_end_to_end_pipeline_writes_manifest_to_disk():
    """
    True end-to-end: mocked LLM, real brand resolver, real interpolation,
    real cache, real manifest writer, real QC. Render and encode mocked
    to avoid Cairo/FFmpeg dependency in CI.
    """
    from lower_third import pipeline
    import lower_third.cache.template_cache as tc

    brand = _minimal_brand()
    spec  = _minimal_spec()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        fake_webm = tmpdir / f"{spec.instance_id}.webm"
        fake_webm.write_bytes(b"FAKEVIDEO")

        original_cache = tc.CACHE_DIR
        tc.CACHE_DIR = tmpdir / "cache"

        try:
            with patch("lower_third.pipeline.resolve_brand",
                       return_value=brand), \
                 patch("lower_third.pipeline.parse_prompt",
                       return_value=spec), \
                 patch("lower_third.pipeline.render",
                       return_value=tmpdir / "frames"), \
                 patch("lower_third.pipeline.encode_to_webm",
                       return_value=fake_webm):

                result = pipeline.generate_lower_third(
                    "Two rotating headlines about Iran and oil",
                    {},
                    tmpdir,
                )

            manifest_path = tmpdir / f"{result['manifest']['instance_id']}_manifest.json"
            assert manifest_path.exists(), "Manifest file not written to disk"

            data = json.loads(manifest_path.read_text())
            assert data["schema_version"] == "2.0"
            assert data["timecode_in"]  is None
            assert data["timecode_out"] is None
            assert data["qc"]["passed"] in (True, False)

        finally:
            tc.CACHE_DIR = original_cache
