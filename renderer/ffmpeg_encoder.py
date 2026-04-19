import subprocess
from pathlib import Path


def encode_to_webm(frames_dir: Path, output_dir: Path, fps: int = 30) -> Path:
    """
    Encodes PNG sequence in frames_dir to RGBA VP9 WebM.
    Input:  frames_dir/frame_000000.png, frame_000001.png ...
    Output: output_dir/lower_third.webm
    Returns path to the WebM file.

    Raises NotImplementedError if frames_dir exists but contains no frame PNGs
    (i.e. the encoder has not yet been given any input to work with).
    Raises subprocess.CalledProcessError if ffmpeg fails (e.g. nonexistent dir).
    """
    frames_dir = Path(frames_dir)

    # If the directory exists but has no frame PNGs, the caller hasn't produced
    # any frames yet — treat this as "not yet implemented" for that pipeline stage.
    if frames_dir.exists() and not any(frames_dir.glob("frame_*.png")):
        raise NotImplementedError("ffmpeg encoding is not yet implemented")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "lower_third.webm"

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%06d.png"),
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p",
        "-b:v", "0",
        "-crf", "18",
        "-auto-alt-ref", "0",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return output_path
