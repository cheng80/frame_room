"""Synthetic export oracles; no model calls and no claims of generated art."""
import copy
import io
import json
from pathlib import PurePosixPath
import zipfile

import numpy as np
from PIL import Image
import pytest

from alignment import animation_exports
from alignment.animation_exports import write_animation_formats
from alignment.pipeline import build_bundle, PipelineError, render_occurrence
from test_pipeline import project  # Shared canonical-render fixture, no new engine mocks.


def decoded_animation(data):
    frames, durations = [], []
    with Image.open(io.BytesIO(data)) as image:
        loop = image.info.get("loop")
        for index in range(image.n_frames):
            image.seek(index)
            image.load()
            frames.append(image.convert("RGBA"))
            durations.append(image.info.get("duration"))
    return frames, durations, loop


def assert_timeline(frames, durations, cells, source_durations):
    # Independent interval oracle supports adjacent-identical codec merging.
    expected = {}
    cursor = 0
    for image, duration in zip(cells, source_durations):
        for ms in range(cursor, cursor + duration):
            expected[ms] = image.tobytes()
        cursor += duration
    assert sum(durations) == cursor
    cursor = 0
    for image, duration in zip(frames, durations):
        for ms in range(cursor, cursor + duration):
            assert image.tobytes() == expected[ms]
        cursor += duration


def cells():
    one = Image.new("RGBA", (8, 6))
    one.putpixel((1, 3), (40, 80, 120, 128))
    one.putpixel((6, 2), (99, 33, 77, 255))
    two = Image.new("RGBA", (8, 6))
    two.putpixel((2, 1), (90, 120, 20, 1))
    two.putpixel((5, 4), (1, 150, 15, 255))
    return [one, two]


