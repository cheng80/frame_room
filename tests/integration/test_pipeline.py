"""Synthetic pixel oracles for the real product pipeline (no provider calls)."""
import copy
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
from PIL import Image, ImageDraw
import pytest

from alignment.pipeline import (ENGINE_COMMIT, PipelineError, build_bundle,
    cutout_image, extract_regions, inspect_image, render_occurrence, suggest_anchor)


def digest(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def project(tmp_path):
    paths = {}
    p = {"projectId": "project", "schemaVersion": 1, "revision": 7,
         "assets": [], "frames": [], "alignmentGroups": [], "alignments": {},
         "references": [], "clips": [], "outline": {"enabled": False, "mode": "bake"}}
    def add(image, fid, anchor=None):
        path = tmp_path / (fid + ".png")
        image.save(path)
        paths[fid] = path
        p["assets"].append({"assetId": fid, "sha256": digest(path.read_bytes()), **inspect_image(path)})
        p["frames"].append({"frameId": fid, "frameVersionId": fid, "rawAssetId": fid, "imageAssetId": fid,
             "sourceRect": {"x": 0, "y": 0, "width": image.width, "height": image.height},
             "sourceToFrameTransform": {"scaleX": 1, "scaleY": 1, "offsetX": 0, "offsetY": 0}, "review": "approved"})
        if not p["alignmentGroups"]:
            p["alignmentGroups"].append({"alignmentGroupId": "group", "groupRevisionId": "g1", "frameVersionIds": [],
                 "mode": "preserve-source-scale", "sharedScale": 1,
                 "cell": {"width": 32, "height": 32, "edge": 2}, "targetAnchor": {"x": 16, "y": 24},
                 "bodyMeasurement": None, "resampler": "nearest", "roundingVersion": "js-round-v1"})
        p["alignmentGroups"][0]["frameVersionIds"].append(fid)
        p["alignments"][fid] = {"frameVersionId": fid, "groupRevisionId": "g1", "approval": "approved",
            "method": "manual", "anchorSpace": "crop", "contactMode": "grounded", "sourceAnchor": anchor or {"x": 2, "y": 4},
            "authoredOffsetPx": {"x": 0, "y": 0}}
        return fid
    a = Image.new("RGBA", (4, 4), (9, 33, 77, 0))
    a.putpixel((1, 1), (100, 50, 25, 128))
    a.putpixel((1, 2), (10, 20, 30, 255))
    a.putpixel((2, 3), (90, 80, 70, 255))
    add(a, "a")
    p["references"] = [{"referenceRevisionId": "ref1", "identityAssetId": "a", "approval": "approved"}]
    p["clips"] = [{"clipId": "idle", "clipRevisionId": "clip-v1", "referenceRevisionId": "ref1", "review": "approved",
        "name": "대기", "defaultFps": 10, "loop": True, "endBehavior": "hold-last",
        "occurrences": [{"occurrenceId": "o1", "frameVersionId": "a", "durationMs": 80, "timingMode": "explicit", "transform": {}, "pixelEdits": []}]}]
    return p, paths.__getitem__, add


def render(project, index=0):
    p, paths, _ = project
    return render_occurrence(p, p["clips"][0], p["clips"][0]["occurrences"][index], paths)


def bundle(project, path, **kwargs):
    p, paths, _ = project
    return build_bundle(p, ["idle"], paths, path, "export", **kwargs)


def test_alpha_stats_full_rgba_fingerprint(tmp_path):
    image = Image.new("RGBA", (5, 1))
    image.putdata([(80, 90, 100, a) for a in (0, 1, 15, 16, 255)])
    path = tmp_path / "alpha.png"
    image.save(path)
    stats = inspect_image(path)
    assert stats["alphaStats"] == {"transparent": 1, "partial": 3, "opaque": 1}
    assert stats["decodedHash"] == digest(image.tobytes())
    opaque = Image.new("RGBA", (8, 8), "white")
    ImageDraw.Draw(opaque).rectangle((0, 0, 3, 3), fill="gray")
    opaque.save(path)
    assert inspect_image(path)["alphaStats"] == {"transparent": 0, "partial": 0, "opaque": 64}


def test_whole_and_regions_are_prefit_and_preserve_hidden_rgb(tmp_path):
    image = Image.new("RGBA", (18, 12), (44, 55, 66, 0))
    ImageDraw.Draw(image).rectangle((4, 2, 7, 10), fill=(20, 30, 40, 255))
    path = tmp_path / "source.png"
    image.save(path)
    before = path.read_bytes()
    assert extract_regions(path, {"mode": "whole"})[0]["image"].tobytes() == image.tobytes()
    result = extract_regions(path, {"mode": "regions", "regions": [{"x": 3, "y": 1, "width": 8, "height": 10}]})[0]
    assert result["image"].size == (8, 10)
    assert result["image"].tobytes() == image.crop((3, 1, 11, 11)).tobytes()
    assert result["sourceToFrameTransform"] == {"scaleX": 1, "scaleY": 1, "offsetX": -3, "offsetY": -1}
    assert path.read_bytes() == before


def test_components_keep_all_faint_and_tiny_equipment(tmp_path):
    image = Image.new("RGBA", (12, 6))
    ImageDraw.Draw(image).rectangle((1, 1, 3, 4), fill=(70, 80, 90, 255))
    image.putpixel((10, 3), (120, 80, 10, 1))
    image.putpixel((9, 3), (10, 20, 30, 16))
    image.putpixel((11, 5), (99, 33, 88, 15))
    path = tmp_path / "components.png"
    image.save(path)
    crops = extract_regions(path, {"mode": "components", "minArea": 4})
    restored = Image.new("RGBA", image.size)
    for crop in crops:
        restored.paste(crop["image"], (crop["rect"]["x"], crop["rect"]["y"]))
    assert restored.tobytes() == image.tobytes()
    assert len(crops) == 3
    assert sum(c["belowMinArea"] for c in crops) == 2
    assert all(c["sourceToFrameTransform"]["scaleX"] == 1 for c in crops)


def test_grid_does_not_slice_crossing_weapon(tmp_path):
    image = Image.new("RGBA", (12, 6))
    ImageDraw.Draw(image).line((2, 3, 9, 3), fill=(100, 40, 90, 255))
    image.putpixel((9, 3), (0, 255, 0, 1))
    path = tmp_path / "sheet.png"
    image.save(path)
    crops = extract_regions(path, {"mode": "grid", "rows": 1, "columns": 2})
    assert len(crops) == 2
    for crop in crops:
        assert np.count_nonzero(np.asarray(crop["image"])[..., 3]) == 8
        assert crop["reviewRequired"] and crop["warnings"]


def test_grid_remainder_pixels_preserved(tmp_path):
    image = Image.new("RGBA", (11, 9))
    for x, y in ((1, 1), (6, 1), (10, 8)):
        image.putpixel((x, y), (255, 0, 0, 255))
    path = tmp_path / "odd.png"
    image.save(path)
    crops = extract_regions(path, {"mode": "grid", "rows": 2, "columns": 2})
    assert sum(c["rect"]["width"] * c["rect"]["height"] for c in crops) == 99
    assert sum(np.count_nonzero(np.asarray(c["image"])[..., 3]) for c in crops) == 3


def test_anchor_uses_ge16_lower_band_exclusive_bottom():
    image = Image.new("RGBA", (20, 25))
    ImageDraw.Draw(image).rectangle((4, 2, 8, 21), fill=(0, 0, 0, 16))
    image.putpixel((11, 21), (0, 0, 0, 255))
    image.putpixel((18, 24), (0, 0, 0, 15))
    assert suggest_anchor(image) == {"x": 7.5, "y": 22}
    with pytest.raises(PipelineError, match="발 후보"):
        suggest_anchor(Image.new("RGBA", (4, 4), (1, 2, 3, 15)))


def test_native_alpha_cutout_keeps_every_byte_of_rgba(tmp_path):
    source, target = tmp_path / "native.png", tmp_path / "out.png"
    image = Image.new("RGBA", (5, 1))
    image.putdata([(77, 88, 99, a) for a in (0, 1, 15, 16, 255)])
    image.save(source)
    before = source.read_bytes()
    result = cutout_image(source, target, {"key": "white"})
    assert result["skipped"] and result["reason"] == "native-alpha"
    assert Image.open(target).tobytes() == image.tobytes()
    assert source.read_bytes() == before
    with pytest.raises(PipelineError) as error:
        cutout_image(source, source, {})
    assert error.value.code == "IMMUTABLE_ASSET"


@pytest.mark.parametrize("color,key", [((255,255,255,255), "white"), ((0,255,0,255), "green"), ((255,0,255,255), "magenta")])
def test_real_engine_cutout_uniform_background(tmp_path, color, key):
    source, target = tmp_path / "opaque.png", tmp_path / "cut.png"
    image = Image.new("RGBA", (64, 64), color)
    ImageDraw.Draw(image).rectangle((20, 20, 43, 43), fill=(90, 40, 20, 255))
    image.save(source)
    result = cutout_image(source, target, {"key": key, "tolerance": 24})
    out = Image.open(target).convert("RGBA")
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((32, 32)) == (90, 40, 20, 255)
    assert result["reviewRequired"]


@pytest.mark.parametrize("scale", [.75, 1, 1.25])
def test_shared_scale_preserves_standing_crouching_ratio(project, scale):
    p, _, add = project
    g = p["alignmentGroups"][0]
    g.update(sharedScale=scale, cell={"width": 800, "height": 800, "edge": 2}, targetAnchor={"x": 400, "y": 700})
    for fid, height in (("standing", 471), ("crouching", 320)):
        add(Image.new("RGBA", (10, height), (10, 20, 30, 255)), fid, {"x": 5, "y": height})
        p["clips"][0]["occurrences"][0]["frameVersionId"] = fid
        output, qa = render(project)
        box = output.getchannel("A").getbbox()
        assert abs((box[3]-box[1])-height*scale) <= 1
        assert box[3] == 700
        assert qa["sharedScale"] == scale
        assert not qa["errors"]


def test_manual_anchor_negative_half_round_and_raw_mapping(project):
    p, _, _ = project
    g, a = p["alignmentGroups"][0], p["alignments"]["a"]
    g["targetAnchor"] = {"x": 0, "y": 24}
    a["sourceAnchor"] = {"x": .5, "y": 4}
    output, qa = render(project)
    assert qa["residual"] == {"x": .5, "y": 0}
    assert output.getpixel((1, 21)) == (100, 50, 25, 128)
    # Same local point expressed in raw coordinates produces exactly same bake.
    p["frames"][0]["sourceToFrameTransform"].update(offsetX=-10, offsetY=-20)
    a.update(anchorSpace="raw", sourceAnchor={"x": 10.5, "y": 24})
    second, _ = render(project)
    assert second.tobytes() == output.tobytes()
    assert a["method"] == "manual" and a["sourceAnchor"] == {"x": 10.5, "y": 24}


def test_airborne_root_trajectory_not_grounded_feet(project):
    p, _, _ = project
    a = p["alignments"]["a"]
    a.update(contactMode="airborne", rootAnchor={"x": 2, "y": 2}, authoredOffsetPx={"x": 0, "y": -8})
    output, qa = render(project)
    assert output.getchannel("A").getbbox()[3] == 18
    assert qa["anchor"] == [16, 16]
    a.pop("rootAnchor")
    with pytest.raises(PipelineError) as error:
        render(project)
    assert error.value.code == "ROOT_ANCHOR_REQUIRED"


@pytest.mark.parametrize("side,offset,expected", [("left",(-16,0),3),("right",(15,0),1),("top",(0,-21),2),("bottom",(0,10),2)])
def test_safe_rect_overflow_all_sides_uses_alpha1(project, side, offset, expected):
    p, _, add = project
    image = Image.new("RGBA", (4, 4))
    image.putpixel((1, 1), (8, 9, 10, 1))
    add(image, "faint", {"x": 2, "y": 4})
    o = p["clips"][0]["occurrences"][0]
    o.update(frameVersionId="faint", transform={"dx": offset[0], "dy": offset[1]})
    _, qa = render(project)
    assert qa["overflowPx"][side] == expected
    assert any(e["code"] == "FRAME_OVERFLOW" for e in qa["errors"])
    assert qa["warnings"][0]["code"] == "LOW_ALPHA_SUPPORT"


def test_pixel_edits_then_flip_and_offset(project):
    p, _, _ = project
    o = p["clips"][0]["occurrences"][0]
    o["pixelEdits"] = [{"x": 10, "y": 10, "color": [7, 8, 9, 123]}, {"x": 15, "y": 22, "color": [90, 80, 70, 0]}]
    o["transform"] = {"flipX": True, "dx": 2, "pivot": {"x": 16, "y": 16}}
    out, qa = render(project)
    assert out.getpixel((23, 10)) == (7, 8, 9, 123)
    assert out.getpixel((18, 22)) == (0, 0, 0, 0)
    assert not qa["errors"]


@pytest.mark.parametrize("transform,location", [({"flipY": True},(10,21)), ({"rotationDeg":90},(10,21)), ({"scaleX":2,"scaleY":1},(4,10)), ({"shearX":1},(4,10))])
def test_affine_canvas_pivot_transform_pixels(project, transform, location):
    p, _, add = project
    add(Image.new("RGBA", (1, 1)), "empty", {"x": 0, "y": 0})
    p["clips"][0]["occurrences"][0].update(frameVersionId="empty", pixelEdits=[{"x":10,"y":10,"color":[255,0,0,255]}], transform={**transform,"pivot":{"x":16,"y":16}})
    out, _ = render(project)
    assert out.getpixel(location) == (255,0,0,255)


@pytest.mark.parametrize("directions,count", [(4,5),(8,9)])
def test_outline_integer_directions_opacity_and_source_last(project, directions, count):
    p, _, add = project
    add(Image.new("RGBA", (1, 1), (200,10,20,255)), "dot", {"x":0,"y":0})
    p["clips"][0]["occurrences"][0]["frameVersionId"] = "dot"
    p["outline"] = {"enabled":True,"mode":"bake","colorRGBA":[10,80,180,128],"thicknessPx":2,"directions":directions,"opacityPerCopy":.5}
    out, qa = render(project)
    assert out.getpixel((16,24)) == (200,10,20,255)
    assert out.getpixel((18,24)) == (10,80,180,64)
    assert np.count_nonzero(np.asarray(out)[...,3]) == count
    assert not qa["errors"]


def test_baked_outline_rechecks_overflow(project):
    p, _, _ = project
    p["clips"][0]["occurrences"][0]["transform"] = {"dy":5}
    _, before = render(project)
    assert not before["errors"]
    p["outline"] = {"enabled":True,"mode":"bake","thicknessPx":3,"directions":8}
    _, after = render(project)
    assert after["overflowPx"]["bottom"] == 2


def test_bundle_occurrence_timing_dedup_and_full_rgba_parity(project, tmp_path):
    p, paths, _ = project
    first = p["clips"][0]["occurrences"][0]
    second = copy.deepcopy(first); second.update(occurrenceId="o2", durationMs=120, transform={"flipX":True}, pixelEdits=[{"x":16,"y":22,"color":[6,5,4,127]}])
    third = copy.deepcopy(first); third.update(occurrenceId="o3", durationMs=200)
    p["clips"][0]["occurrences"] = [first,second,third]
    before = copy.deepcopy(p)
    original = paths("a").read_bytes()
    out = tmp_path / "export"
    result = bundle(project, out)
    manifest = result["manifest"]
    assert p == before and paths("a").read_bytes() == original
    assert result["qa"]["fullRGBAParity"] and result["qa"]["status"] == "verified"
    assert manifest["engineCommit"] == ENGINE_COMMIT
    assert len(manifest["frames"]) == 2
    slots = manifest["clips"][0]["occurrences"]
    assert [o["durationMs"] for o in slots] == [80,120,200]
    assert [o["id"] for o in slots] == ["o1","o2","o3"]
    assert slots[0]["renderedFrameId"] == slots[2]["renderedFrameId"]
    atlas = Image.open(out / "atlas.png").convert("RGBA")
    frames = {f["id"]:f for f in manifest["frames"]}
    with zipfile.ZipFile(out/"pngs.zip") as archive:
        seq = json.loads(archive.read("manifest.json"))
        for index, o in enumerate(seq["clips"][0]["occurrences"]):
            exported = Image.open(io.BytesIO(archive.read(o["file"]))).convert("RGBA")
            frame = frames[o["renderedFrameId"]]; r = frame["rect"]
            crop = atlas.crop((r["x"],r["y"],r["x"]+r["width"],r["y"]+r["height"]))
            direct, _ = render(project,index)
            assert direct.tobytes() == crop.tobytes() == exported.tobytes()
            pixels = np.asarray(exported)
            assert np.all(pixels[pixels[...,3]==0,:3]==0)
    ase = json.loads((out/"aseprite.json").read_bytes())
    assert [f["duration"] for f in ase["frames"]] == [80,120,200]
    assert ase["meta"]["frameTags"][0]["to"] == 2
    for f in result["fileHashes"]:
        assert digest((out/f["name"]).read_bytes()) == f["sha256"]
    with zipfile.ZipFile(out/"bundle.zip") as archive:
        assert json.loads(archive.read("runtime.json")) == manifest
        assert archive.read("atlas.png") == (out/"atlas.png").read_bytes()
    with pytest.raises(PipelineError) as error:
        bundle(project,out)
    assert error.value.code == "IMMUTABLE_EXPORT"


def test_preview_only_outline_does_not_change_bitmap_or_recipe(project,tmp_path):
    p, _, _ = project
    one = bundle(project,tmp_path/"one")
    p["outline"] = {"enabled":True,"mode":"preview-only","colorRGBA":[20,30,40,255],"thicknessPx":4,"directions":4}
    two = bundle(project,tmp_path/"two")
    assert one["manifest"]["recipeHash"] == two["manifest"]["recipeHash"]
    assert (tmp_path/"one/atlas.png").read_bytes() == (tmp_path/"two/atlas.png").read_bytes()
    p["outline"]["mode"]="bake"
    three = bundle(project,tmp_path/"three")
    assert three["manifest"]["recipeHash"] != two["manifest"]["recipeHash"]


@pytest.mark.parametrize("mutation,code", [
    (lambda p:p["clips"][0].update(occurrences=[]),"EMPTY_TIMELINE"),
    (lambda p:p["clips"][0].update(review="pending"),"CLIP_UNAPPROVED"),
    (lambda p:p["references"][0].update(approval="draft"),"REFERENCE_UNAPPROVED"),
    (lambda p:p["frames"][0].update(review="pending"),"FRAME_UNAPPROVED"),
    (lambda p:p["alignments"]["a"].update(approval="pending"),"ANCHOR_UNAPPROVED"),
    (lambda p:p["alignments"]["a"].update(groupRevisionId="old"),"STALE_ALIGNMENT"),
    (lambda p:p.update(savedRevision=6),"STALE_SAVE"),
    (lambda p:p.update(savePending=True),"STALE_SAVE"),
    (lambda p:p["clips"][0].update(endBehavior="stop"),"UNSUPPORTED_TIMING"),
    (lambda p:p["alignmentGroups"][0].update(referenceRevisionId="other"),"STALE_REFERENCE"),
    (lambda p:p["alignmentGroups"][0].update(mode="shared-scale-foot-anchor"),"BODY_MEASUREMENT_UNAPPROVED"),
])
def test_strict_gates_publish_nothing(project,tmp_path,mutation,code):
    mutation(project[0])
    out=tmp_path/"blocked"
    with pytest.raises(PipelineError) as error:
        bundle(project,out)
    assert error.value.code==code
    assert not out.exists()
    assert not list(tmp_path.glob(".bake-*"))


@pytest.mark.parametrize("duration", [0,-1,1.2,float("nan"),True,60001,None])
def test_invalid_timing_not_replaced_by_fps(project,tmp_path,duration):
    project[0]["clips"][0]["occurrences"][0]["durationMs"]=duration
    with pytest.raises(PipelineError) as error:
        bundle(project,tmp_path/"bad")
    assert error.value.code=="UNSUPPORTED_TIMING"


def test_pending_preview_is_never_verified(project,tmp_path):
    project[0]["alignments"]["a"]["approval"]="pending"
    result=bundle(project,tmp_path/"preview",strict=False)
    assert result["qa"]["status"]=="needs_review"
    assert result["manifest"]["qaStatus"]=="needs_review"
    assert result["status"]=="needs_review"


def test_previous_approved_reference_and_unselected_invalid_clip_allowed(project,tmp_path):
    p, _, _=project
    p["activeReferenceRevisionId"]="ref-draft"
    p["references"].append({"referenceRevisionId":"ref-draft","approval":"draft"})
    p["clips"].append({"clipId":"broken","review":"pending","occurrences":[]})
    assert bundle(project,tmp_path/"valid")["qa"]["status"]=="verified"
    with pytest.raises(PipelineError) as error:
        build_bundle(p,["idle","broken"],project[1],tmp_path/"invalid","id")
    assert error.value.code=="EMPTY_TIMELINE"


def test_hash_tamper_and_missing_source_block(project,tmp_path):
    p, paths, _=project
    Image.new("RGBA",(4,4),(255,0,0,255)).save(paths("a"))
    with pytest.raises(PipelineError) as error:
        bundle(project,tmp_path/"tampered")
    assert error.value.code=="ASSET_HASH_MISMATCH"
    paths("a").unlink()
    with pytest.raises(PipelineError) as error:
        bundle(project,tmp_path/"missing")
    assert error.value.code=="ASSET_MISSING"


def test_empty_alpha_and_overflow_strict_gate(project,tmp_path):
    p, _, add=project
    add(Image.new("RGBA",(2,2)),"empty")
    p["clips"][0]["occurrences"][0]["frameVersionId"]="empty"
    with pytest.raises(PipelineError) as error:
        bundle(project,tmp_path/"empty")
    assert error.value.code=="EMPTY_ALPHA"
    p["clips"][0]["occurrences"][0].update(frameVersionId="a",transform={"dx":40})
    with pytest.raises(PipelineError) as error:
        bundle(project,tmp_path/"overflow")
    assert error.value.code=="FRAME_OVERFLOW"
    assert error.value.details["frames"][0]["overflowPx"]["right"]>0


def test_locked_snapshot_not_mixed_with_edit_during_bake(project,tmp_path):
    p, paths, _=project
    def racing_path(aid):
        p["revision"]=8
        p["clips"][0]["occurrences"][0]["durationMs"]=900
        return paths(aid)
    result=build_bundle(p,["idle"],racing_path,tmp_path/"locked","id")
    assert result["manifest"]["projectRevision"]==7
    assert result["manifest"]["clips"][0]["occurrences"][0]["durationMs"]==80
    assert p["revision"]==8


def test_approved_body_landmarks_define_one_scale(project,tmp_path):
    g=project[0]["alignmentGroups"][0]
    g.update(mode="shared-scale-foot-anchor",bodyMeasurement={"topY":2,"bottomY":6,"targetHeight":5,"approved":True},sharedScale=1.25)
    assert bundle(project,tmp_path/"ok")["qa"]["status"]=="verified"
    g["sharedScale"]=1
    with pytest.raises(PipelineError) as error:
        bundle(project,tmp_path/"stale")
    assert error.value.code=="STALE_BODY_SCALE"


def test_empty_clip_list_never_defaults_to_all_candidates(project,tmp_path):
    with pytest.raises(PipelineError) as error:
        build_bundle(project[0],[],project[1],tmp_path/"empty-selection","id")
    assert error.value.code=="EMPTY_TIMELINE"


def test_overlapping_outline_copies_accumulate_alpha(project):
    p, _, add = project
    dots = Image.new("RGBA",(3,1))
    dots.putpixel((0,0),(200,0,0,255)); dots.putpixel((2,0),(200,0,0,255))
    add(dots,"dots",{"x":1,"y":0})
    p["clips"][0]["occurrences"][0]["frameVersionId"]="dots"
    p["outline"]={"enabled":True,"mode":"bake","directions":4,"thicknessPx":1,"opacityPerCopy":.5,"colorRGBA":[10,20,30,255]}
    out,_=render(project)
    assert out.getpixel((16,24))==(10,20,30,192)
    assert out.getpixel((15,24))==(200,0,0,255)


def test_dedup_keeps_distinct_anchor_and_lineage_per_occurrence(project,tmp_path):
    p, _, add=project
    bitmap=Image.new("RGBA",(1,1),(7,8,9,255))
    add(bitmap,"one",{"x":0,"y":0});add(bitmap,"two",{"x":1,"y":0})
    # Different anchor compensated by an authored offset: identical bitmap.
    p["alignments"]["two"]["authoredOffsetPx"]={"x":1,"y":0}
    p["clips"][0]["occurrences"]=[{"occurrenceId":fid,"frameVersionId":fid,"durationMs":100,"timingMode":"explicit"} for fid in ("one","two")]
    result=bundle(project,tmp_path/"dedup")
    assert len(result["manifest"]["frames"])==1
    slots=result["manifest"]["clips"][0]["occurrences"]
    assert [o["frameVersionId"] for o in slots]==["one","two"]
    assert [o["anchor"] for o in slots]==[[16,24],[17,24]]


def test_corrupt_valid_zip_blocks_atomic_publication(project,tmp_path,monkeypatch):
    import alignment.pipeline as pipeline
    write_zip=pipeline._zip
    def corrupt(path,entries):
        if path.name=="pngs.zip":
            entries=[(name,b"tampered" if name.endswith(".png") else data) for name,data in entries]
        write_zip(path,entries)
    monkeypatch.setattr(pipeline,"_zip",corrupt)
    with pytest.raises(PipelineError) as error:
        bundle(project,tmp_path/"corrupt")
    assert error.value.code=="ARTIFACT_HASH_MISMATCH"
    assert not (tmp_path/"corrupt").exists()
    assert not list(tmp_path.glob(".bake-*"))


def test_explicit_output_preview_only_suppresses_baked_outline(project,tmp_path):
    p, _, _=project
    p["outline"]={"enabled":True,"mode":"bake","thicknessPx":2,"directions":8}
    without=bundle(project,tmp_path/"without",outline_mode="preview-only")
    p["outline"]["enabled"]=False
    disabled=bundle(project,tmp_path/"disabled")
    assert without["manifest"]["recipeHash"]==disabled["manifest"]["recipeHash"]
    assert (tmp_path/"without/atlas.png").read_bytes()==(tmp_path/"disabled/atlas.png").read_bytes()


def test_empty_grid_cell_preserved_for_review(tmp_path):
    image=Image.new("RGBA",(12,6))
    image.putpixel((1,2),(10,20,30,255))
    path=tmp_path/"emptycell.png";image.save(path)
    crops=extract_regions(path,{"mode":"grid","columns":2,"rows":1})
    assert len(crops)==2
    assert crops[1]["alphaStats"]=={"transparent":36,"partial":0,"opaque":0}


def test_fps_60_and_explicit_duration_remain_separate(project,tmp_path):
    p, _, _=project
    clip=p["clips"][0];clip["defaultFps"]=60
    o=clip["occurrences"][0]
    o.update(durationMs=17,timingMode="fps")
    clone=copy.deepcopy(o);clone.update(occurrenceId="explicit",durationMs=83,timingMode="explicit")
    clip["occurrences"].append(clone)
    result=bundle(project,tmp_path/"fps")
    assert [o["durationMs"] for o in result["manifest"]["clips"][0]["occurrences"]]==[17,83]
    o["durationMs"]=16
    with pytest.raises(PipelineError) as error: bundle(project,tmp_path/"stale-fps")
    assert error.value.code=="STALE_TIMING"


def test_real_gunner_prefit_height_and_manual_anchor(project,tmp_path):
    """REAL_ASSET aligned images; does NOT claim raw cutout/visual approval."""
    root=Path(__file__).resolve().parents[2]/"research/hero-inc/2026-10-03-implementation-design/artifacts/source-assets"
    if not root.exists():
        pytest.skip("로컬 연구용 원본은 Git 저장소에 포함하지 않습니다.")
    provenance=json.loads((root/"provenance.json").read_bytes())
    hashes={a["file"]:a["sha256"] for a in provenance["assets"]}
    p, _, add=project
    group=p["alignmentGroups"][0]
    group.update(cell={"width":512,"height":512,"edge":2},targetAnchor={"x":256,"y":494})
    measured=[]
    for pose,expected_height in ((0,471),(3,320)):
        path=root/f"pose-{pose}-aligned.png"
        assert digest(path.read_bytes())==hashes[path.name]
        crop=extract_regions(path,{"mode":"whole"})[0]
        image=crop["image"]
        assert suggest_anchor(image)=={"x":256 if pose==0 else 256.5,"y":494}
        add(image,f"pose{pose}",{"x":256 if pose==0 else 256.5,"y":494})
        p["clips"][0]["occurrences"][0]["frameVersionId"]=f"pose{pose}"
        output,qa=render(project)
        ys,xs=np.where(np.asarray(output)[...,3]>=16)
        height=int(ys.max()-ys.min()+1)
        measured.append(height)
        assert height==expected_height
        assert int(ys.max())+1==494
        assert not qa["errors"]
        assert digest(path.read_bytes())==hashes[path.name]
    assert measured[1]/measured[0]==320/471


def test_worker_extract_metadata_faint_anchor_and_typed_asset_gate(project,tmp_path,monkeypatch):
    from services.worker import task
    from services.api.store import AppError
    p, paths, add=project
    image=Image.new("RGBA",(8,4))
    image.putpixel((6,2),(90,80,70,1))
    add(image,"faintonly",{"x":6,"y":3})
    p["defaultCell"]={"width":32,"height":32}
    p["generations"]=[]
    monkeypatch.setattr(task.s,"asset_path",paths)
    def registered(image,name,provenance):
        return {"assetId":"derived","sha256":digest(image.tobytes()),"provenance":provenance}
    monkeypatch.setattr(task,"asset_from_image",registered)
    result=task.execute({"snapshot":p,"operation":"extract","request":{"assetIds":["faintonly"],"params":{"mode":"components"}}},tmp_path/"worker")
    assert len(result["frames"])==1
    frame=result["frames"][0]
    assert frame["extractionReview"]["belowMinArea"] is True
    alignment=result["alignments"][frame["frameVersionId"]]
    assert alignment["sourceAnchor"]=={"x":.5,"y":1}
    assert alignment["approval"]=="pending"
    def missing(aid): raise AppError("ASSET_MISSING","없는 원본",404)
    with pytest.raises(AppError) as error:
        build_bundle(p,["idle"],missing,tmp_path/"missing-typed","id")
    assert error.value.code=="ASSET_MISSING"


@pytest.fixture
def artifact_export(project, tmp_path):
    """Actual local bake with two clips, duplicate slots and a three-level lineage."""
    p, paths, add = project
    add(Image.new("RGBA", (4, 4), (8, 10, 12, 255)), "provider-raw")
    add(Image.new("RGBA", (4, 4), (8, 10, 12, 128)), "cutout")
    assets = {a["assetId"]: a for a in p["assets"]}
    assets["provider-raw"]["provenance"] = {"kind": "real-provider", "generationVersionId": "generation-one"}
    assets["cutout"]["provenance"] = {"kind": "cutout", "parentAssetId": "provider-raw"}
    assets["a"]["provenance"] = {"kind": "raw-crop", "parentAssetId": "cutout"}
    p["frames"][0].update(rawAssetId="cutout", generationVersionId="generation-one", parentFrameVersionId="old-version")
    first = p["clips"][0]["occurrences"][0]
    second = copy.deepcopy(first)
    second.update(occurrenceId="o2", durationMs=120, transform={"flipX": True},
                  pixelEdits=[{"x": 16, "y": 22, "color": [12, 34, 56, 127]}])
    third = copy.deepcopy(first)
    third.update(occurrenceId="o3", durationMs=200)
    p["clips"][0]["occurrences"] = [first, second, third]
    one_shot = copy.deepcopy(p["clips"][0])
    one_shot.update(clipId="attack", clipRevisionId="attack-v1", loop=False, name="단발")
    p["clips"].append(one_shot)
    directory = tmp_path / "artifact-export"
    result = build_bundle(p, ["idle", "attack"], paths, directory, "synthetic-export")
    return directory, result


def _test_write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _test_zip_replace(path, entries):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


def _test_reseal_artifacts(directory):
    """Rehash fault-injected copies so semantic checks, not stale hashes, catch them."""
    runtime = json.loads((directory / "runtime.json").read_bytes())
    for item in runtime["files"]:
        item["sha256"] = digest((directory / item["name"]).read_bytes())
    runtime["atlas"]["sha256"] = digest((directory / "atlas.png").read_bytes())
    _test_write_json(directory / "runtime.json", runtime)
    with zipfile.ZipFile(directory / "bundle.zip") as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    for name in ("runtime.json", *(item["name"] for item in runtime["files"])):
        entries[name] = (directory / name).read_bytes()
    _test_zip_replace(directory / "bundle.zip", entries)


def test_artifact_verifier_all_occurrences_loop_and_lineage_read_only(artifact_export):
    from alignment.verify_artifacts import verify_artifacts
    directory, baked = artifact_export
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}
    result = verify_artifacts(directory)
    assert result["status"] == "PASS" and result["fullRGBAParity"] is True
    assert result["occurrencesChecked"] == 6 and result["renderedFramesChecked"] == 2
    assert [clip["loop"] for clip in result["clips"]] == [True, False]
    assert all(clip["boundariesMs"] == [80, 200, 400] for clip in result["clips"])
    assert result["frameSourcesChecked"] == 1 and result["sourceAssetsChecked"] == 3
    assert result["externalParentFrameVersionIds"] == ["old-version"]
    sources = {a["assetId"]: a for a in baked["manifest"]["sourceAssets"]}
    assert set(sources) == {"a", "cutout", "provider-raw"}
    assert {edge["parentAssetId"] for edge in result["parentHashLinks"]} == {"cutout", "provider-raw"}
    for edge in result["parentHashLinks"]:
        assert edge["parentSha256"] == sources[edge["parentAssetId"]]["sha256"]
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}


