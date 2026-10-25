"""Video Quality Control (QC) Guardrail Checker."""

import os
import re
import subprocess
from typing import Dict, Any, List, Optional
import imageio_ffmpeg

from src.video.models import VideoRunResult


def inspect_media_file(video_path: str) -> Dict[str, Any]:
    """
    Inspect video file properties using imageio_ffmpeg binary.
    Returns dictionary with width, height, duration_sec, has_audio, file_size_mb.
    """
    if not os.path.exists(video_path):
        return {"error": f"File does not exist: {video_path}"}

    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    exe = imageio_ffmpeg.get_ffmpeg_exe()

    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-i", video_path],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        info = proc.stderr
    except Exception as e:
        return {"error": f"Failed to inspect media: {e}"}

    # Extract Duration: 00:00:25.40
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", info)
    duration_sec = 0.0
    if duration_match:
        h, m, s = duration_match.groups()
        duration_sec = int(h) * 3600 + int(m) * 60 + float(s)

    # Extract Resolution: e.g. 1080x1920
    res_match = re.search(r",\s*(\d{3,4})x(\d{3,4})", info)
    width = int(res_match.group(1)) if res_match else 0
    height = int(res_match.group(2)) if res_match else 0

    # Extract Audio Stream presence
    has_audio = "Audio:" in info

    return {
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "has_audio": has_audio,
        "file_size_mb": file_size_mb,
    }


def verify_video_quality(
    video_path: str,
    target_duration_sec: Optional[float] = None,
    tolerance_sec: float = 4.0,
    max_size_mb: float = 50.0,
    expected_width: int = 1080,
    expected_height: int = 1920,
) -> VideoRunResult:
    """
    Guardrail QC Check:
    1. Video file exists and non-empty
    2. Exact target aspect ratio/resolution (1080x1920)
    3. File size within limit (< 50MB)
    4. Audio stream is present and valid
    5. Duration matches target duration within tolerance
    """
    issues: List[str] = []

    if not os.path.exists(video_path):
        return VideoRunResult(
            ok=False,
            video_path=video_path,
            issues=[f"Video file does not exist: {video_path}"],
        )

    props = inspect_media_file(video_path)
    if "error" in props:
        return VideoRunResult(
            ok=False,
            video_path=video_path,
            issues=[props["error"]],
        )

    width = props["width"]
    height = props["height"]
    duration = props["duration_sec"]
    has_audio = props["has_audio"]
    file_size_mb = props["file_size_mb"]

    # 1. Resolution Check
    if width != expected_width or height != expected_height:
        issues.append(
            f"Invalid resolution: got {width}x{height}, expected {expected_width}x{expected_height}."
        )

    # 2. File Size Check
    if file_size_mb > max_size_mb:
        issues.append(
            f"File size {file_size_mb:.2f}MB exceeds maximum limit of {max_size_mb}MB."
        )
    elif file_size_mb < 0.01:
        issues.append("File is corrupt or virtually empty (< 10KB).")

    # 3. Audio Stream Check
    if not has_audio:
        issues.append("Missing audio stream: video is completely mute.")

    # 4. Duration Check
    if target_duration_sec is not None:
        diff = abs(duration - target_duration_sec)
        if diff > tolerance_sec:
            issues.append(
                f"Video duration {duration:.1f}s deviates from target {target_duration_sec:.1f}s by {diff:.1f}s (tolerance: ±{tolerance_sec}s)."
            )

    ok = len(issues) == 0
    return VideoRunResult(
        ok=ok,
        video_path=video_path,
        duration_sec=duration,
        file_size_mb=round(file_size_mb, 2),
        issues=issues,
    )
