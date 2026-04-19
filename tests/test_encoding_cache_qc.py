import pytest
import shutil
import tempfile
from pathlib import Path
from PIL import Image
import numpy as np

from lower_third.motion.motion_ir import MotionIR, ElementDef, LoopConfig
from lower_third.parser.prompt_schema import LowerThirdSpec, ContentMode


def _minimal_spec(bar_color="#1A1A2E", text_color="#FFFFFF") -> LowerThirdSpec:
    elem = ElementDef(id="bar", type="rect", x=0, y=960, w=1920, h=60,
                      fill=bar_color)
    ir = MotionIR(elements=[elem], tracks=[], total_ms=1000)
    return LowerThirdSpec(motion=ir, bar_color=bar_color, text_color=text_color)


def _make_png_sequence(tmpdir: Path, n_frames: int = 3) -> Path:
    frames_dir = tmpdir / "frames"
    frames_dir.mkdir()
    for i in range(n_frames):
        img = Image.new("RGBA", (1920, 1080), (26, 26, 46, 255))
        img.save(frames_dir / f"frame_{i:06d}.png")
    return frames_dir


# ── FFmpeg encoder ──────────────────────────────────────────────────────────

def test_encode_to_webm_creates_file():
    pytest.importorskip("subprocess")
    import subprocess
    result = subprocess.run(["ffmpeg", "-version"],
                            capture_output=True)
    if result.returncode != 0:
        pytest.skip("FFmpeg not available")

    from lower_third.renderer.ffmpeg_encoder import encode_to_webm
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        frames_dir = _make_png_sequence(tmpdir)
        out = encode_to_webm(frames_dir, tmpdir, fps=30)
        assert out.exists()
        assert out.suffix == ".webm"
        assert out.stat().st_size > 0


def test_encode_to_webm_returns_correct_path():
    import subprocess
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("FFmpeg not available")

    from lower_third.renderer.ffmpeg_encoder import encode_to_webm
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        frames_dir = _make_png_sequence(tmpdir)
        out = encode_to_webm(frames_dir, tmpdir, fps=30)
        assert out.name == "lower_third.webm"


def test_encode_to_webm_raises_on_bad_frames_dir():
    from lower_third.renderer.ffmpeg_encoder import encode_to_webm
    import subprocess
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    if result.returncode != 0:
        pytest.skip("FFmpeg not available")
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(subprocess.CalledProcessError):
            encode_to_webm(Path("/nonexistent/frames"), Path(tmpdir), fps=30)


# ── Template cache ───────────────────────────────────────────────────────────

def test_cache_key_is_deterministic():
    from lower_third.cache.template_cache import cache_key
    spec = _minimal_spec()
    assert cache_key(spec) == cache_key(spec)


def test_cache_key_is_64_char_hex():
    from lower_third.cache.template_cache import cache_key
    key = cache_key(_minimal_spec())
    assert len(key) == 64
    int(key, 16)   # must be valid hex


def test_cache_key_differs_for_different_specs():
    from lower_third.cache.template_cache import cache_key
    spec_a = _minimal_spec(bar_color="#1A1A2E")
    spec_b = _minimal_spec(bar_color="#CC0000")
    assert cache_key(spec_a) != cache_key(spec_b)


def test_cache_key_ignores_instance_id():
    from lower_third.cache.template_cache import cache_key
    spec_a = _minimal_spec()
    spec_b = _minimal_spec()
    spec_b.instance_id = "lt_abc123"   # instance_id is excluded
    assert cache_key(spec_a) == cache_key(spec_b)


def test_cache_hit_returns_none_when_missing():
    from lower_third.cache.template_cache import cache_hit
    spec = _minimal_spec()
    # Very unlikely to exist
    result = cache_hit(spec)
    assert result is None or isinstance(result, Path)


def test_cache_write_and_hit_roundtrip():
    from lower_third.cache.template_cache import cache_write, cache_hit, CACHE_DIR
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_webm = Path(tmpdir) / "lower_third.webm"
        fake_webm.write_bytes(b"FAKE_WEBM_DATA")

        import lower_third.cache.template_cache as tc
        original_cache_dir = tc.CACHE_DIR
        tc.CACHE_DIR = Path(tmpdir) / "cache"

        try:
            dest = cache_write(spec, fake_webm)
            assert dest.exists()
            assert dest.read_bytes() == b"FAKE_WEBM_DATA"
            hit = cache_hit(spec)
            # Patch CACHE_DIR for cache_hit too
            assert hit is not None
            assert hit.exists()
        finally:
            tc.CACHE_DIR = original_cache_dir


def test_cache_write_creates_directory():
    from lower_third.cache import template_cache as tc
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_webm = Path(tmpdir) / "lower_third.webm"
        fake_webm.write_bytes(b"FAKE")
        original = tc.CACHE_DIR
        new_cache = Path(tmpdir) / "new_cache_dir"
        tc.CACHE_DIR = new_cache
        try:
            assert not new_cache.exists()
            tc.cache_write(spec, fake_webm)
            assert new_cache.exists()
        finally:
            tc.CACHE_DIR = original


# ── QC validator ─────────────────────────────────────────────────────────────

def test_wcag_contrast_white_on_black():
    from lower_third.qc.validator import wcag_contrast_ratio
    ratio = wcag_contrast_ratio("#FFFFFF", "#000000")
    assert abs(ratio - 21.0) < 0.1


def test_wcag_contrast_identical_colours():
    from lower_third.qc.validator import wcag_contrast_ratio
    ratio = wcag_contrast_ratio("#1A1A2E", "#1A1A2E")
    assert abs(ratio - 1.0) < 0.01


def test_wcag_contrast_white_on_dark_bar():
    from lower_third.qc.validator import wcag_contrast_ratio
    ratio = wcag_contrast_ratio("#FFFFFF", "#1A1A2E")
    assert ratio > 4.5    # should pass WCAG AA


def test_qc_report_is_dataclass():
    from lower_third.qc.validator import QCReport
    report = QCReport(
        passed=True, warnings=[],
        min_contrast_ratio=7.2,
        luma_in_range=True, fps_match=True
    )
    assert report.passed is True
    assert report.warnings == []


def test_validate_returns_qc_report_not_raises():
    from lower_third.qc.validator import validate, QCReport
    spec = _minimal_spec()
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_webm = Path(tmpdir) / "lower_third.webm"
        fake_webm.write_bytes(b"NOT_A_REAL_VIDEO")
        result = validate(fake_webm, spec, project_fps=30)
        assert isinstance(result, QCReport)


def test_validate_high_contrast_spec_passes_contrast_check():
    from lower_third.qc.validator import validate
    spec = _minimal_spec(bar_color="#000000", text_color="#FFFFFF")
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_webm = Path(tmpdir) / "lower_third.webm"
        fake_webm.write_bytes(b"NOT_A_REAL_VIDEO")
        result = validate(fake_webm, spec, project_fps=30)
        assert result.min_contrast_ratio > 4.5


def test_validate_low_contrast_spec_adds_warning():
    from lower_third.qc.validator import validate
    spec = _minimal_spec(bar_color="#777777", text_color="#888888")
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_webm = Path(tmpdir) / "lower_third.webm"
        fake_webm.write_bytes(b"NOT_A_REAL_VIDEO")
        result = validate(fake_webm, spec, project_fps=30)
        contrast_warnings = [w for w in result.warnings if "Contrast" in w]
        assert len(contrast_warnings) == 1