@pytest.mark.parametrize("pixel", [(9, 8, 7, 0), (100, 50, 25, 127)])
def test_artifact_verifier_catches_full_rgba_after_rehash(artifact_export, pixel):
    from alignment.verify_artifacts import ArtifactValidationError, verify_artifacts
    directory, _ = artifact_export
    with zipfile.ZipFile(directory / "pngs.zip") as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(entries["manifest.json"])
    slot = manifest["clips"][0]["occurrences"][0]
    image = Image.open(io.BytesIO(entries[slot["file"]])).convert("RGBA")
    image.putpixel((0, 0) if pixel[3] == 0 else (15, 21), pixel)
    stream = io.BytesIO(); image.save(stream, format="PNG")
    entries[slot["file"]] = stream.getvalue()
    slot["sha256"] = digest(stream.getvalue())
    entries["manifest.json"] = json.dumps(manifest).encode()
    _test_zip_replace(directory / "pngs.zip", entries)
    _test_reseal_artifacts(directory)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "RGBA_MISMATCH"
    assert error.value.details["differingPixels"] == 1


@pytest.mark.parametrize("change,code", [
    (lambda m: m["clips"][0].update(loop=False), "TIMING_MISMATCH"),
    (lambda m: m["clips"][0]["occurrences"][0].update(durationMs=81), "TIMELINE_MISMATCH"),
    (lambda m: m["clips"][0]["occurrences"].reverse(), "TIMELINE_MISMATCH"),
    (lambda m: m.update(projectRevision=999), "SNAPSHOT_MISMATCH"),
])
def test_artifact_verifier_sequence_consistency_after_rehash(artifact_export, change, code):
    from alignment.verify_artifacts import ArtifactValidationError, verify_artifacts
    directory, _ = artifact_export
    with zipfile.ZipFile(directory / "pngs.zip") as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(entries["manifest.json"])
    change(manifest)
    entries["manifest.json"] = json.dumps(manifest).encode()
    _test_zip_replace(directory / "pngs.zip", entries)
    _test_reseal_artifacts(directory)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == code


