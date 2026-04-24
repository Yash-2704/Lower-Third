import numpy as np
import pytest
import cv2
from pathlib import Path

from lower_third.motion.motion_ir import MotionIR, ElementDef, LoopConfig
from lower_third.parser.prompt_schema import LowerThirdSpec
from lower_third.qc.validator import validate, LOOP_SEAMLESS_THRESHOLD


def _write_png(path: Path, pixels: np.ndarray) -> None:
    cv2.imwrite(str(path), pixels)


def _identical_frames(tmp_path: Path) -> Path:
    pixel = np.full((10, 10, 4), [0, 0, 255, 128], dtype=np.uint8)
    _write_png(tmp_path / "frame_000000.png", pixel)
    _write_png(tmp_path / "frame_000060.png", pixel)
    return tmp_path


def _different_frames(tmp_path: Path) -> Path:
    red  = np.full((10, 10, 4), [0, 0, 255, 128], dtype=np.uint8)
    blue = np.full((10, 10, 4), [255, 0, 0, 128], dtype=np.uint8)
    _write_png(tmp_path / "frame_000000.png", red)
    _write_png(tmp_path / "frame_000060.png", blue)
    return tmp_path


def _minimal_looping_spec() -> LowerThirdSpec:
    elem = ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")
    loop = LoopConfig(enabled=True, loop_after_ms=2000)
    ir   = MotionIR(elements=[elem], tracks=[], total_ms=3600000, loop=loop)
    return LowerThirdSpec(motion=ir)


def _minimal_nonlooping_spec() -> LowerThirdSpec:
    elem = ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60, fill="#1A1A2E")
    ir   = MotionIR(elements=[elem], tracks=[], total_ms=3600000)
    return LowerThirdSpec(motion=ir)


def _fake_webm(tmp_path: Path) -> Path:
    p = tmp_path / "fake.webm"
    p.write_bytes(b"NOT_A_REAL_VIDEO")
    return p


# frames_dir=None → loop_seamless=None regardless of loop config

def test_frames_dir_none_returns_loop_seamless_none(tmp_path):
    spec = _minimal_looping_spec()
    result = validate(_fake_webm(tmp_path), spec, project_fps=30, frames_dir=None)
    assert result.loop_seamless is None


# Non-looping spec with frames_dir set → loop_seamless=None

def test_nonlooping_spec_returns_loop_seamless_none(tmp_path):
    spec = _minimal_nonlooping_spec()
    _identical_frames(tmp_path)
    result = validate(_fake_webm(tmp_path), spec, project_fps=30, frames_dir=tmp_path)
    assert result.loop_seamless is None


# Identical frames → loop_seamless=True, no loop warning

def test_identical_frames_loop_seamless_true(tmp_path):
    spec = _minimal_looping_spec()
    _identical_frames(tmp_path)
    result = validate(_fake_webm(tmp_path), spec, project_fps=30, frames_dir=tmp_path)
    assert result.loop_seamless is True
    loop_warnings = [w for w in result.warnings if "Loop restart" in w]
    assert len(loop_warnings) == 0


# Different frames → loop_seamless=False, warning present

def test_different_frames_loop_seamless_false(tmp_path):
    spec = _minimal_looping_spec()
    _different_frames(tmp_path)
    result = validate(_fake_webm(tmp_path), spec, project_fps=30, frames_dir=tmp_path)
    assert result.loop_seamless is False
    loop_warnings = [w for w in result.warnings if "Loop restart discontinuity" in w]
    assert len(loop_warnings) == 1


# Missing loop frame PNG → loop_seamless=None (not False, not crash)

def test_missing_loop_frame_returns_none(tmp_path):
    spec = _minimal_looping_spec()
    # write only frame 0, not frame 60
    pixel = np.full((10, 10, 4), [0, 0, 255, 128], dtype=np.uint8)
    _write_png(tmp_path / "frame_000000.png", pixel)
    result = validate(_fake_webm(tmp_path), spec, project_fps=30, frames_dir=tmp_path)
    assert result.loop_seamless is None


# Missing frame 0 PNG → loop_seamless=None (not False, not crash)

def test_missing_frame_zero_returns_none(tmp_path):
    spec = _minimal_looping_spec()
    pixel = np.full((10, 10, 4), [0, 0, 255, 128], dtype=np.uint8)
    _write_png(tmp_path / "frame_000060.png", pixel)
    result = validate(_fake_webm(tmp_path), spec, project_fps=30, frames_dir=tmp_path)
    assert result.loop_seamless is None


# QCReport.passed is False when loop_seamless is False

def test_qc_passed_false_when_loop_seamless_false(tmp_path):
    spec = _minimal_looping_spec()
    _different_frames(tmp_path)
    result = validate(_fake_webm(tmp_path), spec, project_fps=30, frames_dir=tmp_path)
    assert result.loop_seamless is False
    assert result.passed is False


# loop_seamless=True adds no warning

def test_loop_seamless_true_adds_no_warning(tmp_path):
    spec = _minimal_looping_spec()
    _identical_frames(tmp_path)
    result = validate(_fake_webm(tmp_path), spec, project_fps=30, frames_dir=tmp_path)
    loop_warnings = [w for w in result.warnings if "Loop" in w]
    assert len(loop_warnings) == 0


# Both frames fully transparent → loop_seamless=True

def test_fully_transparent_frames_loop_seamless_true(tmp_path):
    spec = _minimal_looping_spec()
    transparent = np.zeros((10, 10, 4), dtype=np.uint8)
    _write_png(tmp_path / "frame_000000.png", transparent)
    _write_png(tmp_path / "frame_000060.png", transparent)
    result = validate(_fake_webm(tmp_path), spec, project_fps=30, frames_dir=tmp_path)
    assert result.loop_seamless is True
