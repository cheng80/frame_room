"""Bounded local probe shared by video import, timing and frame extraction.

``streamIndex`` is the absolute input stream index: use ``-map 0:<index>``
when extracting. ``timesMs`` contains normalized display timestamps plus the
exclusive end boundary; audio and attached cover pictures never contribute.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import subprocess

MAX_BYTES = 64 * 1024 * 1024
MAX_DURATION_MS = 15_100
MAX_DIMENSION = 2048
MAX_FPS = 60
MAX_FRAMES = 600


class VideoProbeError(ValueError):
    """Invalid/unreadable media, with an API-compatible error classification."""

    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code


def _probe(binary: str, path: Path, options: list[str], timeout: int) -> dict:
    try:
        result = subprocess.run(
            [binary, "-v", "error", "-protocol_whitelist", "file,pipe",
             *options, "-of", "json", str(path)],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode:
            raise VideoProbeError("VIDEO_DECODE", "ffprobe failed")
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError("invalid ffprobe response")
        return payload
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise VideoProbeError("VIDEO_DECODE", "Cannot read video metadata/frames") from exc


def _number(value) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite video metadata")
    return number


def _rate(stream: dict) -> float:
    # avg_frame_rate is meaningful for VFR too; r_frame_rate can be a guessed
    # common denominator of timestamps, not the actual number of frames/sec.
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            num, den = stream[key].split("/")
            value = _number(num) / _number(den)
            if value > 0 and math.isfinite(value):
                return value
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            continue
    raise ValueError("missing video frame rate")


def _optional_duration(value) -> float:
    if value in (None, "", "N/A"):
        return 0.0
    duration = _number(value) * 1000
    if duration < 0:
        raise ValueError("negative video duration")
    return duration


def _limits(condition: bool) -> None:
    if not condition:
        raise VideoProbeError("VIDEO_DIMENSIONS", "Video exceeds 15.1s/2048px/60fps/600 frames")


def read_timing(path: Path | str) -> dict:
    """Read the first non-cover video stream without changing source bytes.

    Raises ``VideoProbeError`` (a ``ValueError``) for invalid media, exceeded
    limits, missing ffprobe or timeout. Streams are inspected before decoding
    frames, with the same local-only protocol whitelist on both probe calls.
    """
    binary = shutil.which("ffprobe")
    if not binary:
        raise VideoProbeError("VIDEO_DEPENDENCY", "ffprobe is required")
    try:
        source = Path(path).resolve(strict=True)
        if not source.is_file():
            raise ValueError("video must be a local file")
        if source.stat().st_size > MAX_BYTES:
            raise VideoProbeError("VIDEO_LIMIT", "Video exceeds 64 MiB")
        metadata = _probe(binary, source, [
            "-show_entries",
            "stream=index,codec_type,width,height,avg_frame_rate,r_frame_rate,nb_frames,duration:"
            "stream_disposition=attached_pic",
        ], timeout=15)
        streams = metadata.get("streams") or []
        stream = next((item for item in streams if item.get("codec_type") == "video"
                       and not int((item.get("disposition") or {}).get("attached_pic", 0))), None)
        if stream is None:
            raise ValueError("no moving video stream")
        index = int(stream["index"])
        if index < 0:
            raise ValueError("invalid video stream index")
        width, height, fps = int(stream["width"]), int(stream["height"]), _rate(stream)
        duration = _optional_duration(stream.get("duration"))
        _limits(1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION
                and 1 <= fps <= MAX_FPS and duration <= MAX_DURATION_MS)
        if str(stream.get("nb_frames", "")).isdigit():
            _limits(1 <= int(stream["nb_frames"]) <= MAX_FRAMES)

        decoded = _probe(binary, source, [
            "-select_streams", str(index), "-show_frames", "-show_entries",
            "frame=stream_index,width,height,best_effort_timestamp_time,duration_time,pkt_duration_time",
        ], timeout=60)
        rows = decoded.get("frames") or []
        _limits(1 <= len(rows) <= MAX_FRAMES)
        if any(int(row["stream_index"]) != index for row in rows):
            raise ValueError("decoded frames do not match selected video stream")
        # Dynamic resolution is not supported by the common sprite canvas.
        if any(int(row["width"]) != width or int(row["height"]) != height for row in rows):
            raise ValueError("video frame size changes during playback")
        pts = [_number(row["best_effort_timestamp_time"]) * 1000 for row in rows]
        pts = [value - pts[0] for value in pts]
        if any(b <= a for a, b in zip(pts, pts[1:])):
            raise ValueError("non-monotonic video timestamps")
        last_duration = (_optional_duration(rows[-1].get("duration_time"))
                         or _optional_duration(rows[-1].get("pkt_duration_time")))
        # Stream duration is a length, so do not subtract its start timestamp.
        # Missing final packet duration falls back to the video's own boundary.
        end = max(duration, pts[-1] + last_duration)
        if end <= pts[-1]:
            end = pts[-1] + 1000 / fps
        _limits(0 < end <= MAX_DURATION_MS)
        times = pts + [end]
        # Timestamp rounding can be a microsecond; do not accept a real >60fps
        # burst just because a VFR stream's average rate is lower than 60.
        _limits(all(b - a >= 1000 / MAX_FPS - 0.01 for a, b in zip(times, times[1:])))
        cfr = all(abs((b - a) - 1000 / fps) < 1.5 for a, b in zip(times, times[1:]))
        return {"width": width, "height": height, "fps": fps, "frameCount": len(rows),
                "durationMs": end, "timesMs": times, "constantFrameRate": cfr,
                "streamIndex": index}
    except VideoProbeError:
        raise
    except (OSError, KeyError, IndexError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise VideoProbeError("VIDEO_DECODE", "Invalid moving-video metadata or timestamps") from exc