@pytest.mark.parametrize("change,code", [
    (lambda m: m.update(frameSources=[]), "LINEAGE_MISSING"),
    (lambda m: m["frameSources"][0].update(frameVersionId="missing"), "FRAME_SOURCE_MISSING"),
    (lambda m: m["sourceAssets"][1].pop("sha256"), "HASH_MISSING"),
    (lambda m: m["sourceAssets"][0]["provenance"].update(parentAssetId="missing"), "PARENT_ASSET_MISSING"),
    (lambda m: m["sourceAssets"][0]["provenance"].update(parentSha256="0"*64), "PARENT_HASH_MISMATCH"),
    (lambda m: m["sourceAssets"][1].update(provenance={"parentAssetId":"a"}), "LINEAGE_CYCLE"),
    (lambda m: m["frameSources"][0].update(rawAssetId="missing"), "FRAME_SOURCE_MISSING"),
    (lambda m: m["frameSources"][0].update(generationVersionId="wrong"), "GENERATION_LINEAGE_MISMATCH"),
    (lambda m: m["frameSources"][0].pop("sourceToFrameTransform"), "INVALID_NUMBER"),
])
def test_artifact_verifier_lineage_faults(artifact_export, change, code):
    from alignment.verify_artifacts import ArtifactValidationError, verify_artifacts
    directory, _ = artifact_export
    runtime = json.loads((directory / "runtime.json").read_bytes())
    change(runtime)
    _test_write_json(directory / "runtime.json", runtime)
    _test_reseal_artifacts(directory)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == code


