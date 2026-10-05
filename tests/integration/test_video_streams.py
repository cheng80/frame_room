"""Synthetic local ffmpeg media; no generation, network or user-file writes."""
import hashlib
import json
import shutil
import subprocess
from types import SimpleNamespace

from PIL import Image
import pytest

from adapters.spritegen import video_probe as probe
from services.api import store, videos


def ffmpeg(*args):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe unavailable")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)],
                   capture_output=True, check=True, timeout=30)


def make_video(path, *, size="64x48", fps="24", count=24):
    ffmpeg("-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}",
           "-frames:v", count, "-c:v", "libx264", "-preset", "ultrafast", path)
    return path


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return make_video(tmp_path_factory.mktemp("stream-video") / "source.mp4")


def test_cfr_probe_and_api_share_metadata_without_modifying_original(clip):
    original = clip.read_bytes()
    timing = probe.read_timing(clip)
    assert timing["streamIndex"] == 0
    assert (timing["width"], timing["height"], timing["frameCount"]) == (64, 48, 24)
    assert timing["fps"] == 24 and timing["constantFrameRate"] is True
    assert timing["timesMs"] == pytest.approx([i * 1000 / 24 for i in range(25)], abs=.001)
    metadata = videos.validate(original, "../original.mp4")
    for key in ("width", "height", "fps", "frameCount", "streamIndex", "constantFrameRate"):
        assert metadata[key] == timing[key]
    assert metadata["durationMs"] == round(timing["durationMs"]) == 1000
    assert metadata["sha256"] == hashlib.sha256(original).hexdigest()
    assert metadata["originalFilename"] == "original.mp4"
    assert clip.read_bytes() == original


def test_long_audio_and_cover_do_not_determine_video_timing_or_extraction(clip, tmp_path):
    cover = tmp_path / "cover.png"
    Image.new("RGB", (16, 16), "yellow").save(cover)
    mixed = tmp_path / "cover-audio-first.mp4"
    # Request the cover first. MOV/MP4 muxers normally serialize attached cover
    # pictures last, irrespective of -map order. The moving video is still not
    # stream 0 here (audio precedes it), exercising an absolute stream index.
    ffmpeg("-i", cover, "-i", clip, "-f", "lavfi", "-i", "sine=duration=16",
           "-map", "0:v", "-map", "2:a", "-map", "1:v", "-c:v:0", "png",
           "-disposition:v:0", "attached_pic", "-c:v:1", "copy", "-c:a", "aac", mixed)
    raw = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(mixed)],
        capture_output=True, text=True, check=True, timeout=15).stdout)
    assert float(raw["format"]["duration"]) >= 16
    covers = [s for s in raw["streams"] if s.get("disposition", {}).get("attached_pic")]
    assert len(covers) == 1
    before = mixed.read_bytes()
    timing = probe.read_timing(mixed)
    assert timing["streamIndex"] != 0 and timing["streamIndex"] != covers[0]["index"]
    assert timing["durationMs"] == 1000 and timing["frameCount"] == 24
    assert (timing["width"], timing["height"]) == (64, 48)
    assert videos.validate(before, mixed.name)["streamIndex"] == timing["streamIndex"]
    # The exact selector returned by the helper must extract the moving frames.
    actual, expected = tmp_path / "selected.png", tmp_path / "expected.png"
    ffmpeg("-i", mixed, "-map", f"0:{timing['streamIndex']}", "-frames:v", "1", actual)
    ffmpeg("-i", clip, "-map", "0:0", "-frames:v", "1", expected)
    with Image.open(actual) as a, Image.open(expected) as e:
        assert a.size == e.size and a.tobytes() == e.tobytes()
    assert mixed.read_bytes() == before


