"""Local synthetic video fixtures, not AI generation or remote provider tests."""
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageSequence
import pytest

from adapters.spritegen import video_processing as vp


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_clip(root, *, count=37, fps="24", moving=True, key=(255, 0, 255), varying_height=False, period=16):
    """Tiny lossless RGB MP4: ffmpeg does real decoding/keying in every test."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe unavailable")
    root.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        im = Image.new("RGB", (64, 80), key)
        draw = ImageDraw.Draw(im)
        phase = i * math.tau / period
        dy = round(3 * math.sin(phase)) if moving else 0
        top = 10 if not varying_height or i == 0 else 18
        draw.rectangle((25, top + dy, 39, 52 + dy), fill=(30, 40, 100))
        dx = round(8 * math.sin(phase)) if moving else 0
        draw.rectangle((23 + dx, 50 + dy, 28 + dx, 69 + dy), fill=(170, 70, 20))
        draw.rectangle((37 - dx, 50 + dy, 42 - dx, 69 + dy), fill=(40, 170, 200))
        # A tiny held item outside the main body must survive adapter processing.
        draw.rectangle((47, 28 + dy, 49, 40 + dy), fill=(240, 230, 30))
        im.save(root / f"input-{i:04d}.png")
    path = root / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-framerate", fps, "-i", str(root / "input-%04d.png"),
                    "-c:v", "libx264rgb", "-crf", "0", "-preset", "ultrafast", "-y", str(path)],
                   check=True, capture_output=True, timeout=30)
    return path


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return make_clip(tmp_path_factory.mktemp("video-fixture"), varying_height=True)


def test_prepare_alpha_crops_and_nearest_composites_without_black_background(tmp_path):
    source, dest = tmp_path / "source.png", tmp_path / "prepared.png"
    im = Image.new("RGBA", (64, 128), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((7, 24, 52, 117), fill=(90, 120, 180, 255))
    im.putpixel((8, 24), (200, 160, 100, 128))
    im.save(source)
    before = source.read_bytes()
    result = vp.prepare_still(source, dest, {"key": "auto"})
    assert source.read_bytes() == before
    assert result["crop"] == [7, 24, 53, 118]
    assert result["scale"] == 4
    assert result["scaledSize"] == [184, 376]
    assert result["key"] == "magenta"
    with Image.open(dest) as actual:
        assert actual.mode == "RGB" and actual.size == (512, 512)
        assert actual.getpixel((0, 0)) == (255, 0, 255)
        expected = Image.new("RGBA", (512, 512), (255, 0, 255, 255))
        expected.alpha_composite(im.crop((7, 24, 53, 118)).resize((184, 376), Image.Resampling.NEAREST), tuple(result["offset"]))
        assert actual.tobytes() == expected.convert("RGB").tobytes()
    assert vp.prepare_still(source, dest, {"key": "auto"}) == result
    with pytest.raises(vp.VideoProcessingError, match="다른 경로"):
        vp.prepare_still(source, source, {})
    im.putpixel((7, 24), (20, 30, 40, 255))
    im.save(source)
    prepared = dest.read_bytes()
    with pytest.raises(vp.VideoProcessingError) as error:
        vp.prepare_still(source, dest, {})
    assert error.value.code == "VIDEO_DESTINATION_EXISTS"
    assert dest.read_bytes() == prepared


@pytest.mark.parametrize("kind,color", [("green", (8, 166, 25)), ("magenta", (200, 8, 201)), ("cyan", (0, 220, 220)), ("white", (255, 255, 255))])
def test_prepare_opaque_engine_normalization(tmp_path, kind, color):
    source = tmp_path / "flat.png"
    im = Image.new("RGB", (48, 64), color)
    ImageDraw.Draw(im).rectangle((16, 12, 32, 51), fill=(50, 35, 45))
    im.save(source)
    before = sha(source)
    result = vp.prepare_still(source, tmp_path / "prepared.png", {"key": kind})
    assert sha(source) == before
    assert result["key"] == ("magenta" if kind == "white" else kind)
    assert result["cutout"]["alpha_zero_pct"] > 0
    assert result["sourceHadTransparency"] is False
    with Image.open(result["path"]) as prepared:
        assert prepared.getpixel((0, 0)) == tuple(result["keyRgb"])
        assert prepared.getpixel((256, 256)) != tuple(result["keyRgb"])


def test_prepare_refuses_nonflat_empty_and_unsupported_black(tmp_path):
    source = tmp_path / "input.png"
    Image.new("RGBA", (16, 16)).save(source)
    with pytest.raises(vp.VideoProcessingError) as empty:
        vp.prepare_still(source, tmp_path / "empty.png", {})
    assert empty.value.code == "VIDEO_EMPTY_STILL"
    Image.new("RGB", (16, 16), "black").save(source)
    with pytest.raises(vp.VideoProcessingError) as black:
        vp.prepare_still(source, tmp_path / "black.png", {})
    assert black.value.code == "VIDEO_BACKGROUND_UNSUPPORTED"
    image = Image.new("RGB", (16, 16), "magenta")
    image.putpixel((0, 0), (0, 255, 0))
    image.save(source)
    with pytest.raises(vp.VideoProcessingError) as nonflat:
        vp.prepare_still(source, tmp_path / "bad.png", {})
    assert nonflat.value.code == "VIDEO_STILL_FAILED"


@pytest.mark.parametrize("state", ["jump", "attack"])
def test_prepare_state_profile_keeps_extra_motion_room(tmp_path, state):
    source = tmp_path / "alpha.png"
    im = Image.new("RGBA", (64, 128))
    ImageDraw.Draw(im).rectangle((7, 24, 52, 117), fill=(30, 40, 100, 255))
    im.save(source)
    result = vp.prepare_still(source, tmp_path / "prepared.png", {"state": state, "key": "green"})
    assert result["key"] == "magenta"  # Effective input key wins over an alpha image's request.
    assert min(result["width"], result["height"]) >= 512
    assert result["height"] > 512 and result["offset"][1] > 64
    assert result["scale"] == 4 and result["scaledSize"] == [184, 376]
    assert result["canvas"]["shape"] == ("tall" if state == "jump" else "wide")


def test_prompt_lite_calm_view_gear_and_custom_motion():
    lite = vp.build_motion_prompt({"model": "grok-imagine-video-1.5-lite", "direction": "back"})
    assert "slow, relaxed, unhurried walk" in lite
    assert "face stays hidden" in lite and "moving farther away" in lite
    assert "same hand" in lite and "no zoom" in lite
    pro = vp.build_motion_prompt({"state": "walk", "direction": "side", "facing": "left"})
    assert "facing left" in pro and "slow, relaxed" not in pro
    custom = vp.build_motion_prompt({"model": "grok-imagine-video-1.5-lite", "direction": "front", "motionPrompt": "  A high-knee march.  "})
    assert "A high-knee march." in custom and "slow, relaxed" not in custom
    assert "facing the viewer" in custom and "Stay in place" in custom
    assert "one melee attack" in vp.build_motion_prompt({"state": "attack"})
    assert "Return to the starting pose" in vp.build_motion_prompt({"state": "idle"})


def test_full_manual_timing_canvas_anchor_cache_and_preview(clip, tmp_path, monkeypatch):
    work = tmp_path / "processing"
    source_before = sha(clip)
    progress = []
    full = vp.process_clip(clip, work, {"loopMode": "full", "maxFrames": 4}, lambda *args: progress.append(args))
    assert [stage for stage, _ in progress] == ["extract", "select_cycle", "complete"]
    assert full["source"]["frameCount"] == 37 and full["source"]["fps"] == 24
    assert full["source"]["width"] == 64 and full["source"]["height"] == 80
    assert [f["sourceFrameIndex"] for f in full["frames"]] == [0, 9, 18, 27]
    assert sum(f["durationMs"] for f in full["frames"]) == 1542
    assert full["selection"]["loop"] is False
    assert full["standingHeight"] == 60 and full["anchor"]["y"] == 70
    raw = sorted(Path(full["extraction"]["rawDir"]).glob("*.png"))
    keyed = sorted(Path(full["extraction"]["keyedDir"]).glob("*.png"))
    assert len(raw) == len(keyed) == 37
    originals = {p: (sha(p), p.stat().st_mtime_ns) for p in [*raw, *keyed]}
    def no_extract(*args, **kwargs):
        pytest.fail("completed extraction must be reused")
    monkeypatch.setattr(vp, "_run_extraction", no_extract)
    manual = vp.process_clip(clip, work, {"loopMode": "manual", "startFrame": 5, "endFrame": 34, "maxFrames": 4,
                                         "bodyHeight": 32, "cellWidth": 32, "cellHeight": 32})
    assert manual["standingHeight"] == full["standingHeight"] and manual["anchor"] == full["anchor"]
    assert manual["anchorSourceFrameIndex"] == 0
    assert manual["selection"]["endFrame"] == 34 and manual["selection"]["loop"] is True
    assert sum(f["durationMs"] for f in manual["frames"]) == 1208
    for f in manual["frames"]:
        assert f["sourceTimeMs"] == pytest.approx(f["sourceFrameIndex"] * 1000 / 24, abs=0.001)
        with Image.open(f["rawPath"]) as a, Image.open(f["keyedPath"]) as b:
            assert a.size == b.size == (64, 80)
            assert b.getchannel("A").getextrema()[0] == 0
            # Detached equipment survives. No per-frame crop/cleanup/normalization.
            assert np.asarray(b)[20:48, 47:50, 3].max() == 255
    assert originals == {p: (sha(p), p.stat().st_mtime_ns) for p in originals}
    assert sha(clip) == source_before
    assert all(not Path(name).is_absolute() and (work / name).is_file() for name in manual["files"])
    with Image.open(manual["previewPath"]) as gif:
        assert gif.info["loop"] == 0
        total = sum(f.info["duration"] for f in ImageSequence.Iterator(gif))
        assert total == 1210
    with Image.open(full["previewPath"]) as gif:
        assert "loop" not in gif.info
    assert json.loads((work / "video-processing.json").read_text())["status"] == "complete"


@pytest.mark.parametrize("params", [
    {"maxFrames": 3}, {"maxFrames": 65}, {"maxFrames": True},
    {"loopMode": "manual", "startFrame": -1, "endFrame": 4},
    {"loopMode": "manual", "startFrame": 5, "endFrame": 5},
    {"loopMode": "manual", "startFrame": 0, "endFrame": 38},
    {"loopMode": "manual", "startFrame": 0, "endFrame": 4.5},
])
def test_strict_ranges_no_implicit_clamp(clip, tmp_path, params):
    with pytest.raises(vp.VideoProcessingError) as exc:
        vp.process_clip(clip, tmp_path, params)
    assert exc.value.code in ("VIDEO_INVALID_PARAMS", "VIDEO_INVALID_RANGE")
    assert isinstance(exc.value.message, str) and isinstance(exc.value.details, dict)


def test_no_periodic_match_keeps_extraction_and_manual_recovers(tmp_path, monkeypatch):
    clip = make_clip(tmp_path / "fixture", count=32, moving=False)
    work = tmp_path / "work"
    with pytest.raises(vp.VideoProcessingError) as refused:
        vp.process_clip(clip, work, {"state": "walk", "loopMode": "auto"})
    error = refused.value
    assert error.code == "VIDEO_NO_PERIODIC_MATCH"
    assert error.details["regenerationRequired"] is False
    assert error.details["stage"] == "select_cycle"
    assert len(list(Path(error.details["rawDir"]).glob("*.png"))) == 32
    assert (Path(error.details["artifactDir"]) / "failure.report.json").is_file()
    assert error.details["metrics"]
    monkeypatch.setattr(vp, "_run_extraction", lambda *a: pytest.fail("must reuse keyed frames after selection refusal"))
    manual = vp.process_clip(clip, work, {"loopMode": "manual", "startFrame": 0, "endFrame": 32})
    assert len(manual["frames"]) == 32
    assert sum(f["durationMs"] for f in manual["frames"]) == 1333
    assert manual["preview"]["encodedFrameCount"] < 32  # Identical frames merged, durations retained.


@pytest.mark.parametrize("state", ["walk", "jump"])
def test_auto_loop_real_local_periodic_fixture(tmp_path, state):
    clip = make_clip(tmp_path / "fixture", count=64)
    result = vp.process_clip(clip, tmp_path / "work", {"state": state, "key": "magenta"})
    assert result["selection"]["loop"] is True
    assert result["selection"]["periodicity"] >= 0.15
    assert result["selection"]["seamRatio"] <= 2
    assert len(result["frames"]) <= 32
    assert result["standingHeight"] == 60


def test_interrupted_extraction_does_not_remove_previous_raw(clip, tmp_path, monkeypatch):
    original = vp._run_extraction
    def interrupted(source, directory, options, timing):
        (directory / "raw").mkdir()
        (directory / "raw" / "frame-0001.png").write_bytes(b"interrupted-evidence")
        raise SystemExit("interrupted local extraction")
    monkeypatch.setattr(vp, "_run_extraction", interrupted)
    with pytest.raises(vp.VideoProcessingError):
        vp.process_clip(clip, tmp_path, {"loopMode": "full"})
    retained = list(tmp_path.glob("extractions/*/attempt-*/raw/frame-0001.png"))[0]
    monkeypatch.setattr(vp, "_run_extraction", original)
    result = vp.process_clip(clip, tmp_path, {"loopMode": "full"})
    assert retained.read_bytes() == b"interrupted-evidence"
    assert Path(result["frames"][0]["rawPath"]) != retained


def test_spill_reference_and_cyan(clip, tmp_path):
    prepared = tmp_path / "reference.png"
    vp.prepare_still(clip.parent / "input-0000.png", prepared, {})
    result = vp.process_clip(clip, tmp_path / "auto-spill", {"loopMode": "full", "referencePath": str(prepared)})
    assert result["extraction"]["spill"]["mode"] == "full"
    cyan = make_clip(tmp_path / "cyan", count=4, key=(0, 255, 255))
    result = vp.process_clip(cyan, tmp_path / "cyan-work", {"loopMode": "full", "key": "cyan"})
    assert len(result["frames"]) == 4
    with Image.open(result["frames"][0]["keyedPath"]) as image:
        assert image.getpixel((0, 0)) == (0, 0, 0, 0)


def make_spill_fixture(root, *, key="magenta", variable=False, material=None):
    """Synthetic brown subject with optional genuine, faint key-coloured cloth."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe unavailable")
    root.mkdir(parents=True, exist_ok=True)
    rgba = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    ImageDraw.Draw(rgba).rectangle((16, 16, 79, 79), fill=(160, 100, 40, 255))
    if material:
        ImageDraw.Draw(rgba).rectangle((36, 36, 59, 59), fill=(*material, 255))
    reference = root / "alpha.png"
    rgba.save(reference)
    canvas = Image.new("RGBA", rgba.size, (*vp._engine("frames.cutout").KEY_TARGETS[key], 255))
    canvas.alpha_composite(rgba)
    opaque = root / "canvas.png"
    canvas.convert("RGB").save(opaque)
    clip = root / "source.mp4"
    if variable:
        manifest = root / "vfr.txt"
        manifest.write_text("".join(f"file '{opaque}'\nduration {duration}\n" for duration in (.04, .12, .08, .16))
                            + f"file '{opaque}'\n")
        inputs = ["-safe", "0", "-f", "concat", "-i", str(manifest), "-fps_mode", "vfr"]
    else:
        inputs = ["-loop", "1", "-framerate", "24", "-i", str(opaque), "-frames:v", "5"]
    subprocess.run(["ffmpeg", "-v", "error", *inputs, "-c:v", "libx264rgb", "-crf", "0",
                    "-preset", "ultrafast", "-y", str(clip)], check=True, capture_output=True, timeout=30)
    return clip, reference, opaque


