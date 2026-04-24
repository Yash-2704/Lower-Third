import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch, MagicMock

import pytest

from lower_third.motion.motion_ir import MotionIR, ElementDef
from lower_third.parser.prompt_schema import LowerThirdSpec
from lower_third.qc.validator import QCReport
from lower_third.output.manifest_writer import write_manifest

# api.py calls `from dotenv import load_dotenv` at import time.
# Stub it out if the package is not installed so the test can still run.
if "dotenv" not in sys.modules:
    _fake_dotenv = ModuleType("dotenv")
    _fake_dotenv.load_dotenv = lambda: None  # type: ignore[attr-defined]
    sys.modules["dotenv"] = _fake_dotenv

from lower_third.api import GenerateRequest  # noqa: E402 — after stub


def _minimal_spec(instance_id: str = "lt_tc_test") -> LowerThirdSpec:
    elem = ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")
    ir   = MotionIR(elements=[elem], tracks=[], total_ms=1000)
    spec = LowerThirdSpec(motion=ir)
    spec.instance_id = instance_id
    return spec


def _good_qc(loop_seamless: bool | None = None) -> QCReport:
    return QCReport(
        passed=True, warnings=[],
        min_contrast_ratio=17.8,
        luma_in_range=True, fps_match=True,
        loop_seamless=loop_seamless,
    )


# timecode_in / timecode_out written to manifest JSON

def test_write_manifest_timecodes_provided(tmp_path):
    spec = _minimal_spec()
    result = write_manifest(
        spec, tmp_path / "lt.webm", _good_qc(), tmp_path,
        timecode_in="00:04:32:12",
        timecode_out="00:04:40:12",
    )
    assert result["timecode_in"]  == "00:04:32:12"
    assert result["timecode_out"] == "00:04:40:12"

    manifest_path = tmp_path / f"{spec.instance_id}_manifest.json"
    data = json.loads(manifest_path.read_text())
    assert data["timecode_in"]  == "00:04:32:12"
    assert data["timecode_out"] == "00:04:40:12"


def test_write_manifest_timecodes_null_by_default(tmp_path):
    spec = _minimal_spec()
    result = write_manifest(spec, tmp_path / "lt.webm", _good_qc(), tmp_path)
    assert result["timecode_in"]  is None
    assert result["timecode_out"] is None


# loop_seamless propagated into qc section

def test_write_manifest_qc_loop_seamless_true(tmp_path):
    spec = _minimal_spec()
    result = write_manifest(spec, tmp_path / "lt.webm", _good_qc(loop_seamless=True), tmp_path)
    assert result["qc"]["loop_seamless"] is True


def test_write_manifest_qc_loop_seamless_none(tmp_path):
    spec = _minimal_spec()
    result = write_manifest(spec, tmp_path / "lt.webm", _good_qc(loop_seamless=None), tmp_path)
    assert result["qc"]["loop_seamless"] is None

    manifest_path = tmp_path / f"{spec.instance_id}_manifest.json"
    data = json.loads(manifest_path.read_text())
    assert data["qc"]["loop_seamless"] is None


# generate_lower_third accepts timecode kwargs without TypeError

def test_generate_lower_third_accepts_timecodes():
    from lower_third import pipeline
    from lower_third.choreography.brand_resolver import ResolvedBrand

    brand = ResolvedBrand(
        canvas_w=1920, canvas_h=1080,
        bar_y=960, bar_h=60,
        bar_color="#1a1a2e", text_color="#ffffff",
        bar_padding_left=24, bar_padding_top=12,
        inter_line_spacing=6,
        font_size_headline=32, font_size_kicker=22,
        font_size_name=38, font_size_title=28,
    )
    spec = _minimal_spec()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        fake_webm = tmpdir / "lower_third.webm"
        fake_webm.write_bytes(b"FAKE")

        with patch("lower_third.pipeline.resolve_brand", return_value=brand), \
             patch("lower_third.pipeline.parse_prompt", return_value=spec), \
             patch("lower_third.pipeline.cache_hit", return_value=None), \
             patch("lower_third.pipeline.render", return_value=tmpdir / "frames"), \
             patch("lower_third.pipeline.encode_to_webm", return_value=fake_webm), \
             patch("lower_third.pipeline.cache_write"), \
             patch("lower_third.pipeline.validate", return_value=_good_qc()), \
             patch("lower_third.pipeline.write_manifest", return_value={"instance_id": "lt_tc_test"}):

            result = pipeline.generate_lower_third(
                "test", {}, tmpdir,
                timecode_in="00:01:00:00",
                timecode_out="00:01:10:00",
            )
    assert result is not None


# GenerateRequest fields

def test_generate_request_timecodes_default_none():
    req = GenerateRequest(prompt="test")
    assert req.timecode_in  is None
    assert req.timecode_out is None


def test_generate_request_timecodes_parse():
    req = GenerateRequest(prompt="test", timecode_in="00:01:00:00")
    assert req.timecode_in == "00:01:00:00"
    assert req.timecode_out is None