def test_artifact_verifier_rejects_aseprite_uniform_duration(artifact_export):
    from alignment.verify_artifacts import ArtifactValidationError, verify_artifacts
    directory, _ = artifact_export
    ase = json.loads((directory / "aseprite.json").read_bytes())
    for frame in ase["frames"]:
        frame["duration"] = 100
    _test_write_json(directory / "aseprite.json", ase)
    _test_reseal_artifacts(directory)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "ASEPRITE_MISMATCH"


def test_artifact_verifier_rejects_stale_bundle_copy(artifact_export):
    from alignment.verify_artifacts import ArtifactValidationError, verify_artifacts
    directory, _ = artifact_export
    runtime = json.loads((directory / "runtime.json").read_bytes())
    runtime["coordinateConvention"] = "changed"
    _test_write_json(directory / "runtime.json", runtime)
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "BUNDLE_MISMATCH"


def test_artifact_verifier_cli_missing_files_no_directory_created(tmp_path, capsys):
    from alignment.verify_artifacts import main
    missing = tmp_path / "not-generated"
    assert main([str(missing)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED" and len(result["details"]["missing"]) == 6
    assert not missing.exists()


def test_artifact_verifier_cli_pass_and_malformed_json(artifact_export, capsys):
    from alignment.verify_artifacts import main
    directory, _ = artifact_export
    assert main([str(directory)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    (directory / "runtime.json").write_text('{"bad":', encoding="utf-8")
    assert main([str(directory)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAIL" and result["code"] == "INVALID_ARTIFACT"


def test_artifact_verifier_runtime_duplicates_not_silently_accepted(artifact_export):
    from alignment.verify_artifacts import ArtifactValidationError, verify_artifacts
    directory, _ = artifact_export
    (directory / "runtime.json").write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
    with pytest.raises(ArtifactValidationError) as error:
        verify_artifacts(directory)
    assert error.value.code == "INVALID_JSON"


def test_artifact_verifier_dedup_retains_each_occurrence_anchor(project, tmp_path):
    from alignment.verify_artifacts import verify_artifacts
    p, _, add = project
    bitmap = Image.new("RGBA", (1, 1), (7, 8, 9, 255))
    add(bitmap, "one", {"x": 0, "y": 0}); add(bitmap, "two", {"x": 1, "y": 0})
    p["alignments"]["two"]["authoredOffsetPx"] = {"x": 1, "y": 0}
    p["clips"][0]["occurrences"] = [{"occurrenceId": fid, "frameVersionId": fid, "durationMs": 100, "timingMode": "explicit"} for fid in ("one", "two")]
    directory = tmp_path / "two-anchors"
    bundle(project, directory)
    result = verify_artifacts(directory)
    assert result["occurrencesChecked"] == result["frameSourcesChecked"] == 2
    assert result["renderedFramesChecked"] == 1