@pytest.mark.parametrize("variable", [False, True], ids=["cfr", "vfr"])
@pytest.mark.parametrize("key", ["magenta", "green"])
def test_transparent_brown_reference_uses_video_key_and_matches_opaque(tmp_path, variable, key):
    clip, reference, opaque = make_spill_fixture(tmp_path / "fixture", key=key, variable=variable)
    before = sha(reference)
    outputs = []
    for label, ref in (("rgb", opaque), ("rgba", reference)):
        result = vp.process_clip(clip, tmp_path / label, {"loopMode": "full", "maxFrames": 64, "referencePath": str(ref)})
        decision = result["extraction"]["spill"]
        assert result["source"]["constantFrameRate"] is (not variable)
        assert decision["mode"] == "full" and decision["key"] == key
        assert decision["keySource"] == "first-video-frame"
        assert decision["referenceSourceSha256"] == sha(ref)
        assert decision["referencePreparedSha256"] == sha(Path(decision["reference"]))
        assert decision["referenceHadTransparency"] is (label == "rgba")
        assert decision["referencePreparation"] == ("alpha-composite-key-ring" if label == "rgba" else "unchanged")
        # The worker strips only these two known path keys from provenance.
        assert not any(isinstance(value, str) and Path(value).is_absolute()
                       for field, value in decision.items() if field not in ("reference", "referencePath"))
        report = json.loads(Path(result["extraction"]["reportPath"]).read_text())
        assert report["spill"] == decision
        outputs.append([np.asarray(Image.open(frame["keyedPath"]).convert("RGBA")) for frame in result["frames"]])
    assert sha(reference) == before
    assert len(outputs[0]) == len(outputs[1]) == 5
    for rgb, rgba in zip(*outputs):
        np.testing.assert_array_equal(rgb, rgba)


