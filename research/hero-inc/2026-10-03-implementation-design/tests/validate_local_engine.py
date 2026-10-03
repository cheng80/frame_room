#!/usr/bin/env python3
"""Research-only reproducible tests. Never invokes generation or mutates the engine.

Run with the installed sprite-gen .venv/bin/python and PYTHONDONTWRITEBYTECODE=1.
An existing output directory is refused. Source images are the downloaded public
assets, not generated fixtures; only montage/overflow/foot-failure inputs are made here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

from PIL import Image, ImageDraw
import numpy as np

ENGINE = Path("/Users/cheng80/.codex/skills/sprite-gen")
ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "artifacts/source-assets"
sys.path.insert(0, str(ENGINE))
from sprite_gen.curate.curation import (apply_pixel_edits, apply_transform,
    load_curation, write_curation_atomic)
from sprite_gen.spec.runio import publish_guard


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(path: Path) -> dict:
    im = Image.open(path).convert("RGBA")
    alpha = np.asarray(im)[:, :, 3]
    ys, xs = np.where(alpha >= 16)
    if not len(xs):
        return {"path": str(path), "size": list(im.size), "empty": True}
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
    band_h = max(4, round((bbox[3] - bbox[1]) * .12))
    foot_ys, foot_xs = np.where((alpha >= 16) & (np.indices(alpha.shape)[0] >= bbox[3] - band_h))
    return {"path": str(path), "size": list(im.size), "bbox_alpha_ge_16": bbox,
        "bbox_size": [bbox[2] - bbox[0], bbox[3] - bbox[1]],
        "bbox_center_x": (bbox[0] + bbox[2] - 1) / 2,
        "foot_band_height": band_h,
        "foot_band_x_range": [int(foot_xs.min()), int(foot_xs.max())],
        "foot_band_mid_x": float((foot_xs.min() + foot_xs.max()) / 2),
        "bottom_exclusive": bbox[3], "bottom_visible_pixel": bbox[3] - 1,
        "opaque_pixels": int((alpha == 255).sum()),
        "nonzero_alpha_pixels": int((alpha > 0).sum()),
        "transparent_pixels": int((alpha == 0).sum()),
        "partial_alpha_pixels": int(((alpha > 0) & (alpha < 255)).sum()),
        "alpha_levels": int(np.unique(alpha).size), "sha256": sha(path)}


def equal_visible(a: Image.Image, b: Image.Image) -> bool:
    aa, bb = np.array(a.convert("RGBA")), np.array(b.convert("RGBA"))
    return bool(aa.shape == bb.shape and np.array_equal(aa[:, :, 3], bb[:, :, 3])
                and np.array_equal(aa[aa[:, :, 3] > 0], bb[bb[:, :, 3] > 0]))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", type=Path, default=ROOT / "artifacts/local-validation-run-v2")
    args = p.parse_args()
    out = args.out_dir.resolve()
    if out.exists():
        raise SystemExit(f"Refusing existing output; choose a fresh --out-dir: {out}")
    out.mkdir(parents=True)
    logs = out / "logs"
    logs.mkdir()
    result = {"scope": "local deterministic CLI/API research; no provider calls; no application implemented",
              "engine": str(ENGINE), "tests": [], "commands": []}

    def check(name: str, condition: bool, evidence: dict | list | str):
        result["tests"].append({"id": name, "pass": bool(condition), "evidence": evidence})

    def cli(label: str, *argv: object, expect: int = 0):
        command = [str(ENGINE / ".venv/bin/sprite-gen"), *map(str, argv)]
        completed = subprocess.run(command, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, cwd=ROOT)
        record = {"label": label, "argv": command, "exit_code": completed.returncode,
                  "stdout": completed.stdout, "stderr": completed.stderr}
        (logs / f"{label}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        result["commands"].append({"label": label, "exit_code": completed.returncode,
                                   "log": str(logs / f"{label}.json")})
        if completed.returncode != expect:
            raise RuntimeError(f"{label}: exit {completed.returncode}, expected {expect}: {completed.stderr}")
        return record

    originals = {str(f): sha(f) for f in SOURCES.iterdir() if f.is_file()}
    source_stats = [stats(f) for f in sorted(SOURCES.iterdir()) if f.suffix in (".webp", ".png")]
    result["source_assets"] = source_stats
    expected = {0: [128, 23, 505, 494], 1: [148, 116, 486, 494], 3: [113, 174, 442, 494]}
    poses = {i: Image.open(SOURCES / f"pose-{i}-aligned.png").convert("RGBA") for i in expected}
    check("real-png-page-bbox-oracle", all(stats(SOURCES / f"pose-{i}-aligned.png")["bbox_alpha_ge_16"] == bb for i, bb in expected.items()), expected)
    check("raw-checkerboard-is-not-alpha", all(stats(SOURCES / f"pose-{i}-raw.png")["transparent_pixels"] == 0 for i in expected), "All three raw images are fully opaque; only aligned assets have actual transparency.")
    check("lossless-decoded-webp-to-png", all(np.array_equal(np.asarray(Image.open(SOURCES / f"pose-{i}-{kind}.webp").convert("RGBA")), np.asarray(Image.open(SOURCES / f"pose-{i}-{kind}.png"))) for i in expected for kind in ("raw", "aligned")), "Container conversion preserves decoded RGBA. This does not recover information from any earlier WebP compression.")

    # A constructed green montage of real published sprites, not a generated source sheet.
    montage = Image.new("RGBA", (1536, 512), (0, 255, 0, 255))
    for col, im in enumerate(poses.values()):
        montage.alpha_composite(im, (col * 512, 0))
    montage.save(out / "real-assets-green-montage.png")
    cli("slice-real", "slice-sheet", "--sheet", out / "real-assets-green-montage.png", "--out-dir", out / "sliced-real", "--chroma-key", "green", "--grid", "3x1", "--names", "standing,horizontal,crouching", "--cell-width", 512, "--cell-height", 512, "--baseline-y", 494, "--target-height", 471)
    sliced = {name: stats(out / "sliced-real" / f"{name}.png") for name in ("standing", "horizontal", "crouching")}
    result["slice_real"] = sliced
    check("slice-normalizes-crouch-observed-risk", sliced["crouching"]["bbox_size"][1] == sliced["standing"]["bbox_size"][1] == 471,
          {"input_height_ratio": 320 / 471, "output_height_ratio": sliced["crouching"]["bbox_size"][1] / sliced["standing"]["bbox_size"][1], "crouch_scale_from_code": 471 / 320, "horizontal_scale_from_code": 471 / 378, "status": "Confirmed incompatibility with animation shared-scale requirement; not a product pass."})

    # New adapter PROTOTYPE: public aligned pixels + stored source foot anchors, s=1.
    # Existing artwork already uses target y=494. The .5px crouch ambiguity is retained.
    shared = out / "shared-scale-prototype"
    shared.mkdir()
    shared_records = []
    for i, im in poses.items():
        st = stats(SOURCES / f"pose-{i}-aligned.png")
        source_anchor = [st["foot_band_mid_x"], st["bottom_exclusive"]]
        # Half-pixel is intentionally left to human review; do not silently resample.
        dx, dy = round(256 - source_anchor[0]), round(494 - source_anchor[1])
        placed = Image.new("RGBA", (512, 512))
        placed.alpha_composite(im, (dx, dy))
        dest = shared / f"pose-{i}.png"
        placed.save(dest)
        shared_records.append({"pose": i, "scale": 1, "source_anchor": source_anchor,
            "target_anchor": [256, 494], "integer_offset": [dx, dy],
            "residual_x": source_anchor[0] + dx - 256, "metrics": stats(dest)})
    result["shared_scale_prototype"] = shared_records
    check("shared-scale-real-ratio-and-feet", all(r["metrics"]["bottom_exclusive"] == 494 for r in shared_records) and shared_records[2]["metrics"]["bbox_size"][1] / shared_records[0]["metrics"]["bbox_size"][1] == 320 / 471,
          "s=1 preserves 320/471 = 0.6794055 and each bottom=494; crouch x residual=0.5px is recorded.")
    check("weapon-not-clipped-in-real-fixture", all(r["metrics"]["nonzero_alpha_pixels"] == stats(SOURCES / f"pose-{r['pose']}-aligned.png")["nonzero_alpha_pixels"] and 2 <= r["metrics"]["bbox_alpha_ge_16"][0] and r["metrics"]["bbox_alpha_ge_16"][2] <= 510 for r in shared_records), "All public visible-alpha pixels retained; rightmost original is x=504 (exclusive505), within 2px margin. Does not prove upstream generated weapon completeness.")

    source_import = out / "import-input"
    for state in ("idle", "oneshot"):
        (source_import / state).mkdir(parents=True)
        for n, i in enumerate(poses):
            shutil.copy2(shared / f"pose-{i}.png", source_import / state / f"{n}-pose-{i}.png")
    (source_import / "_base").mkdir()
    shutil.copy2(SOURCES / "gunner.png", source_import / "_base/gunner.png")
    run = out / "engine-run"
    cli("import-real", "unpack-atlas", "--pngs-dir", source_import, "--out-dir", run)
    request_path = run / "sprite-request.json"
    request = json.loads(request_path.read_text())
    request["states"]["idle"].update(fps=5, loop=True)
    request["states"]["oneshot"].update(fps=10, loop=False, durations_ms=[80, 160, 320])
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    frames_before = {str(p): sha(p) for p in (run / "frames").rglob("*.png")}
    check("import-preserves-real-visible-pixels", all(equal_visible(Image.open(run / f"frames/idle/frame-{n}.png"), im) for n, im in enumerate(poses.values())), "Same-size 512 PNGs import with no scale normalization.")
    check("base-source-byte-preserved", sha(run / "base-source.png") == sha(SOURCES / "gunner.png"), "Importer copies _base byte-for-byte.")
    payload = {"version": 1, "kind": "sprite-gen-curation", "states": {
        "idle": {"selected": [2, 0, 3], "order": [2, 0, 3, 1], "clones": {"3": 1},
                 "transforms": {"3": {"rotate": 0, "scale": 1, "dx": -3, "dy": -2, "flipX": 0}},
                 "pixels": {"0": {"240,300": "#AABBCC"}}},
        "oneshot": {"selected": [1, 0, 3], "order": [1, 0, 3, 2], "clones": {"3": 1}}}}
    with publish_guard(run):
        write_curation_atomic(run, payload)
    loaded = load_curation(run)
    check("curation-save-load-order-clone-transform", loaded["states"]["idle"]["selected"] == [2, 0, 3] and loaded["states"]["idle"]["transforms"]["3"]["dx"] == -3,
          {"run_revision": loaded["run_revision"], "idle": loaded["states"]["idle"]})
    cli("compose-curated", "compose-atlas", "--run-dir", run)
    cli("export-selected-pngs", "export-pngs", "--run-dir", run, "--selected-only")
    cli("export-aseprite", "export-aseprite", "--run-dir", run)
    manifest = json.loads((run / "manifest.json").read_text())
    result["manifest_animation"] = manifest["animation"]
    atlas = Image.open(run / "sprite-sheet-alpha.png").convert("RGBA")
    identity = {"rotate": 0, "scale": 1, "dx": 0, "dy": 0, "flipX": 0}
    expected_frames = [poses[3], apply_pixel_edits(poses[0], {"240,300": "#AABBCC"}), apply_transform(poses[1], {**identity, "dx": -3, "dy": -2}, (512, 512))]
    atlas_checks = []
    export_names = ["idle-2-pose-3.png", "idle-0-pose-0.png", "idle-frame-3.png"]
    for n, rectangle in enumerate(manifest["frame_layout"]["rows"]["idle"]):
        x, y, w, h = (rectangle[k] for k in ("x", "y", "w", "h"))
        atlas_crop = atlas.crop((x, y, x + w, y + h))
        export_im = Image.open(run / "curated" / export_names[n])
        atlas_checks.append({"position": n, "atlas_vs_expected_visible": equal_visible(atlas_crop, expected_frames[n]),
            "export_vs_expected_visible": equal_visible(export_im, expected_frames[n]),
            "atlas_vs_export_visible": equal_visible(atlas_crop, export_im)})
    check("curated-atlas-export-bake-match", all(all(v for k, v in c.items() if k != "position") for c in atlas_checks), atlas_checks)
    check("frames-byte-immutable-after-bake", all(sha(Path(p)) == h for p, h in frames_before.items()), frames_before)
    anim = manifest["animation"]["rows"]
    check("loop-and-uniform-time-saved", anim["idle"]["loop"] is True and anim["oneshot"]["loop"] is False and anim["idle"]["durations_ms"] == [200] * 3 and anim["oneshot"]["durations_ms"] == [100] * 3,
          anim)
    check("custom-per-frame-duration-unsupported-observed", anim["oneshot"]["durations_ms"] != [80, 160, 320], {"requested_field_probe": [80, 160, 320], "actual": anim["oneshot"]["durations_ms"], "status": "Existing composer uses uniform fps, repeats express holds; proposed per-frame time UI needs an explicit contract change."})
    check("repeat-instance-rect-reused", manifest["frame_layout"]["rows"]["oneshot"][0] == manifest["frame_layout"]["rows"]["oneshot"][2], manifest["frame_layout"]["rows"]["oneshot"])
    aseprite = json.loads((run / "exports/aseprite.json").read_text())
    check("aseprite-duration-preserved", [f["duration"] for f in aseprite["frames"]] == [200, 200, 200, 100, 100, 100], "Aseprite JSON preserves duration and order; loop remains only in sprite-gen manifest.")

    # Negative import failure must not replace a previous successful result.
    refs = source_import / "idle/_refs"
    refs.mkdir()
    shutil.copy2(SOURCES / "gunner.png", refs / "invalid-role.png")
    canonical = [p for p in run.rglob("*") if p.is_file() and not p.name.startswith(".sprite-gen")]
    before_failure = {str(p): sha(p) for p in canonical}
    failure = cli("invalid-reimport", "unpack-atlas", "--pngs-dir", source_import, "--out-dir", run, "--force", expect=1)
    check("failed-reimport-preserves-completed-run", all(sha(Path(p)) == h for p, h in before_failure.items()), failure["stderr"])

    # Clearly synthetic connected long-weapon fixture; proves clipping guard absence.
    weapon = Image.new("RGBA", (800, 512), (0, 255, 0, 255))
    draw = ImageDraw.Draw(weapon)
    draw.rectangle((200, 23, 279, 493), fill=(70, 80, 130, 255))
    draw.rectangle((0, 200, 649, 214), fill=(190, 100, 50, 255))
    weapon.save(out / "synthetic-overflow-green.png")
    cli("slice-synthetic-overflow", "slice-sheet", "--sheet", out / "synthetic-overflow-green.png", "--out-dir", out / "sliced-overflow", "--chroma-key", "green", "--grid", "1x1", "--cell-width", 512, "--cell-height", 512, "--baseline-y", 494, "--target-height", 471)
    overflow = stats(out / "sliced-overflow/cell-0.png")
    input_subject_pixels = 80 * 471 + 650 * 15 - 80 * 15
    check("slice-long-weapon-silent-clipping-observed-risk", overflow["bbox_size"][0] == 512 and overflow["nonzero_alpha_pixels"] < input_subject_pixels,
          {"fixture_kind": "synthetic test geometry", "input_subject_width": 650, "output_canvas_width": 512,
           "input_subject_pixels": input_subject_pixels, "output": overflow,
           "status": "CLI returned 0; no overflow rejection. This is a product acceptance failure to prevent in the adapter."})
    # Synthetic cape/gun below feet: the site heuristic confidently chooses the prop.
    badfoot = Image.new("RGBA", (512, 512))
    draw = ImageDraw.Draw(badfoot)
    draw.rectangle((210, 50, 289, 450), fill=(40, 90, 180, 255))
    draw.line((250, 200, 470, 494), fill=(150, 100, 40, 255), width=8)
    badfoot.save(out / "synthetic-prop-below-feet.png")
    foot_stats = stats(out / "synthetic-prop-below-feet.png")
    check("foot-heuristic-can-select-prop-observed-risk", abs(foot_stats["foot_band_mid_x"] - 250) > 25 or foot_stats["bottom_exclusive"] != 451,
          {"fixture_kind": "synthetic known-foot oracle", "manual_foot_anchor": [250, 451], "heuristic": foot_stats,
           "status": "Heuristic result is not a verified anatomical foot; require confidence/unknown/manual correction."})
    check("all-downloaded-sources-byte-immutable", all(sha(Path(p)) == h for p, h in originals.items()), originals)
    result["not_run"] = ["provider authentication or generation", "new web-app flow", "browser preview pixel parity", "SIGKILL/cancel recovery", "actual partial generation", "automatic body-part segmentation", "upstream checkerboard removal quality", "Aseprite/Phaser/Flame runtime loading", "team outline UI/bake"]
    result["summary"] = {"checks": len(result["tests"]), "checks_passed": sum(t["pass"] for t in result["tests"]), "note": "Risk-observation checks pass when the undesired current-engine behavior is demonstrated, not when product acceptance is met."}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))
    return 0 if all(t["pass"] for t in result["tests"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
