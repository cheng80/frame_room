"""Independent saved-artifact checks with deliberately rehashed corruptions."""
import io
import json
import zipfile

from PIL import Image
import pytest

from alignment.verify_artifacts import ArtifactValidationError, verify_artifacts
from alignment.pipeline import build_bundle
from test_pipeline import (project, artifact_export, digest, _test_write_json,
                           _test_zip_replace, _test_reseal_artifacts)


def read_animations(directory):
    with zipfile.ZipFile(directory / "animations.zip") as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    return json.loads((directory / "animation-manifest.json").read_bytes()), entries


def reseal_animations(directory, metadata, entries):
    for clip in metadata["clips"]:
        for record in clip["formats"].values():
            if record["status"] == "created":
                record["sha256"] = digest(entries[record["file"]])
    entries["manifest.json"] = json.dumps(metadata, ensure_ascii=False).encode()
    (directory / "animation-manifest.json").write_bytes(entries["manifest.json"])
    _test_zip_replace(directory / "animations.zip", entries)
    _test_reseal_artifacts(directory)


def test_animation_verifier_reports_all_formats_hashes_and_interpolation(artifact_export):
    directory, _ = artifact_export
    runtime = json.loads((directory / "runtime.json").read_bytes())
    runtime["frameSources"][0].update(interpolated=True,
        interpolation={"method": "rife-ncnn-vulkan", "fraction": .5, "sourceFrameIndices": [41, 43]})
    _test_write_json(directory / "runtime.json", runtime)
    _test_reseal_artifacts(directory)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}
    result = verify_artifacts(directory)
    assert result["interpolatedFrameSourcesChecked"] == 1
    assert len(result["animationClips"]) == 2
    assert all(set(clip["formatsChecked"]) == {"stripPng", "gridPng", "gif", "webp"} for clip in result["animationClips"])
    assert len(result["files"]) == 8
    for file in result["files"]:
        assert file["sha256"] == digest((directory / file["name"]).read_bytes())
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}


@pytest.mark.parametrize("name", ["animations.zip", "animation-manifest.json"])
def test_animation_verifier_detects_standalone_hash_change(artifact_export, name):
    directory, _ = artifact_export
    with (directory / name).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "FILE_HASH_MISMATCH"
    assert error.value.details["file"] == name


@pytest.mark.parametrize("name", ["animations.zip", "animation-manifest.json"])
def test_animation_verifier_detects_stale_bundle_copy(artifact_export, name):
    directory, _ = artifact_export
    with zipfile.ZipFile(directory / "bundle.zip") as archive:
        entries = {key: archive.read(key) for key in archive.namelist()}
    entries[name] += b" "
    _test_zip_replace(directory / "bundle.zip", entries)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "BUNDLE_MISMATCH"
    assert error.value.details["file"] == name


def test_animation_verifier_detects_inner_manifest_mismatch_after_outer_rehash(artifact_export):
    directory, _ = artifact_export
    _, entries = read_animations(directory)
    entries["manifest.json"] += b" "
    _test_zip_replace(directory / "animations.zip", entries)
    _test_reseal_artifacts(directory)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "ANIMATION_MANIFEST_MISMATCH"


def test_animation_verifier_detects_inner_file_hash_change_after_outer_rehash(artifact_export):
    directory, _ = artifact_export
    metadata, entries = read_animations(directory)
    name = metadata["clips"][0]["formats"]["stripPng"]["file"]
    entries[name] += b" "
    _test_zip_replace(directory / "animations.zip", entries)
    _test_reseal_artifacts(directory)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "FILE_HASH_MISMATCH"
    assert error.value.details["file"] == name


@pytest.mark.parametrize("kind", ["stripPng", "gridPng", "webp"])
def test_animation_verifier_detects_pixel_corruption_after_all_hashes_resealed(artifact_export, kind):
    directory, _ = artifact_export
    metadata, entries = read_animations(directory)
    record = metadata["clips"][0]["formats"][kind]
    name = record["file"]
    with Image.open(io.BytesIO(entries[name])) as image:
        frames, durations = [], []
        for index in range(image.n_frames):
            image.seek(index); image.load()
            frames.append(image.convert("RGBA"))
            durations.append(image.info.get("duration", 0))
    frames[0].putpixel((0, 0), (3, 4, 5, 255))
    stream = io.BytesIO()
    if kind == "webp":
        frames[0].save(stream, format="WEBP", save_all=True, append_images=frames[1:],
                       duration=durations, loop=0, lossless=True, exact=True)
    else:
        frames[0].save(stream, format="PNG")
    entries[name] = stream.getvalue()
    reseal_animations(directory, metadata, entries)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "RGBA_MISMATCH"