@pytest.mark.parametrize("variable", [False, True], ids=["cfr", "vfr"])
def test_faint_genuine_magenta_material_keeps_conservative_spill(tmp_path, variable):
    # Tint 10 is below the old strong-tint bar 40, but above full's bar 8.
    material = (130, 120, 130)
    clip, reference, opaque = make_spill_fixture(tmp_path / "fixture", variable=variable, material=material)
    outputs = []
    for label, ref in (("none", None), ("rgb", opaque), ("rgba", reference)):
        params = {"loopMode": "full", **({"referencePath": str(ref)} if ref else {})}
        result = vp.process_clip(clip, tmp_path / label, params)
        decision = result["extraction"]["spill"]
        assert decision["mode"] == "small"
        if ref:
            assert decision["key_material_share"] > decision["share_max"]
            assert decision["material_metric"] == "key-channel-excess"
            assert decision["reference_fringe_policy"] == "dark-only"
        else:
            assert decision["reason"] == "no reference"
        frames = [np.asarray(Image.open(frame["keyedPath"]).convert("RGBA")) for frame in result["frames"]]
        for frame in frames:
            np.testing.assert_array_equal(frame[44:52, 44:52], np.tile((*material, 255), (8, 8, 1)))
        outputs.append(frames)
    for no_reference, rgb, rgba in zip(*outputs):
        np.testing.assert_array_equal(no_reference, rgb)
        np.testing.assert_array_equal(rgb, rgba)
    # Verify this fixture would actually lose its material if promoted to full.
    engine = vp._engine("video.frames")
    engine.key_frames([Path(result["frames"][0]["rawPath"])], tmp_path / "forced-full",
                      key="magenta", spill="full", decontam="auto")
    with Image.open(tmp_path / "forced-full" / Path(result["frames"][0]["rawPath"]).name) as forced:
        assert forced.getpixel((48, 48)) != (*material, 255)


