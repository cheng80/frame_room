#!/usr/bin/env python3
"""Replay the real frame-room video worker without a server or asset database.

Run with engine/sprite-gen/.venv/bin/python; --out must not already exist.
No generation, installation, project import, approval or custom image algorithm.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

VARIANTS = {"default": ("gif", "off"), "rgba": ("rgba", "off"), "repaired": ("rgba", "on")}
DIFFERENCES = [
    "services.worker.video_task.execute_video의 로컬 처리 및 final-preview 렌더 설정을 재현한다. 작업자 자체는 DB 쓰기가 있어 호출하지 않는다.",
    "API 검증/작업 등록/DB 자산 등록 대신 minimal snapshot과 파일 resolver를 사용한다. ID는 실험 내부 ID이며 실제 프로젝트 ID가 아니다.",
    "프로세스의 SPRITE_DATA_DIR은 출력 폴더다. normalize/finish의 기존 atomic_bytes가 DB 경로 조회 없이 JSON을 저장하며 SQLite 연결 자체는 차단한다.",
    "referencePath에 입력 reference를 직접 전달한다. UI의 spillReferenceAssetId 또는 영상 referenceAssetId 선택에 해당한다.",
    "새 프레임/앵커/동작은 UI와 동일하게 pending이다. render_occurrence QA를 보존하며 승인·export 프로젝트 게이트는 실행하지 않는다.",
    "UI final-preview와 동일하게 include_outline=False, 1배율, 64×128, edge=2, targetAnchor=(32,118)을 사용한다. 기존 프로젝트의 외곽선/수동 편집/타임라인 변경은 없다.",
    "정식 프로젝트 ZIP/atlas/export manifest는 만들지 않는다. 같은 bake PNG를 write_animation_formats에 넘겨 PNG strip/grid·GIF·WebP를 만든다.",
    "default는 legacy Lanczos+gif finish, rgba/repaired는 실제 color-alpha resize+rgba finish다. 따라서 default와 rgba의 차이는 팔레트만의 차이가 아니다.",
    "추출 raw/keyed 캐시는 세 변형이 공유한다. 선택/보정은 각 변형마다 실제 process_clip으로 실행하며 알고리즘·threshold·프레임 순서를 대체하지 않는다.",
    "기존 MP4와 reference를 읽을 뿐 생성 API를 호출하지 않는다. 이 실행의 출처는 supplied-existing-video이며 새 GPT/Grok 생성 결과가 아니다.",
]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    # Only our fresh output tree is writable; every report is published once.
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def protected_manifest():
    """Read bytes directly: never open SQLite, including in read-only mode."""
    data = ROOT / ".data"
    paths = list((data / "projects").rglob("*"))
    paths += list(data.glob("app.sqlite3*"))
    files = {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths) if p.is_file()}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"sha256": digest, "fileCount": len(files), "files": files}


def install_guard(out):
    """Catch accidental DB/network use and Python writes outside the experiment."""
    def check_path(path):
        if isinstance(path, (str, bytes, os.PathLike)):
            resolved = Path(os.fsdecode(path)).resolve()
            if not resolved.is_relative_to(out) and resolved != Path(os.devnull):
                raise PermissionError(f"Write outside output refused: {resolved}")

    def audit(event, args):
        if event == "sqlite3.connect" or event in ("socket.connect", "socket.bind", "socket.getaddrinfo"):
            raise PermissionError(f"Offline DB-free replay refused: {event}")
        if event == "open":
            path, mode, flags = args
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
            ):
                check_path(path)
        elif event in ("os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.utime"):
            check_path(args[0])
        elif event in ("os.rename", "os.link", "os.symlink"):
            check_path(args[0])
            check_path(args[1])
    sys.addaudithook(audit)


def make_snapshot(result, normalization, finish_paths, params):
    from alignment.pipeline import inspect_image

    group = dict(alignmentGroupId="experiment-group", groupRevisionId="experiment-group-v1",
                 frameVersionIds=[], mode="preserve-source-scale", sharedScale=1,
                 cell={"width": params['cellWidth'], "height": params['cellHeight'], "edge": 2},
                 targetAnchor={"x": params['cellWidth']/2, "y": params['cellHeight']-10},
                 bodyMeasurement=None, resampler="nearest", roundingVersion="js-round-v1",
                 measurementProposal={"bodyHeight": result["standingHeight"] * normalization["sourceToFrameTransform"]["scaleY"],
                                      "targetHeight": 94, "source": "video-normalized-first-frame"})
    snapshot = {"assets": [], "frames": [], "alignmentGroups": [group], "alignments": {}, "outline": {"enabled": False}}
    resolver, occurrences = {}, []
    for index, (item, path) in enumerate(zip(result["frames"], finish_paths, strict=True)):
        fid, aid = f"frame-{index:04d}", f"finished-{index:04d}"
        resolver[aid] = str(path)
        snapshot["assets"].append({"assetId": aid, "sha256": sha(path), **inspect_image(path)})
        group["frameVersionIds"].append(fid)
        snapshot["frames"].append(dict(frameId=fid, frameVersionId=fid,
            rawAssetId=f"raw-source-{item['sourceFrameIndex']:04d}", imageAssetId=aid,
            sourceRect=normalization["sourceRect"], sourceToFrameTransform=normalization["sourceToFrameTransform"],
            extractionVersion="video-v3-finished", nativeScaleGroupId=group["alignmentGroupId"],
            review="pending", hidden=False, sourceFrameIndex=item["sourceFrameIndex"],
            sourceTimeMs=item["sourceTimeMs"], interpolated=bool(item.get("interpolated")),
            sourceProcessing=item.get("processing", {"kind": "chroma-key"})))
        snapshot["alignments"][fid] = dict(frameVersionId=fid, groupRevisionId=group["groupRevisionId"],
            sourceAnchor=normalization["anchor"], anchorSpace="crop", method="automatic", contactMode="grounded",
            authoredOffsetPx={"x": 0, "y": 0}, approval="pending")
        occurrences.append(dict(occurrenceId=f"occurrence-{index:04d}", frameVersionId=fid,
            durationMs=item["durationMs"], timingMode="explicit", pixelEdits=[],
            transform=dict(dx=0, dy=0, scaleX=1, scaleY=1, rotationDeg=0, shearX=0, shearY=0, flipX=False, flipY=False)))
    clip = dict(clipId="experiment-clip", clipRevisionId="experiment-clip-v1", name="영상 걷기 · 측면 · 검수 대기",
                stateId="walk", direction=params['direction'], facing=params["facing"], referenceRevisionId=None,
                loop=result["selection"]["loop"], endBehavior="hold-last", review="pending", occurrences=occurrences,
                defaultFps=min(60, max(1, round(len(occurrences) / (sum(o["durationMs"] for o in occurrences) / 1000)))))
    snapshot["clips"] = [clip]
    return snapshot, clip, resolver


def run_variant(name, params, clip_path, out):
    from adapters.spritegen.video_processing import process_clip
    from adapters.spritegen.video_normalization import normalize_frames
    from adapters.spritegen.video_finish import finish_frames
    from alignment.pipeline import render_occurrence
    from alignment.animation_exports import write_animation_formats

    directory = out / name
    directory.mkdir()
    write_json(directory / "settings.json", params)
    stage = "process_clip"
    try:
        def progress(step, message):
            print(f"[{name}/{step}] {message}", flush=True)
        result = process_clip(clip_path, out / "processing", params, on_progress=progress)
        write_json(directory / "processing.json", result)
        scale = params["bodyHeight"] / result["standingHeight"]
        if not .01 <= scale <= 8:
            raise ValueError("VIDEO_SCALE: UI body scale limits exceeded")
        keyed_dir = result["extraction"].get("processedKeyedDir") or result["extraction"].get("keyedDir")
        bounds = sorted(Path(keyed_dir).glob("frame-*.png"))[result["selection"]["startFrame"]:result["selection"]["endFrame"]] if keyed_dir else None
        bounds = result.get("boundsPaths") or bounds
        stage = "normalize_frames"
        normalized, normalization = normalize_frames(result["frames"], result["standingHeight"], 94,
            directory / "normalized", bounds_paths=bounds, source_anchor=result["anchor"],
            resize_mode="legacy" if params["finishMode"] == "gif" else "color-alpha")
        stage = "finish_frames"
        finished, finish = finish_frames(normalized, directory / "finished", mode=params["finishMode"], cell_width=params['cellWidth'], cell_height=params['cellHeight'])
        snapshot, clip, resolver = make_snapshot(result, normalization, finished, params)
        write_json(directory / "snapshot.json", snapshot)
        write_json(directory / "file-resolver.json", resolver)
        stage = "render_occurrence"
        final = directory / "final-preview"
        final.mkdir()
        cells, lineage = [], []
        for index, (occurrence, item) in enumerate(zip(clip["occurrences"], result["frames"], strict=True)):
            image, qa = render_occurrence(snapshot, clip, occurrence, resolver.__getitem__, include_outline=False)
            assert image.size == (params['cellWidth'], params['cellHeight']), image.size
            target = final / f"frame-{index:04d}.png"
            image.save(target)
            cells.append(image)
            paths = {"raw": Path(item["rawPath"]), "originalKeyed": Path(item["originalKeyedPath"]),
                     "processedKeyed": Path(item["keyedPath"]), "normalized": normalized[index],
                     "finished": finished[index], "baked": target}
            lineage.append({"index": index, "source": item, "qa": qa,
                            "files": {key: {"path": str(path), "sha256": sha(path)} for key, path in paths.items()}})
        write_json(directory / "lineage.json", lineage)
        stage = "write_animation_formats"
        preview = write_animation_formats(cells, [o["durationMs"] for o in clip["occurrences"]], clip["loop"], final)
        write_json(final / "preview.json", preview)
        errors = Counter(e["code"] for frame in lineage for e in frame["qa"]["errors"])
        warnings = Counter(e["code"] for frame in lineage for e in frame["qa"]["warnings"])
        missing = [key for key in ("stripPng", "gif", "webp") if preview["formats"][key]["status"] != "created"]
        summary = dict(status="incomplete" if missing else "completed", productionApproved=False,
            frameCount=len(cells), cell=[params['cellWidth'], params['cellHeight']], durationMs=sum(o["durationMs"] for o in clip["occurrences"]),
            selection=result["selection"], normalization=normalization, finish=finish,
            qaErrors=dict(errors), qaWarnings=dict(warnings), missingFormats=missing,
            preview=preview, lineage=str(directory / "lineage.json"), rawDir=result["extraction"]["rawDir"])
        write_json(directory / "result.json", summary)
        print(f"[{name}] {summary['status']}: {len(cells)} frames, QA={dict(errors)}", flush=True)
        return summary
    except (Exception, SystemExit) as exc:
        failure = dict(status="failed", stage=stage, exception=type(exc).__name__, message=str(exc),
                       code=getattr(exc, "code", None), details=getattr(exc, "details", None), traceback=traceback.format_exc())
        write_json(directory / "failure.report.json", failure)
        print(f"[{name}] FAILED {stage}: {exc}", flush=True)
        return failure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="New output directory; existing paths are refused")
    parser.add_argument('--cell-width', type=int, default=64)
    parser.add_argument('--cell-height', type=int, default=128)
    parser.add_argument('--direction', choices=['side', 'front', 'back', 'front_diagonal', 'back_diagonal'], default='side')
    args = parser.parse_args()
    clip, reference, out = (p.expanduser().resolve() for p in (args.clip, args.reference, args.out))
    if not clip.is_file() or not reference.is_file():
        parser.error("--clip and --reference must be existing local files")
    if out.is_relative_to(ROOT / ".data" / "projects"):
        parser.error("--out must not be inside the default project folder")
    if out.exists():
        parser.error("--out already exists; choose a fresh path to preserve all prior results")
    before = protected_manifest()
    sources = {"kind": "supplied-existing-video", "clip": {"path": str(clip), "sha256": sha(clip)},
               "reference": {"path": str(reference), "sha256": sha(reference)}}
    out.mkdir(parents=True)
    os.environ["SPRITE_DATA_DIR"] = str(out)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    (out / "tmp").mkdir()
    tempfile.tempdir = str(out / "tmp")
    os.environ["TMPDIR"] = tempfile.tempdir
    install_guard(out)
    write_json(out / "protected-before.json", before)
    write_json(out / "sources.json", sources)
    differences = [s.replace('64×128', f'{args.cell_width}×{args.cell_height}').replace('(32,118)', f'({args.cell_width/2:g},{args.cell_height-10})') for s in DIFFERENCES]
    write_json(out / "ui-differences.json", differences)
    from adapters.spritegen.video_processing import rife_capability
    settings = dict(state="walk", direction=args.direction, facing="right", key="magenta", bodyHeight=94,
                    cellWidth=args.cell_width, cellHeight=args.cell_height, maxFrames=32, loopMode="auto", referencePath=str(reference))
    code_paths = [ROOT / path for path in (
        "scripts/skill_compare/frame_room.py", "services/worker/video_task.py", "adapters/spritegen/video_processing.py",
        "adapters/spritegen/video_normalization.py", "adapters/spritegen/video_finish.py",
        "alignment/pipeline.py", "alignment/animation_exports.py")]
    code_paths += sorted((ROOT / "engine/sprite-gen/sprite_gen").rglob("*.py"))
    code_hashes = {str(p.relative_to(ROOT)): sha(p) for p in code_paths}
    write_json(out / "settings.json", {"base": settings, "variants": VARIANTS, "python": sys.executable,
               "pythonVersion": sys.version, "rife": rife_capability(), "codeHashes": code_hashes})
    results = {}
    for name, (finish, repair) in VARIANTS.items():
        results[name] = run_variant(name, {**settings, "finishMode": finish, "repairMode": repair}, clip, out)
    after = protected_manifest()
    write_json(out / "protected-after.json", after)
    changed = [p for p in before["files"].keys() | after["files"].keys() if before["files"].get(p) != after["files"].get(p)]
    preservation = dict(defaultProjectsAndAppDbUnchanged=not changed, changedPaths=sorted(changed),
        beforeSha256=before["sha256"], afterSha256=after["sha256"], protectedFileCount=before["fileCount"],
        clipUnchanged=sha(clip) == sources["clip"]["sha256"], referenceUnchanged=sha(reference) == sources["reference"]["sha256"],
        codeUnchanged=all(sha(ROOT / p) == digest for p, digest in code_hashes.items()),
        databaseCreated=any(out.rglob("*.sqlite3")))
    raw_dirs = [r["rawDir"] for r in results.values() if "rawDir" in r]
    success = all(r["status"] == "completed" for r in results.values()) and not changed
    success = success and preservation["clipUnchanged"] and preservation["referenceUnchanged"] and preservation["codeUnchanged"] and not preservation["databaseCreated"]
    report = dict(status="completed" if success else "incomplete", productionApproved=False,
                  sources=sources, settings=settings, uiDifferences=differences, preservation=preservation,
                  sharedRawExtraction=len(raw_dirs) == 3 and len(set(raw_dirs)) == 1, variants=results)
    write_json(out / "report.json", report)
    print(json.dumps({"status": report["status"], "report": str(out / "report.json"), "preservation": preservation}, ensure_ascii=False), flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