def test_vfr_keeps_actual_display_boundaries(tmp_path):
    manifest = tmp_path / "frames.txt"
    lines = []
    for i, duration in enumerate((.04, .12, .08, .16, .04, .12)):
        image = tmp_path / f"source-{i}.png"
        Image.new("RGB", (32, 32), (i * 30, 40, 90)).save(image)
        lines.extend([f"file '{image}'", f"duration {duration}"])
    lines.append(f"file '{image}'")
    manifest.write_text("\n".join(lines) + "\n")
    path = tmp_path / "vfr.mp4"
    ffmpeg("-safe", "0", "-f", "concat", "-i", manifest, "-fps_mode", "vfr",
           "-c:v", "libx264rgb", "-crf", "0", path)
    timing = probe.read_timing(path)
    assert timing["constantFrameRate"] is False
    assert timing["frameCount"] == 7
    assert timing["timesMs"] == pytest.approx([0, 40, 160, 240, 400, 440, 560, 600])
    assert timing["durationMs"] == 600
    assert videos.validate(path.read_bytes(), path.name)["durationMs"] == 600


def test_nonzero_video_start_is_normalized_without_shortening_duration(tmp_path):
    path = tmp_path / "offset.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=32x32:rate=8", "-frames:v", "8",
           "-vf", "setpts=PTS+2/TB", "-fps_mode", "passthrough", "-c:v", "libx264", path)
    timing = probe.read_timing(path)
    assert timing["timesMs"] == pytest.approx([i * 125 for i in range(9)])
    assert timing["durationMs"] == 1000 and timing["constantFrameRate"] is True


@pytest.mark.parametrize("options", [
    {"size": "2050x16", "count": 1},
    {"fps": "61", "count": 61},
    {"fps": "5", "count": 76},
    {"fps": "60", "count": 601},
])
def test_real_media_limits_match_api(tmp_path, options):
    path = make_video(tmp_path / "oversized.mp4", **options)
    with pytest.raises(ValueError) as invalid:
        probe.read_timing(path)
    assert invalid.value.code == "VIDEO_DIMENSIONS"
    with pytest.raises(store.AppError) as api:
        videos.validate(path.read_bytes(), path.name)
    assert api.value.code == "VIDEO_DIMENSIONS" and api.value.status == 413


def test_muxer_padding_below_15_point_1_seconds_is_allowed(tmp_path):
    path = make_video(tmp_path / "padding.mp4", count=361)
    timing = probe.read_timing(path)
    assert 15000 < timing["durationMs"] <= 15100
    assert timing["frameCount"] == 361


def test_real_audio_only_has_no_moving_video(tmp_path):
    path = tmp_path / "audio-only.mp4"
    ffmpeg("-f", "lavfi", "-i", "sine=duration=1", "-c:a", "aac", path)
    with pytest.raises(probe.VideoProbeError) as invalid:
        probe.read_timing(path)
    assert invalid.value.code == "VIDEO_DECODE"


def fake_probe(monkeypatch, tmp_path, *, streams=None, rows=None):
    """Malformed/order cases that MOV muxers cannot serialize faithfully."""
    path = tmp_path / "metadata-fixture.mp4"
    path.write_bytes(b"synthetic metadata fixture")
    stream = {"index": 7, "codec_type": "video", "width": 32, "height": 32,
              "avg_frame_rate": "8/1", "r_frame_rate": "8/1", "duration": "0.25"}
    if streams is None:
        streams = [{"index": 0, "codec_type": "video", "disposition": {"attached_pic": 1}},
                   {"index": 3, "codec_type": "audio"}, stream]
    if rows is None:
        rows = [{"stream_index": 7, "width": 32, "height": 32,
                 "best_effort_timestamp_time": str(i / 8), "duration_time": "0.125"} for i in range(2)]
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(
            {"frames": rows} if "-show_frames" in args else {"streams": streams}))
    monkeypatch.setattr(probe.shutil, "which", lambda _: "/synthetic/ffprobe")
    monkeypatch.setattr(probe.subprocess, "run", run)
    return path, stream, rows, calls