def test_spill_cache_tracks_reference_content_and_prepared_evidence(tmp_path, monkeypatch):
    clip, reference, _ = make_spill_fixture(tmp_path / "fixture", material=(130, 120, 130))
    params = {"loopMode": "full", "referencePath": str(reference)}
    work = tmp_path / "work"
    first = vp.process_clip(clip, work, params)
    original_hash = sha(reference)
    with Image.open(reference) as image:
        ImageDraw.Draw(image).rectangle((36, 36, 59, 59), fill=(160, 100, 40, 255))
        image.save(reference)
    second = vp.process_clip(clip, work, params)
    assert first["extraction"]["spill"]["mode"] == "small"
    assert second["extraction"]["spill"]["mode"] == "full"
    assert first["extraction"]["rawDir"] != second["extraction"]["rawDir"]
    assert first["extraction"]["spill"]["referenceSourceSha256"] == original_hash
    assert second["extraction"]["spill"]["referenceSourceSha256"] == sha(reference)
    markers = list(work.glob("extractions/*/complete.json"))
    assert len(markers) == 2
    assert all(json.loads(path.read_text())["options"]["version"] == "video-processing-v3" for path in markers)
    prepared = Path(second["extraction"]["spill"]["reference"])
    prepared.write_bytes(b"invalid prepared reference evidence")
    third = vp.process_clip(clip, work, params)
    assert third["extraction"]["rawDir"] != second["extraction"]["rawDir"]
    assert third["extraction"]["spill"]["referencePreparedSha256"] == second["extraction"]["spill"]["referencePreparedSha256"]
    monkeypatch.setattr(vp, "_run_extraction", lambda *args: pytest.fail("valid evidence must be reused"))
    cached = vp.process_clip(clip, work, params)
    assert cached["extraction"] == third["extraction"]


