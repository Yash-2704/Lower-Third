import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from lower_third.api import app, OUTPUT_DIR
from lower_third.qc.validator import QCReport

client = TestClient(app)


def _mock_result(instance_id="lt_test01") -> dict:
    return {
        "video_path": OUTPUT_DIR / f"{instance_id}.webm",
        "manifest": {
            "schema_version":  "2.0",
            "instance_id":     instance_id,
            "asset":           str(OUTPUT_DIR / f"{instance_id}.webm"),
            "format":          "webm_rgba_vp9",
            "resolution":      [1920, 1080],
            "fps":             30,
            "duration_ms":     8000,
            "timecode_in":     None,
            "timecode_out":    None,
            "loop":            True,
            "qc": {
                "passed":             True,
                "warnings":           [],
                "min_contrast_ratio": 17.8,
            },
            "ffmpeg_overlay":  "overlay=0:0:format=auto:enable='between(t,{IN},{OUT})'",
            "color_space":     "bt709",
        },
        "qc_report": QCReport(
            passed=True, warnings=[],
            min_contrast_ratio=17.8,
            luma_in_range=True, fps_match=True,
        ),
        "cache_hit": False,
    }


# ── Health ───────────────────────────────────────────────────────────────────

def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_ok():
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.0"


# ── Generate ─────────────────────────────────────────────────────────────────

def test_generate_empty_prompt_returns_422():
    response = client.post("/generate", json={"prompt": ""})
    assert response.status_code == 422


def test_generate_missing_prompt_returns_422():
    response = client.post("/generate", json={})
    assert response.status_code == 422


def test_generate_returns_200_on_success():
    with patch("lower_third.api.generate_lower_third",
               return_value=_mock_result()):
        response = client.post("/generate", json={"prompt": "test prompt"})
    assert response.status_code == 200


def test_generate_response_has_required_fields():
    with patch("lower_third.api.generate_lower_third",
               return_value=_mock_result()):
        response = client.post("/generate", json={"prompt": "test prompt"})
    data = response.json()
    for field in ["instance_id", "video_url", "manifest",
                  "cache_hit", "qc_passed", "qc_warnings",
                  "min_contrast_ratio"]:
        assert field in data, f"Missing field: {field}"


def test_generate_video_url_format():
    with patch("lower_third.api.generate_lower_third",
               return_value=_mock_result("lt_abc123")):
        response = client.post("/generate", json={"prompt": "test prompt"})
    data = response.json()
    assert data["video_url"].startswith("/assets/")
    assert data["video_url"].endswith(".webm")


def test_generate_instance_id_in_response():
    with patch("lower_third.api.generate_lower_third",
               return_value=_mock_result("lt_abc123")):
        response = client.post("/generate", json={"prompt": "test"})
    assert response.json()["instance_id"] == "lt_abc123"


def test_generate_cache_hit_propagated():
    result = _mock_result()
    result["cache_hit"] = True
    with patch("lower_third.api.generate_lower_third", return_value=result):
        response = client.post("/generate", json={"prompt": "test"})
    assert response.json()["cache_hit"] is True


def test_generate_pipeline_exception_returns_500():
    with patch("lower_third.api.generate_lower_third",
               side_effect=RuntimeError("LLM failed")):
        response = client.post("/generate", json={"prompt": "test"})
    assert response.status_code == 500
    assert "error" in response.json()


def test_generate_passes_upstream_signals():
    signals = {"lower_third_style": "bold_red_bar"}
    captured = {}
    def capture(**kwargs):
        captured.update(kwargs)
        return _mock_result()
    with patch("lower_third.api.generate_lower_third", side_effect=capture):
        client.post("/generate", json={
            "prompt": "test",
            "upstream_signals": signals
        })
    assert captured.get("upstream_signals") == signals


def test_generate_passes_project_fps():
    captured = {}
    def capture(**kwargs):
        captured.update(kwargs)
        return _mock_result()
    with patch("lower_third.api.generate_lower_third", side_effect=capture):
        client.post("/generate", json={"prompt": "test", "project_fps": 25})
    assert captured.get("project_fps") == 25


# ── Manifest ─────────────────────────────────────────────────────────────────

def test_manifest_not_found_returns_404():
    response = client.get("/manifest/nonexistent_id")
    assert response.status_code == 404


def test_manifest_returns_200_when_exists(tmp_path):
    import lower_third.api as api_module
    original = api_module.OUTPUT_DIR
    api_module.OUTPUT_DIR = tmp_path

    manifest_data = {"instance_id": "lt_test99", "schema_version": "2.0"}
    manifest_file = tmp_path / "lt_test99_manifest.json"
    manifest_file.write_text(json.dumps(manifest_data))

    try:
        response = client.get("/manifest/lt_test99")
        assert response.status_code == 200
        assert response.json()["instance_id"] == "lt_test99"
    finally:
        api_module.OUTPUT_DIR = original


def test_manifest_response_is_valid_json(tmp_path):
    import lower_third.api as api_module
    original = api_module.OUTPUT_DIR
    api_module.OUTPUT_DIR = tmp_path

    manifest_data = {"instance_id": "lt_xyz", "loop": True}
    (tmp_path / "lt_xyz_manifest.json").write_text(json.dumps(manifest_data))

    try:
        response = client.get("/manifest/lt_xyz")
        data = response.json()
        assert isinstance(data, dict)
    finally:
        api_module.OUTPUT_DIR = original