@pytest.mark.parametrize("loop", [True, False])
def test_canonical_bundle_sheets_preserve_every_slot_and_metadata(project, tmp_path, loop):
    snapshot, path, _ = project
    interpolation = {"method": "rife", "fraction": 0.5, "sourceFrameIndices": [41, 42]}
    processing = {"kind": "rife-jump-repair", "sourceTransform": {"scaleX": 1, "scaleY": 1, "offsetX": -2, "offsetY": 1}}
    snapshot["frames"][0].update(interpolated=True, interpolation=interpolation, sourceProcessing=processing)
    clip = snapshot["clips"][0]
    clip.update(name="../../unsafe\\name:<|?", loop=loop)
    original = clip["occurrences"][0]
    clip["occurrences"] = []
    for index, duration in enumerate((17, 83, 125, 41, 34)):
        slot = copy.deepcopy(original)
        slot.update(occurrenceId=f"slot-{index}", durationMs=duration,
                    transform={"flipX": index % 2 == 1}, pixelEdits=[{"x": 16, "y": 21, "color": [10 + index, 50, 80, 255]}])
        clip["occurrences"].append(slot)
    before = copy.deepcopy(snapshot)
    output = tmp_path / "bundle"
    result = build_bundle(snapshot, [clip["clipId"]], path, output, "exp")
    assert snapshot == before
    runtime = result["manifest"]
    metadata = json.loads((output / "animation-manifest.json").read_bytes())
    assert metadata["recipeHash"] == runtime["recipeHash"]
    assert metadata["projectRevision"] == runtime["projectRevision"]
    assert metadata["source"] == "canonical-bake-cells"
    assert {"animations.zip", "animation-manifest.json"} <= set(result["files"])
    assert {"animations.zip", "animation-manifest.json"} <= {f["name"] for f in runtime["files"]}
    animation = metadata["clips"][0]
    assert animation["loop"] == loop
    assert animation["durationMs"] == 300
    direct = [render_occurrence(snapshot, clip, slot, path)[0] for slot in clip["occurrences"]]
    with zipfile.ZipFile(output / "animations.zip") as archive:
        assert archive.read("manifest.json") == (output / "animation-manifest.json").read_bytes()
        assert len(archive.namelist()) == 5
        for filename in archive.namelist():
            assert not PurePosixPath(filename).is_absolute()
            assert ".." not in PurePosixPath(filename).parts
            assert "\\" not in filename
        for key, rect_key in (("stripPng", "stripRect"), ("gridPng", "gridRect")):
            sheet = Image.open(io.BytesIO(archive.read(animation["formats"][key]["file"]))).convert("RGBA")
            for i, slot in enumerate(animation["occurrences"]):
                r = slot[rect_key]
                assert sheet.crop((r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"])).tobytes() == direct[i].tobytes()
                for field in ("id", "renderedFrameId", "durationMs", "anchor", "timingMode"):
                    assert slot[field] == runtime["clips"][0]["occurrences"][i][field]
            if key == "gridPng":
                assert sheet.size == (96, 64)
                assert sheet.crop((64, 32, 96, 64)).getbbox() is None
        frames, durations, actual_loop = decoded_animation(archive.read(animation["formats"]["webp"]["file"]))
        assert actual_loop == (0 if loop else 1)
        assert_timeline(frames, durations, direct, [17, 83, 125, 41, 34])
    with zipfile.ZipFile(output / "bundle.zip") as archive:
        assert archive.read("animations.zip") == (output / "animations.zip").read_bytes()
        assert archive.read("animation-manifest.json") == (output / "animation-manifest.json").read_bytes()
        bundled_runtime = json.loads(archive.read("runtime.json"))
        for exported in (runtime, bundled_runtime, json.loads((output / "runtime.json").read_bytes())):
            assert exported["frameSources"][0]["interpolated"] is True
            assert exported["frameSources"][0]["interpolation"] == interpolation
            assert exported["frameSources"][0]["sourceProcessing"] == processing


@pytest.mark.parametrize("loop", [True, False])
def test_gif_boundary_rounding_alpha_loop_and_loss_report(tmp_path, loop):
    source = cells()
    source = [source[0], source[1], source[0]]
    out = write_animation_formats(source, [17, 17, 17], loop, tmp_path)
    gif = out["formats"]["gif"]
    frames, durations, actual_loop = decoded_animation((tmp_path / gif["file"]).read_bytes())
    assert durations == [20, 10, 20]
    assert actual_loop == (0 if loop else None)
    assert gif["sourceDurationsMs"] == [17, 17, 17]
    assert gif["encodedDurationsMs"] == durations
    assert gif["totalDurationErrorMs"] == -1
    assert gif["lossy"] and gif["pixelLossDetected"] and gif["timingLossy"]
    assert frames[0].getpixel((1, 3))[3] == 0  # Inclusive <=128 threshold.
    assert frames[1].getpixel((2, 1))[3] == 0
    assert frames[0].getpixel((6, 2)) == (99, 33, 77, 255)
    # Disposal must clear the previous frame instead of accumulating trails.
    assert frames[1].getpixel((6, 2))[3] == 0
    assert frames[2].getpixel((5, 4))[3] == 0


def test_gif_exact_255_visible_colors_and_duplicate_timing(tmp_path):
    image = Image.new("RGBA", (16, 16))
    for index in range(255):
        image.putpixel((index % 16, index // 16), (index, 15, 75, 255))
    out = write_animation_formats([image, image, image], [40, 80, 120], True, tmp_path)
    metadata = out["formats"]["gif"]
    frames, durations, _ = decoded_animation((tmp_path / metadata["file"]).read_bytes())
    assert len(frames) == 3
    assert durations == [40, 80, 120]
    assert not metadata["pixelLossDetected"]
    assert metadata["changedPixelsPerOccurrence"] == [0, 0, 0]
    assert all(frame.tobytes() == image.tobytes() for frame in frames)


def test_gif_many_colors_quantized_explicitly(tmp_path):
    image = Image.new("RGBA", (32, 32))
    for y in range(32):
        for x in range(32):
            image.putpixel((x, y), (x * 7, y * 7, (x + y) * 3, 129 if x == 0 else 255))
    out = write_animation_formats([image], [25], False, tmp_path)
    gif = out["formats"]["gif"]
    frames, durations, loop = decoded_animation((tmp_path / gif["file"]).read_bytes())
    assert gif["pixelLossDetected"] and gif["changedPixelsPerOccurrence"][0] > 0
    assert len(frames[0].getcolors(1024)) <= 255
    assert frames[0].getpixel((0, 0))[3] == 255
    assert durations == [30] and loop is None


@pytest.mark.parametrize("durations", [[1], [9, 50], [15, 1, 25]])
def test_subcentisecond_gif_omitted_without_changing_other_outputs(tmp_path, durations):
    images = [cells()[i % 2] for i in range(len(durations))]
    out = write_animation_formats(images, durations, False, tmp_path)
    assert "animation.gif" not in out["files"]
    assert not (tmp_path / "animation.gif").exists()
    assert out["formats"]["gif"]["reason"]["code"] == "GIF_TIMING_UNREPRESENTABLE"
    assert out["warnings"][0]["code"] == "GIF_TIMING_UNREPRESENTABLE"
    frames, decoded_durations, loop = decoded_animation((tmp_path / "animation.webp").read_bytes())
    assert loop == 1
    assert_timeline(frames, decoded_durations, images, durations)


@pytest.mark.parametrize("loop", [True, False])
@pytest.mark.parametrize("indices,durations", [([0], [83]), ([0, 0, 0], [20, 80, 41]), ([0, 0, 1, 1, 0], [17, 41, 83, 20, 25])])
def test_webp_rgba_exact_with_single_duplicate_and_variable_frames(tmp_path, loop, indices, durations):
    originals = cells()
    images = [originals[i] for i in indices]
    before = [image.tobytes() for image in images]
    out = write_animation_formats(images, durations, loop, tmp_path)
    metadata = out["formats"]["webp"]
    frames, decoded_durations, actual_loop = decoded_animation((tmp_path / metadata["file"]).read_bytes())
    assert [image.tobytes() for image in images] == before
    assert actual_loop == (0 if loop else 1)
    assert_timeline(frames, decoded_durations, images, durations)
    assert metadata["decodedFrameCount"] == len(frames)
    assert metadata["decodedDurationsMs"] == decoded_durations
    assert metadata["durationMs"] == sum(durations)
    assert metadata["fullRGBAParity"] and not metadata["lossy"]


def test_different_cell_sizes_only_padded_top_left(tmp_path):
    one, two = cells()
    two = two.crop((0, 0, 6, 5))
    out = write_animation_formats([one, two], [40, 80], True, tmp_path)
    assert out["cell"] == {"width": 8, "height": 6}
    with Image.open(tmp_path / "strip.png") as image:
        assert image.crop((0, 0, 8, 6)).tobytes() == one.tobytes()
        assert image.crop((8, 0, 14, 5)).tobytes() == two.tobytes()
        assert image.crop((14, 0, 16, 6)).getbbox() is None


def test_missing_webp_codec_and_sheet_limit_are_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(animation_exports.features, "check", lambda feature: False)
    monkeypatch.setattr(animation_exports, "MAX_SHEET_PIXELS", 50)
    result = write_animation_formats(cells(), [40, 40], True, tmp_path)
    assert result["files"] == ["animation.gif"]
    assert result["formats"]["webp"]["reason"]["code"] == "WEBP_UNAVAILABLE"
    assert {w["code"] for w in result["warnings"]} == {"WEBP_UNAVAILABLE", "SHEET_TOO_LARGE"}


def test_helper_rejects_invalid_timing_and_never_overwrites(tmp_path):
    for durations in ([0, 10], [True, 10], [10.5, 20], [40]):
        with pytest.raises(ValueError):
            write_animation_formats(cells(), durations, True, tmp_path)
    assert not list(tmp_path.iterdir())
    write_animation_formats(cells(), [40, 80], True, tmp_path)
    existing = (tmp_path / "strip.png").read_bytes()
    with pytest.raises(FileExistsError):
        write_animation_formats(cells(), [40, 80], True, tmp_path)
    assert (tmp_path / "strip.png").read_bytes() == existing


def test_animation_archive_corruption_blocks_atomic_publication(project, tmp_path, monkeypatch):
    import alignment.pipeline as pipeline
    original_zip = pipeline._zip
    def corrupt(path, entries):
        if path.name == "animations.zip":
            entries = [(name, b"changed" if name.endswith("strip.png") else data) for name, data in entries]
        original_zip(path, entries)
    monkeypatch.setattr(pipeline, "_zip", corrupt)
    with pytest.raises(PipelineError) as error:
        build_bundle(project[0], ["idle"], project[1], tmp_path / "unpublished", "exp")
    assert error.value.code == "ARTIFACT_HASH_MISMATCH"
    assert not (tmp_path / "unpublished").exists()
    assert not list(tmp_path.glob(".bake-*"))