def test_fractional_fps_cumulative_integer_timing(tmp_path):
    clip = make_clip(tmp_path / "fixture", count=31, fps="30000/1001")
    result = vp.process_clip(clip, tmp_path / "work", {"loopMode": "full", "maxFrames": 64})
    durations = [f["durationMs"] for f in result["frames"]]
    assert set(durations) == {33, 34}
    assert sum(durations) == round(31 * 1000 * 1001 / 30000)
    assert result["frames"][30]["sourceTimeMs"] == pytest.approx(1001, abs=0.001)


def test_timing_accepts_15_second_video_with_muxer_padding(tmp_path):
    clip = make_clip(tmp_path / "fixture", count=361, moving=False)
    meta = vp._timing(clip)
    assert 15000 < meta["durationMs"] <= 15100
    assert meta["frameCount"] == 361


def test_vfr_passthrough_preserves_source_frames_and_timestamps(tmp_path):
    original = make_clip(tmp_path / "fixture", count=6)
    manifest = tmp_path / "vfr.txt"
    lines = []
    for index, duration in enumerate((.04, .12, .08, .16, .04, .12)):
        lines.extend([f"file '{original.parent / f'input-{index:04d}.png'}'", f"duration {duration}"])
    lines.append(f"file '{original.parent / 'input-0005.png'}'")
    manifest.write_text("\n".join(lines) + "\n")
    clip = tmp_path / "variable.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-safe", "0", "-f", "concat", "-i", str(manifest),
                    "-fps_mode", "vfr", "-c:v", "libx264rgb", "-crf", "0", "-y", str(clip)],
                   capture_output=True, check=True, timeout=30)
    result = vp.process_clip(clip, tmp_path / "work", {"loopMode": "full", "maxFrames": 64})
    assert result["source"]["constantFrameRate"] is False
    assert [f["sourceTimeMs"] for f in result["frames"]] == pytest.approx([0, 40, 160, 240, 400, 440, 560])
    assert [f["durationMs"] for f in result["frames"]] == [40, 120, 80, 160, 40, 120, 40]
    for index, frame in enumerate(result["frames"]):
        with Image.open(original.parent / f"input-{min(index, 5):04d}.png") as expected, Image.open(frame["rawPath"]) as actual:
            assert expected.tobytes() == actual.convert("RGB").tobytes()
    with pytest.raises(vp.VideoProcessingError) as auto:
        vp.process_clip(clip, tmp_path / "work", {"loopMode": "auto"})
    assert auto.value.code == "VIDEO_VARIABLE_RATE_AUTO"


