import json
from pathlib import Path

from lower_third.parser.prompt_schema import LowerThirdSpec
from lower_third.qc.validator import QCReport


def write_manifest(
    spec: LowerThirdSpec,
    video_path: Path,
    qc_report: QCReport,
    output_dir: Path,
) -> dict:
    manifest = {
        "schema_version": "2.0",
        "instance_id": spec.instance_id,
        "asset": str(video_path),
        "format": "webm_rgba_vp9",
        "resolution": [1920, 1080],
        "fps": 30,
        "duration_ms": spec.motion.total_ms,
        "timecode_in": None,
        "timecode_out": None,
        "loop": spec.motion.loop.enabled,
        "qc": {
            "passed": qc_report.passed,
            "warnings": qc_report.warnings,
            "min_contrast_ratio": round(qc_report.min_contrast_ratio, 2),
        },
        "ffmpeg_overlay": "overlay=0:0:format=auto:enable='between(t,{IN},{OUT})'",
        "color_space": "bt709",
    }

    out_path = Path(output_dir) / f"{spec.instance_id}_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2))

    return manifest