def test_cover_first_selector_protocol_whitelist_and_timeouts(monkeypatch, tmp_path):
    path, _, _, calls = fake_probe(monkeypatch, tmp_path)
    timing = probe.read_timing(path)
    assert timing["streamIndex"] == 7 and timing["frameCount"] == 2
    assert len(calls) == 2
    assert "-select_streams" not in calls[0][0]
    second = calls[1][0]
    assert second[second.index("-select_streams") + 1] == "7"
    for (args, kwargs), timeout in zip(calls, (15, 60)):
        assert args[args.index("-protocol_whitelist") + 1] == "file,pipe"
        assert kwargs["timeout"] == timeout and args[-1] == str(path.resolve())


@pytest.mark.parametrize("mutation", [
    lambda s, r: r[0].pop("best_effort_timestamp_time"),
    lambda s, r: r[1].update(best_effort_timestamp_time="nan"),
    lambda s, r: r[1].update(best_effort_timestamp_time="0"),
    lambda s, r: r[1].update(stream_index=0),
    lambda s, r: r[1].update(width=64),
    lambda s, r: s.update(duration="nan"),
])
def test_invalid_timestamp_and_stream_metadata_raise_value_error(monkeypatch, tmp_path, mutation):
    path, stream, rows, _ = fake_probe(monkeypatch, tmp_path)
    mutation(stream, rows)
    with pytest.raises(probe.VideoProbeError) as invalid:
        probe.read_timing(path)
    assert isinstance(invalid.value, ValueError) and invalid.value.code == "VIDEO_DECODE"


def test_vfr_high_rate_burst_cannot_hide_behind_low_average(monkeypatch, tmp_path):
    path, _, rows, _ = fake_probe(monkeypatch, tmp_path)
    rows[1]["best_effort_timestamp_time"] = "0.01"
    with pytest.raises(probe.VideoProbeError) as invalid:
        probe.read_timing(path)
    assert invalid.value.code == "VIDEO_DIMENSIONS"


def test_only_attached_pictures_are_rejected_without_decoding(monkeypatch, tmp_path):
    path, _, _, calls = fake_probe(monkeypatch, tmp_path, streams=[
        {"index": 0, "codec_type": "video", "disposition": {"attached_pic": 1}}])
    with pytest.raises(probe.VideoProbeError):
        probe.read_timing(path)
    assert len(calls) == 1


def test_missing_ffprobe_and_timeout_are_classified(monkeypatch, clip):
    monkeypatch.setattr(probe.shutil, "which", lambda _: None)
    with pytest.raises(store.AppError) as dependency:
        videos.validate(clip.read_bytes(), clip.name)
    assert dependency.value.code == "VIDEO_DEPENDENCY" and dependency.value.status == 424
    monkeypatch.setattr(probe.shutil, "which", lambda _: "/synthetic/ffprobe")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(probe.subprocess, "run", timeout)
    with pytest.raises(ValueError):
        probe.read_timing(clip)
    with pytest.raises(store.AppError) as decode:
        videos.validate(clip.read_bytes(), clip.name)
    assert decode.value.code == "VIDEO_DECODE"


def test_byte_limit_format_and_nonlocal_paths_reject_before_probe(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "MAX_BYTES", 16)
    path = tmp_path / "large.mp4"
    path.write_bytes(b"x" * 17)
    with pytest.raises(probe.VideoProbeError) as limit:
        probe.read_timing(path)
    assert limit.value.code == "VIDEO_LIMIT"
    monkeypatch.setattr(videos, "MAX_BYTES", 16)
    with pytest.raises(store.AppError) as api:
        videos.validate(b"x" * 17, path.name)
    assert api.value.code == "VIDEO_LIMIT" and api.value.status == 413
    with pytest.raises(store.AppError) as bad_format:
        videos.validate(b"not MP4", "image.png")
    assert bad_format.value.code == "VIDEO_FORMAT"
    with pytest.raises(probe.VideoProbeError):
        probe.read_timing("https://invalid.example/clip.mp4")