def make_action_clip(root):
    """One observed excursion between resting poses, with slight filmed jitter."""
    root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(3)
    for t in range(144):
        lift = round(14 * math.sin(math.pi * (t - 60) / 15)) if 60 <= t < 75 else 0
        dx, dy = int(rng.integers(-1, 2)), int(rng.integers(-1, 2))
        image = Image.new("RGB", (64, 64), (255, 0, 255))
        ImageDraw.Draw(image).rectangle((24 + dx, 20 - lift + dy, 39 + dx, 57 - lift + dy), fill=(200, 60, 60))
        image.save(root / f"input-{t:04d}.png")
    clip = root / "action.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-framerate", "24", "-i", str(root / "input-%04d.png"),
                    "-c:v", "libx264rgb", "-crf", "0", "-preset", "ultrafast", "-y", str(clip)],
                   check=True, capture_output=True, timeout=30)
    return clip


@pytest.mark.parametrize("state", ["jump", "attack"])
def test_auto_one_shot_actions_play_once_and_keep_motion(tmp_path, state):
    clip = make_action_clip(tmp_path / "fixture")
    result = vp.process_clip(clip, tmp_path / "work", {"loopMode": "auto", "state": state})
    selection = result["selection"]
    assert selection["kind"] == "one-shot"
    assert selection["loop"] is False and selection["verifiedPeriodic"] is False
    assert selection["startFrame"] <= 60 and selection["endFrame"] >= 75
    assert sum(f["durationMs"] for f in result["frames"]) == selection["durationMs"]
    if state == "jump":
        rejected = selection["metrics"]["periodicAttempt"]
        assert "main action excursion" in rejected["reason"]
        assert rejected["metrics"]["excursionCoverage"]["share"] < .5
    with Image.open(result["previewPath"]) as gif:
        assert "loop" not in gif.info


def test_pinned_idle_keeps_whole_clip_except_duplicate_return_pose(tmp_path):
    clip = make_clip(tmp_path / "fixture", count=65)
    result = vp.process_clip(clip, tmp_path / "work", {"state": "idle", "maxFrames": 64})
    selection = result["selection"]
    assert selection["kind"] == "pinned" and selection["loop"] is True
    assert selection["verifiedPeriodic"] is False
    assert (selection["startFrame"], selection["endFrame"]) == (0, 64)
    assert selection["metrics"]["pin_error"] <= selection["metrics"]["pin_tolerance"]
    assert len(result["frames"]) == 64
    assert sum(f["durationMs"] for f in result["frames"]) == 2667


def test_attack_stillness_is_not_a_successful_action(tmp_path):
    clip = make_clip(tmp_path / "fixture", count=32, moving=False)
    with pytest.raises(vp.VideoProcessingError) as error:
        vp.process_clip(clip, tmp_path / "work", {"state": "attack"})
    assert error.value.code == "VIDEO_NO_ACTION_MATCH"
    assert error.value.details["regenerationRequired"] is False
    assert len(list(Path(error.value.details["keyedDir"]).glob("*.png"))) == 32


@pytest.mark.parametrize('direction', ['front_diagonal', 'back_diagonal'])
@pytest.mark.parametrize('facing', ['left', 'right'])
def test_diagonal_view_holds_its_heading_equipment_and_first_last_pose(direction, facing):
    from adapters.spritegen import video_provider
    params = video_provider.validate_params({'direction': direction, 'facing': facing}, generation=True)
    prompt = vp.build_motion_prompt(params)
    assert 'three-quarter' in prompt and f'the {facing}' in prompt
    assert 'Never turn into a side view' in prompt or 'never turn into a side view' in prompt
    assert 'same hand' in prompt and 'Return to the starting pose' in prompt
    if direction == 'back_diagonal':
        assert 'face stays hidden' in prompt
    batch = vp._engine('video.batch')
    assert batch.pins_last_frame('walk', direction) and batch.pins_last_frame('run', direction)
    assert params['repairMode'] == 'off' and params['finishMode'] == 'gif'


def test_lite_back_diagonal_head_hold_does_not_override_custom_gait():
    prompt = vp.build_motion_prompt({'direction': 'back_diagonal', 'model': 'grok-imagine-video-1.5-lite',
                                     'motionPrompt': 'A high-knee march.'})
    assert 'head stays level and steady' in prompt
    assert 'A high-knee march.' in prompt and 'slow, relaxed' not in prompt
    assert 'head stays level and steady' not in vp.build_motion_prompt({'direction': 'back_diagonal'})


@pytest.mark.parametrize('state', ['wave', 'cheer', 'dance'])
def test_new_motion_states_keep_equipment_and_usable_canvas(tmp_path, state):
    from adapters.spritegen import video_provider
    params = video_provider.validate_params({'state': state}, generation=True)
    prompt = vp.build_motion_prompt(params)
    assert state in prompt or state == 'cheer' and 'celebrates' in prompt
    assert 'same hand' in prompt and 'no zoom' in prompt
    source = tmp_path / 'source.png'
    image = Image.new('RGBA', (64, 128))
    ImageDraw.Draw(image).rectangle((18, 20, 42, 110), fill=(160, 110, 70, 255))
    image.save(source)
    result = vp.prepare_still(source, tmp_path / 'prepared.png', params)
    assert result['canvas']['shape'] == ('wide' if state in ('wave', 'cheer') else 'square')