@pytest.mark.parametrize("kind", ["gif", "webp"])
def test_animation_verifier_detects_wrong_encoded_loop_after_rehash(artifact_export, kind):
    directory, _ = artifact_export
    metadata, entries = read_animations(directory)
    record = metadata["clips"][0]["formats"][kind]
    name = record["file"]
    with Image.open(io.BytesIO(entries[name])) as image:
        frames, durations = [], []
        for index in range(image.n_frames):
            image.seek(index); image.load()
            frames.append(image.convert("RGBA"))
            durations.append(image.info["duration"])
    stream = io.BytesIO()
    frames[0].save(stream, format=kind.upper(), save_all=True, append_images=frames[1:],
                   duration=durations, loop=1, lossless=True, exact=True)
    entries[name] = stream.getvalue()
    reseal_animations(directory, metadata, entries)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "ANIMATION_TIMING_MISMATCH"


@pytest.mark.parametrize("change,code", [
    (lambda m: m["clips"][0]["occurrences"].reverse(), "TIMELINE_MISMATCH"),
    (lambda m: m["clips"][0]["formats"]["webp"].update(sourceDurationsMs=[100, 100, 200]), "ANIMATION_TIMING_MISMATCH"),
    (lambda m: m["clips"][0]["formats"]["gif"].update(decodedFrameCount=1), "ANIMATION_METADATA_MISMATCH"),
])
def test_animation_verifier_detects_forged_metadata_after_rehash(artifact_export, change, code):
    directory, _ = artifact_export
    metadata, entries = read_animations(directory)
    change(metadata)
    reseal_animations(directory, metadata, entries)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == code


@pytest.mark.parametrize("name,code", [("unlisted.txt", "ZIP_MEMBER_MISMATCH"), ("../escape.png", "INVALID_ZIP_MEMBER")])
def test_animation_verifier_rejects_unlisted_or_unsafe_members(artifact_export, name, code):
    directory, _ = artifact_export
    metadata, entries = read_animations(directory)
    entries[name] = b"unexpected"
    reseal_animations(directory, metadata, entries)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == code


@pytest.mark.parametrize("name", ["animations.zip", "animation-manifest.json"])
def test_animation_verifier_blocks_missing_announced_artifact(artifact_export, name):
    directory, _ = artifact_export
    (directory / name).unlink()
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.status == "BLOCKED"
    assert error.value.details["missing"] == [name]


def test_animation_verifier_keeps_legacy_bundles_readable(artifact_export):
    directory, _ = artifact_export
    runtime = json.loads((directory / "runtime.json").read_bytes())
    runtime.pop("animationExports")
    added = {"animations.zip", "animation-manifest.json"}
    runtime["files"] = [entry for entry in runtime["files"] if entry["name"] not in added]
    _test_write_json(directory / "runtime.json", runtime)
    with zipfile.ZipFile(directory / "bundle.zip") as archive:
        entries = {name: archive.read(name) for name in archive.namelist() if name not in added}
    _test_zip_replace(directory / "bundle.zip", entries)
    for name in added:
        (directory / name).unlink()
    _test_reseal_artifacts(directory)
    result = verify_artifacts(directory)
    assert result["animationClips"] == []
    assert len(result["files"]) == 6


@pytest.mark.parametrize("webp_available", [True, False])
def test_animation_verifier_accepts_explicit_optional_format_omissions(project, tmp_path, monkeypatch, webp_available):
    from alignment import animation_exports
    if not webp_available:
        monkeypatch.setattr(animation_exports.features, "check", lambda name: False)
    snapshot, path, _ = project
    snapshot["clips"][0]["occurrences"][0]["durationMs"] = 1
    directory = tmp_path / "short-duration"
    build_bundle(snapshot, ["idle"], path, directory, "short-duration")
    result = verify_artifacts(directory)
    formats = result["animationClips"][0]
    assert set(formats["omittedFormats"]) == ({"gif"} if webp_available else {"gif", "webp"})
    assert set(formats["formatsChecked"]) == ({"stripPng", "gridPng", "webp"} if webp_available else {"stripPng", "gridPng"})
    assert result["clips"][0]["durationMs"] == 1


@pytest.mark.parametrize("interpolation", [None, {}, {"method": "rife", "fraction": 2, "sourceFrameIndices": [1, 2]},
    {"method": "rife", "fraction": .5, "sourceFrameIndices": [1, 1]}])
def test_animation_verifier_rejects_incomplete_interpolation_lineage(artifact_export, interpolation):
    directory, _ = artifact_export
    runtime = json.loads((directory / "runtime.json").read_bytes())
    runtime["frameSources"][0].update(interpolated=True, interpolation=interpolation)
    _test_write_json(directory / "runtime.json", runtime)
    _test_reseal_artifacts(directory)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "INTERPOLATION_LINEAGE_MISMATCH"