def test_unrecognized_finish_repair_and_direction_are_rejected():
    from adapters.spritegen import video_provider
    from services.api import store
    for params in ({'finishMode': 'fake'}, {'repairMode': 'fake'}, {'direction': 'diagonal'}):
        with pytest.raises(store.AppError):
            video_provider.validate_params(params, generation=False)


def _jump_loop(root):
    """Synthetic coverage anomaly for adapter bookkeeping, never AI output."""
    root.mkdir()
    paths, truth = [], []
    for k in range(24):
        image = Image.new('RGBA', (120, 140))
        draw = ImageDraw.Draw(image)
        draw.rectangle((50, 30, 69, 99), fill=(90, 90, 200, 255))
        draw.rectangle((48, 10, 71, 29), fill=(230, 190, 160, 255))
        fx, fy = 60 + round(22 * math.cos(k * math.tau / 24)), 121 + round(10 * math.sin(k * math.tau / 24))
        draw.rectangle((fx - 6, fy - 6, fx + 5, fy + 5), fill=(60, 60, 60, 255))
        tx = 14 + min(k, 24 - k)
        clean = image.copy()
        ImageDraw.Draw(clean).rectangle((tx, 45, tx + 15, 94), fill=(200, 40, 40, 255))
        truth.append(clean)
        if k == 10:
            tx += 12
        draw.rectangle((tx, 45, tx + 15, 94), fill=(200, 40, 40, 255))
        path = root / f'frame-{k + 1:04d}.png'
        image.save(path)
        paths.append(path)
    return paths, truth


def test_rife_repair_is_opt_in_preserves_sources_and_declares_interpolator(tmp_path, monkeypatch):
    files, truth = _jump_loop(tmp_path / 'keyed')
    before = [sha(path) for path in files]
    selection = dict(startFrame=0, endFrame=24, loop=True)
    options = dict(state='walk', facing='right', repairMode='off')
    monkeypatch.setattr(vp, 'rife_interpolator', lambda: pytest.fail('off must not locate RIFE'))
    unchanged, record = vp._repair_selection(files, selection, options, tmp_path)
    assert unchanged is files and record['applied'] is False and record['replaced'] == []
    calls = []
    class Fake:
        def __call__(self, a, b, t):
            calls.append(t)
            return truth[10]
        def describe(self):
            return {'binary': 'synthetic-test-double', 'model': 'synthetic-test-double'}
    monkeypatch.setattr(vp, 'rife_interpolator', Fake)
    updated, record = vp._repair_selection(files, selection, {**options, 'repairMode': 'on'}, tmp_path)
    assert calls == [0.5] and record['sourceFrameIndices'] == [10]
    assert record['interpolator']['binary'] == 'synthetic-test-double'
    assert [sha(path) for path in files] == before
    assert [sha(p) != sha(q) for p, q in zip(files, updated)] == [k == 10 for k in range(24)]
    assert (tmp_path / 'repaired').is_dir()


def test_missing_rife_auto_is_explicit_but_required_repair_fails(tmp_path, monkeypatch):
    files, _ = _jump_loop(tmp_path / 'keyed')
    rife = vp._engine('video.rife')
    def missing():
        raise rife.RifeNotInstalled('synthetic missing install')
    monkeypatch.setattr(vp, 'rife_interpolator', missing)
    selection = dict(startFrame=0, endFrame=24, loop=True)
    options = dict(state='walk', facing='right', repairMode='auto')
    same, record = vp._repair_selection(files, selection, options, tmp_path)
    assert same is files and not record['applied'] and 'synthetic missing install' in record['warning']
    with pytest.raises(vp.VideoProcessingError, match='RIFE') as failure:
        vp._repair_selection(files, selection, {**options, 'repairMode': 'on'}, tmp_path)
    assert failure.value.code == 'VIDEO_RIFE_UNAVAILABLE'


def test_first_successful_loop_never_runs_gait_fallback(tmp_path, monkeypatch):
    clip = make_clip(tmp_path / 'fixture', count=64)
    monkeypatch.setattr(vp, '_gait_fallback', lambda *a: pytest.fail('successful primary cycle must remain unchanged'))
    result = vp.process_clip(clip, tmp_path / 'work', {'state': 'walk'})
    assert result['selection']['verifiedPeriodic']
    assert not result['selection']['repair']['applied']
    assert all(not f['interpolated'] and f['keyedPath'] == f['originalKeyedPath'] for f in result['frames'])


def test_matched_cycle_resamples_with_unique_output_identity_and_provenance(tmp_path, monkeypatch):
    clip = make_clip(tmp_path / 'fixture', count=37)
    calls = []
    class SyntheticInterpolator:
        def __call__(self, a, b, t):
            calls.append(t)
            return Image.blend(a, b, t)
        def describe(self):
            return {'binary': 'synthetic-test-double', 'model': 'synthetic-test-double'}
    monkeypatch.setattr(vp, 'rife_interpolator', SyntheticInterpolator)
    result = vp.process_clip(clip, tmp_path / 'work', {'loopMode': 'manual', 'startFrame': 0, 'endFrame': 16,
                             'targetFrameCount': 32, 'targetDurationMs': 1200})
    frames = result['frames']
    assert len(frames) == 32 and len(calls) == 16
    assert [f['outputFrameIndex'] for f in frames] == list(range(32))
    assert len({f['keyedPath'] for f in frames}) == 32
    assert len({f['sourceFrameIndex'] for f in frames}) == 16
    assert sum(f['durationMs'] for f in frames) == result['selection']['durationMs'] == 1200
    assert sum(f['interpolated'] for f in frames) == 16
    for frame in frames:
        if frame['interpolated']:
            proof = frame['interpolation']
            assert proof['method'] == 'rife-cycle-align' and proof['fraction'] == .5
            assert len(proof['sourceFrameIndices']) == 2
        else:
            with Image.open(frame['keyedPath']) as current, Image.open(frame['originalKeyedPath']) as original:
                assert np.array_equal(current, original)
    assert result['boundsPaths'] == [f['keyedPath'] for f in frames]
    assert result['selection']['cycleAlignment']['made_by_rife'] == 16
    assert result['selection']['cycleAlignment']['referencePhaseChanged'] is False
    assert len(list(Path(result['extraction']['keyedDir']).glob('*.png'))) == 37


def test_matched_cycle_at_exact_samples_uses_no_rife_and_full_video_is_refused(tmp_path, monkeypatch):
    clip = make_clip(tmp_path / 'fixture', count=37)
    monkeypatch.setattr(vp, 'rife_interpolator', lambda: pytest.fail('integer source samples need no RIFE'))
    params = {'loopMode': 'manual', 'startFrame': 0, 'endFrame': 16, 'targetFrameCount': 8}
    result = vp.process_clip(clip, tmp_path / 'work', params)
    assert len(result['frames']) == 8 and all(not f['interpolated'] for f in result['frames'])
    assert result['selection']['cycleAlignment']['made_by_rife'] == 0
    assert sum(f['durationMs'] for f in result['frames']) == 667
    with pytest.raises(vp.VideoProcessingError) as refused:
        vp.process_clip(clip, tmp_path / 'work', {'loopMode': 'full', 'targetFrameCount': 8})
    assert refused.value.code == 'VIDEO_ALIGN_NOT_LOOP'


def test_scale_drift_metadata_distinguishes_affine_source_from_interpolated_canvas():
    transform = {'scaleX': .8, 'scaleY': .8, 'offsetX': 20.0, 'offsetY': 30.0}
    rows = [{'sourceFrameIndex': i, 'fittedHeightPx': 100 + i * 10,
             'footAnchor': {'x': 100, 'y': 150}, 'sourceTransform': transform} for i in range(3)]
    selection = {'metrics': {'gaitFallback': {'scaleCorrection': {
        'method': 'fitted-height-about-fitted-foot-v1', 'referenceSourceFrameIndex': 0,
        'referenceFittedHeightPx': 100, 'resampler': 'premultiplied-bicubic', 'frames': rows}}}}
    frame = {'sourceFrameIndex': 1, 'interpolated': False, 'processing': {'kind': 'scale-drift-correction'}}
    vp._describe_source_processing(frame, selection)
    provenance = frame['processing']
    assert provenance['coordinateSpace'] == 'processed-video-canvas'
    assert provenance['sourceCoordinateSpace'] == 'decoded-video-canvas'
    assert provenance['sourceTransform'] == transform
    assert provenance['scaleCorrection']['referenceSourceFrameIndex'] == 0
    assert provenance['scaleCorrection']['fittedHeightPx'] == 110
    assert provenance['sourceTransform']['scaleX'] * 100 + provenance['sourceTransform']['offsetX'] == 100
    interpolated = {'sourceFrameIndex': 1, 'interpolated': True, 'processing': {'kind': 'rife-jump-repair'},
                    'interpolation': {'sourceFrameIndices': [0, 2], 'fraction': .5}}
    vp._describe_source_processing(interpolated, selection)
    assert interpolated['processing']['rawToProcessedMapping'] == 'non-affine-interpolation'
    assert 'sourceTransform' not in interpolated['processing']
    assert [x['sourceFrameIndex'] for x in interpolated['processing']['preInterpolationSourceTransforms']] == [0, 2]
