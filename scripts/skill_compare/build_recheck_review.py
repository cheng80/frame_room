#!/usr/bin/env python3
"""Package recorded gunner comparison assets into one offline HTML file.

Usage (after the recorded assets exist):
    engine/sprite-gen/.venv/bin/python -B scripts/skill_compare/build_recheck_review.py ROOT

ROOT defaults to .data/experiments/skill-ab-gunner-20261006 in this repository.
Requires Pillow. Reads existing media/JSON only; never runs an engine, ffmpeg,
generation, browser, server, or network request. Writes only the chosen HTML
(default ROOT/review.html); refuses to overwrite an existing file.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
from pathlib import Path
import re


DEFAULT_ROOT = Path(__file__).resolve().parents[2] / ".data/experiments/skill-ab-gunner-20261006"
PROVENANCE = "기존 GPT 하늘 해적 기준 그림 재사용 · Grok 3초 1회"


def read_json(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 객체가 필요합니다: {path}")
    return value


def number(value, label, minimum=0, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"숫자가 필요합니다: {label} = {value!r}")
    if not math.isfinite(value) or value < minimum or (integer and value != int(value)):
        raise ValueError(f"잘못된 수치: {label} = {value!r}")
    return int(value) if integer else float(value)


def data_url(data, mime="image/png"):
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def source_time(source, index):
    """Prefer recorded presentation timestamps; never assume a 24 fps source."""
    times = source.get("timesMs", [])
    if index < len(times):
        return number(times[index], f"source.timesMs[{index}]")
    if source.get("constantFrameRate") is True and source.get("fps"):
        fps = number(source["fps"], "source.fps", minimum=0.000001)
        return index * 1000 / fps
    return None


def frame_sort_key(path):
    match = re.fullmatch(r"frame-(\d+)\.png", path.name)
    if not match:
        raise ValueError(f"프레임 번호가 필요합니다: {path}")
    return int(match.group(1))


def app_variant(root, key, label, cell, report, Image):
    directory = root / "frame-room" / key
    proc = read_json(directory / "processing.json")
    frames = proc["frames"]
    paths = sorted((directory / "final-preview").glob("frame-*.png"), key=frame_sort_key)
    if not frames or len(frames) != len(paths):
        raise ValueError(f"앱 메타데이터/PNG 수 불일치: {directory}")
    # Final-preview filenames identify output order, never source-video indices.
    if [frame_sort_key(p) for p in paths] != list(range(len(frames))):
        raise ValueError(f"final-preview 프레임 번호는 0부터 연속이어야 합니다: {directory}")
    selection, source = proc["selection"], proc["source"]
    start = number(selection["startFrame"], f"{key}.startFrame", integer=True)
    end = number(selection["endFrame"], f"{key}.endFrame", minimum=start + 1, integer=True)
    images, durations, indices, times = [], [], [], []
    repaired = set(selection.get("repair", {}).get("sourceFrameIndices", []))
    for i, (frame, path) in enumerate(zip(frames, paths)):
        if frame.get("outputFrameIndex", i) != i:
            raise ValueError(f"앱 출력 순서가 PNG 순서와 다릅니다: {path}")
        with Image.open(path) as image:
            if image.format != "PNG" or image.size != cell:
                raise ValueError(f"앱 PNG 셀 크기 불일치: {path}: {image.size}, 설정 {cell}")
            image.verify()
        images.append(data_url(path.read_bytes()))
        durations.append(number(frame["durationMs"], f"{path.name}.durationMs", minimum=0.000001))
        index = frame.get("sourceFrameIndex")
        processing = frame.get("processing") or {}
        interpolated = (frame.get("interpolated") or frame.get("interpolation")
                        or processing.get("interpolation") or index in repaired
                        or "rife" in str(processing.get("kind", "")).lower())
        if interpolated or index is None:
            indices.append(None)
            times.append(None)
        else:
            index = number(index, f"{path.name}.sourceFrameIndex", integer=True)
            if not start <= index < end:
                raise ValueError(f"앱 계보가 선택 구간을 벗어납니다: {path}")
            indices.append(index)
            timestamp = frame.get("sourceTimeMs")
            times.append(number(timestamp, f"{path.name}.sourceTimeMs")
                         if timestamp is not None else source_time(source, index))
    source_duration = selection.get("sourceDurationMs")
    if source_duration is None:
        first, last = source_time(source, start), source_time(source, end)
        source_duration = last - first if first is not None and last is not None else None
    if source_duration is not None:
        source_duration = number(source_duration, f"{key}.sourceDurationMs", minimum=0.000001)
    variant = dict(id="current-" + key, label=label, images=images,
                   durationsMs=durations, durationMs=sum(durations), sourceDurationMs=source_duration,
                   sourceIndices=indices, sourceTimesMs=times, start=start, end=end,
                   notes="앱 final-preview PNG 원본 · 보간 프레임은 원본 이동 없음",
                   evidence={"selection": selection, "result": report.get("variants", {}).get(key)})
    return variant, source, proc.get("sourceSha256")


def strip_variant(directory, identifier, label, cell, Image, source, fixed=False, shared=False):
    meta = read_json(directory / "walk.strip.json")
    evidence_name = "resample.json" if shared else "walk.loop.report.json"
    evidence = read_json(directory / evidence_name)
    width = number(meta["w"], f"{directory}.w", minimum=1, integer=True)
    height = number(meta["h"], f"{directory}.h", minimum=1, integer=True)
    count = number(meta["frames"], f"{directory}.frames", minimum=1, integer=True)
    # The app worker places feet at (cellWidth / 2, cellHeight - 10).
    # Keep upstream pixels byte-for-byte in RGBA: paste without a mask or resize.
    x, y = (cell[0] - width) // 2, cell[1] - 10 - height
    if x < 0 or y < 0 or x + width > cell[0] or y + height > cell[1]:
        raise ValueError(f"투명 패딩 범위 초과: {directory}, strip 셀 {width}×{height}, "
                         f"앱 셀 {cell[0]}×{cell[1]}, 발 기준 y={cell[1] - 10}; 축소·자르기 금지")
    images = []
    with Image.open(directory / "walk.strip.png") as original:
        if original.format != "PNG" or original.size != (width * count, height):
            raise ValueError(f"strip PNG 크기/메타데이터 불일치: {directory}")
        strip = original.convert("RGBA")
        for i in range(count):
            crop = strip.crop((i * width, 0, (i + 1) * width, height))
            padded = Image.new("RGBA", cell, (0, 0, 0, 0))
            padded.paste(crop, (x, y))
            buffer = io.BytesIO()
            padded.save(buffer, format="PNG")
            images.append(data_url(buffer.getvalue()))
    # Includes shared RIFE: retain source cycle duration, never count / source fps.
    duration = number(meta["cycle_seconds"], f"{directory}.cycle_seconds", minimum=0.000001) * 1000
    indices, times = [], []
    start = end = None
    if not shared:
        cycle = evidence["cycle"]
        start = number(cycle["start"], f"{directory}.cycle.start", integer=True)
        length = number(cycle["length"], f"{directory}.cycle.length", minimum=1, integer=True)
        end = start + length
        if fixed:
            repair = evidence.get("jump_repair") or {}
            if (count != length or meta.get("subsampled") or repair.get("applied")
                    or repair.get("replaced") or evidence.get("cycle_mode", "fixed") != "fixed"
                    or evidence.get("resample") or meta.get("resample")):
                raise ValueError(f"latest-fixed는 보간·보정·샘플 생략 없는 원본 순서여야 합니다: {directory}")
            indices = [start + i for i in range(count)]
            times = [source_time(source, index) for index in indices]
    notes = f"실제 strip PNG · 투명 패딩만 적용 ({x}, {y}) · 확대·축소 없음"
    if shared:
        notes += " · source duration은 메타 cycle_seconds · 원본 계보 없음"
    elif not fixed:
        notes += " · 자동 처리의 개별 원본 계보 없음"
    return dict(id=identifier, label=label, images=images, durationsMs=[duration / count] * count,
                durationMs=duration, sourceDurationMs=duration, sourceIndices=indices, sourceTimesMs=times,
                start=start, end=end, notes=notes, evidence={"strip": meta, evidence_name: evidence})


def common_finish_variant(directory, identifier, label, parent, cell, Image):
    """Embed already-finished experiment PNGs with transparent padding only."""
    provenance = read_json(directory / "provenance.json")
    paths = sorted((directory / "finished").glob("frame-*.png"), key=frame_sort_key)
    count = len(parent["images"])
    if provenance.get("frames") != count or [frame_sort_key(p) for p in paths] != list(range(count)):
        raise ValueError(f"공통 마무리 프레임 수/순서 불일치: {directory}")
    finish = provenance.get("finish", {})
    normalization = provenance.get("normalization", {})
    if (provenance.get("kind") != "isolated-experiment-combination"
            or finish.get("mode") != "gif" or normalization.get("resampler") != "lanczos"
            or (finish.get("cellWidth"), finish.get("cellHeight")) != cell
            or finish.get("footMargin") != 10):
        raise ValueError(f"현재 legacy 축소 + 공통 GIF 마무리 기록을 확인하세요: {directory}")
    images, offsets = [], []
    for path in paths:
        with Image.open(path) as original:
            if original.format != "PNG":
                raise ValueError(f"공통 마무리는 PNG여야 합니다: {path}")
            width, height = original.size
            if (width, height) != (normalization.get("width"), normalization.get("height")):
                raise ValueError(f"공통 마무리 PNG/정규화 크기 불일치: {path}")
            # Match app final-preview placement (js-round-v1); only add padding.
            anchor = normalization["anchor"]
            x = math.floor(cell[0] / 2 - number(anchor["x"], f"{path}.anchor.x") + 0.5)
            y = math.floor(cell[1] - 10 - number(anchor["y"], f"{path}.anchor.y") + 0.5)
            if x < 0 or y < 0 or x + width > cell[0] or y + height > cell[1]:
                raise ValueError(f"공통 마무리 투명 패딩 범위 초과: {path}; 축소·자르기 금지")
            padded = Image.new("RGBA", cell, (0, 0, 0, 0))
            padded.paste(original.convert("RGBA"), (x, y))
            buffer = io.BytesIO()
            padded.save(buffer, format="PNG")
            images.append(data_url(buffer.getvalue()))
            offsets.append([x, y])
    # Inherit the recorded source cycle: fixed start+i, RIFE no source mapping.
    # No timing or lineage is taken from the separate upstream/alignment.json.
    return {**parent, "id": identifier, "label": label, "images": images,
            "notes": "실험 조합 · 제품 통합 결과 아님 · 현재 legacy 축소 + GIF 마무리 적용 PNG"
                     " · 기록된 앵커로 투명 패딩만 추가 (내용 확대·축소 없음)",
            "evidence": {"provenance": provenance, "parentId": parent["id"],
                         "parent": parent["evidence"], "paddingOffsets": offsets}}


def build_data(root):
    from PIL import Image

    report = read_json(root / "frame-room/report.json")
    settings = report["settings"]
    cell = (number(settings["cellWidth"], "settings.cellWidth", minimum=1, integer=True),
            number(settings["cellHeight"], "settings.cellHeight", minimum=11, integer=True))
    video_bytes = (root / "video/original.mp4").read_bytes()
    base_bytes = (root / "video/input-canvas.png").read_bytes()
    if not video_bytes:
        raise ValueError("video/original.mp4가 비어 있습니다")
    with Image.open(io.BytesIO(base_bytes)) as image:
        if image.format != "PNG":
            raise ValueError("video/input-canvas.png는 PNG여야 합니다")
        image.verify()
    video_hash = hashlib.sha256(video_bytes).hexdigest()
    variants, sources = [], []
    for key, label in (("default", "현재 · 기본 GIF 마무리"), ("rgba", "현재 · RGBA"),
                       ("repaired", "현재 · RGBA + 보정")):
        variant, source, recorded_hash = app_variant(root, key, label, cell, report, Image)
        if recorded_hash and recorded_hash != video_hash:
            raise ValueError(f"앱 {key} 처리 영상과 video/original.mp4의 SHA-256이 다릅니다")
        variants.append(variant)
        sources.append(source)
    if any(source != sources[0] for source in sources[1:]):
        raise ValueError("앱 변형들의 원본 영상 시각 메타데이터가 다릅니다")
    for key, label in (("auto", "최신 · 자동 선택 + 보정"), ("no-repair", "최신 · 자동 선택 · 보정 끄기"),
                       ("fixed", "최신 · 같은 고정 구간 · RGBA")):
        variants.append(strip_variant(root / "upstream" / key, "latest-" + key, label,
                                      cell, Image, sources[0], fixed=key == "fixed"))
    by_id = {variant["id"]: variant for variant in variants}
    fair_ids = ["current-default", "current-rgba", "latest-fixed"]
    if len({(by_id[key]["start"], by_id[key]["end"]) for key in fair_ids}) != 1:
        raise ValueError("동일 구간 비교 불가: default / rgba / latest-fixed의 선택 구간이 다릅니다")
    modes = [dict(id="fair", label="동일 구간", ids=fair_ids,
                  note="기본 마무리 / RGBA / 최신 고정 구간. 같은 선택 구간이며 처리 방식 차이가 포함됩니다."),
             dict(id="auto", label="자동 비교", ids=["current-default", "current-repaired", "latest-auto"],
                  note="각 경로의 자동 선택 결과입니다. 구간·보정·정렬 차이가 함께 포함됩니다. 카드에서 보정 끄기도 선택할 수 있습니다.")]
    shared_dirs = [root / "shared-rife" / key for key in ("frame-room", "upstream")]
    missing = [f"{d.name}/{name}" for d in shared_dirs
               for name in ("walk.strip.png", "walk.strip.json", "resample.json") if not (d / name).is_file()]
    optional_note = "동일 입력 RIFE: 선택 자료가 없어 표시하지 않습니다."
    if not missing:
        records = [read_json(d / "resample.json") for d in shared_dirs]
        hashes = records[0].get("inputSha256")
        if not isinstance(hashes, list) or not hashes or hashes != records[1].get("inputSha256"):
            raise ValueError("shared-rife의 순서별 inputSha256이 없거나 다릅니다: 동일 입력으로 표시할 수 없습니다")
        rife_variants = [strip_variant(d, "rife-" + d.name, "동일 입력 RIFE · " + label + " · RGBA",
                                       cell, Image, sources[0], shared=True)
                         for d, label in zip(shared_dirs, ("현재", "최신"))]
        if abs(rife_variants[0]["durationMs"] - rife_variants[1]["durationMs"]) > 0.11:
            raise ValueError("shared-rife 양쪽의 source cycle_seconds가 다릅니다")
        variants.extend(rife_variants)
        phase_note = ("위상 회전 없음" if all(r.get("phaseRotated") is False for r in records)
                      else "위상 회전 여부는 기록 확인 필요")
        modes.append(dict(id="rife", label="RIFE 동일 입력", ids=[v["id"] for v in rife_variants],
                          note=f"순서별 입력 SHA-256 일치 · {len(hashes)}장 입력 · {phase_note}. "
                               "양쪽 길이는 strip 메타 cycle_seconds를 사용합니다. 보간 결과의 원본 이동은 제공하지 않습니다."))
        optional_note = "동일 입력 RIFE: 저장된 두 경로의 결과를 표시합니다."
    elif any(d.exists() for d in shared_dirs):
        optional_note = "동일 입력 RIFE: 자료가 덜 준비되어 표시하지 않습니다 (" + ", ".join(missing) + ")."
    by_id = {variant["id"]: variant for variant in variants}
    for key, parent_id, label in (
        ("latest-fixed", "latest-fixed", "최신 + 현재 영역·마무리 · 공통 GIF · 실험"),
        ("rife-current", "rife-frame-room", "RIFE 현재 · 공통 GIF · 실험"),
        ("rife-latest", "rife-upstream", "RIFE 최신 · 공통 GIF · 실험"),
    ):
        directory = root / "analysis/common-finish" / key
        if not directory.exists():
            continue
        if parent_id not in by_id:
            optional_note += f" 공통 마무리 {key}: 기반 RIFE 자료가 없어 표시하지 않습니다."
            continue
        variant = common_finish_variant(directory, "common-" + key, label, by_id[parent_id], cell, Image)
        if key == "latest-fixed":
            normalization = variant["evidence"]["provenance"]["normalization"]
            current = report["variants"]["default"]["normalization"]
            if any(normalization.get(field) != current.get(field)
                   for field in ("sourceRect", "sourceToFrameTransform", "anchor")):
                raise ValueError("최신 + 현재 영역·마무리: 현재 앱과 영역·변환·앵커가 다릅니다")
            variant["notes"] += " · 현재 앱의 영역·변환·앵커 공유"
        variants.append(variant)
        by_id[variant["id"]] = variant
    if "common-latest-fixed" in by_id:
        modes.insert(1, dict(id="common-finish", label="같은 마무리",
                             ids=["current-default", "common-latest-fixed", "latest-fixed"],
                             note="현재 기본 GIF / 최신 + 현재 영역·마무리 / 최신 고정 구간 RGBA. "
                                  "가운데는 현재 앱의 영역·변환·앵커와 legacy 축소·GIF 마무리를 적용한 실험 조합이며 "
                                  "제품 통합 결과가 아닙니다. 오른쪽 RGBA는 최신 기본 영역·배치를 유지합니다."))
    common_rife = ["common-rife-current", "common-rife-latest"]
    if all(key in by_id for key in common_rife):
        rife_mode = next(mode for mode in modes if mode["id"] == "rife")
        rife_mode["ids"] = common_rife
        rife_mode["note"] += (" 기본 표시는 양쪽에 현재 legacy 축소 + GIF 마무리를 적용한 실험 조합입니다"
                              " (제품 통합 결과 아님). 기존 RGBA는 카드에서 선택할 수 있습니다.")
    alignment = None
    alignment_path = root / "upstream/alignment.json"
    if alignment_path.is_file():
        record = read_json(alignment_path)
        frames = number(record["length"], "alignment.length", minimum=1, integer=True)
        duration = number(record["cycle_seconds"], "alignment.cycle_seconds", minimum=0.000001) * 1000
        alignment = dict(note=f"별도 정합 진단: {frames}장 · 약 {duration:.0f}ms. "
                              f"이 비교의 원본 구간 {by_id['latest-fixed']['durationMs']:.0f}ms와 별개이며 "
                              "재생 시간·원본 계보에 반영하지 않습니다.", report=record)
    for variant in variants:
        bounds = [0.0]
        for duration in variant["durationsMs"]:
            bounds.append(bounds[-1] + duration)
        variant["boundaries"] = [value / bounds[-1] for value in bounds]
    contact = root / "analysis/contact.png"
    diagnostic = None
    if contact.is_file():
        with Image.open(contact) as image:
            if image.format != "PNG":
                raise ValueError("analysis/contact.png는 PNG여야 합니다")
            image.verify()
        diagnostic = data_url(contact.read_bytes())
    return dict(provenance=PROVENANCE, cellWidth=cell[0], cellHeight=cell[1], variants=variants,
                modes=modes, optionalNote=optional_note, video=data_url(video_bytes, "video/mp4"),
                base=data_url(base_bytes), videoHash=video_hash, baseHash=hashlib.sha256(base_bytes).hexdigest(),
                diagnostic=diagnostic, alignment=alignment, source=sources[0], report=report)


HTML = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; media-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>두 번째 실제 영상 비교</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#11161d;color:#e9eef5;font:15px/1.6 system-ui,sans-serif}
main{max-width:1380px;margin:auto;padding:24px}h1{font-size:26px;margin:0 0 8px}h2{font-size:19px}
p{margin:8px 0;color:#bbc8d8}button,select{font:inherit;color:inherit;background:#263444;border:1px solid #607087;border-radius:6px;padding:7px 10px}
button{cursor:pointer}button:disabled{opacity:.5;cursor:default}button[aria-pressed=true]{background:#36577b;border-color:#a2d0ff}
:focus-visible{outline:3px solid #aed6ff;outline-offset:3px}.bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:18px 0}
.bar input{flex:1;min-width:160px}.note{border-left:3px solid #a2c5ec;padding:10px 14px;background:#1c2836}
.cards{display:grid;grid-template-columns:repeat(var(--columns,3),minmax(0,1fr));gap:16px}
.card{min-width:0;background:#1b2531;border:1px solid #43546a;border-radius:10px;overflow:hidden}
.card select{width:calc(100% - 20px);margin:10px}.stage{display:flex;justify-content:center;align-items:center;padding:16px;overflow:auto;background:var(--background,#d8dce3)}
canvas,img{image-rendering:pixelated}canvas{flex-shrink:0}.caption{padding:12px;white-space:pre-line;font-size:13px}.card button{margin:0 12px 12px}
.raw{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:24px}.raw video{width:100%;max-height:440px;background:#202a36}
.base-wrap{overflow:auto}.base-wrap img{max-width:100%;max-height:400px;object-fit:contain}.small{font-size:12px;overflow-wrap:anywhere}
details{margin:20px 0}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#1b2531;padding:14px;max-height:400px;overflow:auto}
.diagnostic{overflow:auto}.diagnostic img{display:block;max-width:none}#error{color:#ffd0c8}#status{font-variant-numeric:tabular-nums;min-width:75px}
@media(max-width:900px){.cards,.raw{grid-template-columns:1fr}main{padding:16px}}
</style></head><body><main>
<h1>두 번째 실제 영상 비교</h1><p id="provenance"></p>
<p>실제 처리 PNG·원본 MP4·기준 그림을 내장한 오프라인 자료입니다. 아래 결과로 품질 우열을 자동 판정하지 않습니다.</p>
<div class="bar" id="modes" aria-label="비교 모드"></div><p id="condition" class="note"></p>
<p id="timing"></p><p id="optional" class="small"></p>
<div class="bar"><button id="play" disabled>재생</button><button id="prev" disabled>이전 프레임</button><button id="next" disabled>다음 프레임</button>
<input id="scrub" type="range" min="0" max="10000" value="0" disabled aria-label="같은 주기 진행률"><span id="status">0.0%</span>
<label>속도 <select id="speed"><option value="0.25">0.25배</option><option value="0.5">0.5배</option><option value="1" selected>1배</option><option value="2">2배</option></select></label>
<label>확대 <select id="zoom"><option value="1">1배</option><option value="2">2배</option><option value="3" selected>3배</option><option value="4">4배</option></select></label>
<label>배경 <select id="bg"><option value="#d8dce3">회색</option><option value="#ffffff">흰색</option><option value="#101010">검정</option></select></label></div>
<p class="small">모든 카드는 같은 주기 진행률로 재생합니다. 1배 속도의 기준은 왼쪽 결과 길이이며, 다른 카드의 원래 재생 속도와 다를 수 있습니다. 한 프레임 이동도 왼쪽 기준입니다. 같은 진행률은 같은 원본 시각이나 같은 자세를 뜻하지 않습니다.</p>
<p id="error" role="alert"></p><div class="cards" id="cards"></div>
<div class="raw"><section><h2>Grok 원본 MP4</h2><video id="video" controls muted playsinline preload="metadata"></video>
<p class="small">원본 영상은 독립 재생입니다. 각 카드의 원본 이동은 기록된 시각으로 일시정지 이동하며, MP4 디코더의 프레임 표시를 보증하지 않습니다. 번호는 0부터 시작합니다.</p><p id="seek-status" role="status"></p><p id="video-hash" class="small"></p></section>
<section><h2>재사용한 기준 그림</h2><div class="base-wrap"><img id="base" alt="기존 GPT 하늘 해적 기준 그림을 사용한 video/input-canvas.png"></div><p id="base-hash" class="small"></p></section></div>
<details id="diagnostic" hidden><summary>추가 진단 비교 PNG 보기</summary><p>analysis/contact.png · 별도 분석 이미지이며 생성 원본이 아닙니다.</p><div class="diagnostic"><img id="contact" alt="추가 진단 비교 PNG"></div></details>
<details id="alignment" hidden><summary>별도 정합 진단 보기</summary><p id="alignment-note"></p><pre id="alignment-evidence"></pre></details>
<details><summary>처리 기록과 해석 범위</summary><p>현재 결과는 앱 final-preview 원본입니다. 최신·RIFE RGBA 결과는 저장된 strip을 셀 단위로 분리한 뒤 투명 여백만 추가했습니다. 공통 GIF는 현재 legacy 축소 + GIF 마무리를 미리 적용한 실험 조합이며 제품 통합 결과가 아닙니다. 이 뷰어는 저장된 공통 마무리 PNG에도 투명 패딩만 추가합니다. 기존 엔진의 축소·색상·보정·배치 차이는 남아 있습니다. 보간 또는 계보가 없는 결과에는 원본 프레임을 추정해 연결하지 않습니다. 기록의 status는 처리 상태이며 시각 품질 승인이 아닙니다.</p><pre id="evidence"></pre></details>
<noscript>이 비교 뷰어는 JavaScript를 켜야 재생할 수 있습니다.</noscript>
</main><script id="review-data" type="application/json">__DATA__</script><script>
'use strict';
const DATA = JSON.parse(document.getElementById('review-data').textContent);
const $ = id => document.getElementById(id);
const variants = new Map(DATA.variants.map(v => [v.id, v]));
const cache = new Map();
let selected = [], loaded = [], cards = [], phase = 0, playing = false, last = null, revision = 0;
let activeMode = null;
window.reviewReady = false;
function pause() { playing = false; last = null; $('play').textContent = '재생'; }
function controls(enabled) { for (const id of ['play','prev','next','scrub']) $(id).disabled = !enabled; }
function frameAt(v) {
  let index = 0;
  while (index + 1 < v.images.length && phase + 1e-12 >= v.boundaries[index + 1]) index++;
  return index;
}
function loadImages(v) {
  if (!cache.has(v.id)) cache.set(v.id, Promise.all(v.images.map(src => new Promise((resolve, reject) => {
    const im = new Image();
    im.onload = () => resolve(im);
    im.onerror = () => reject(new Error(v.label + ': 내장 PNG를 읽을 수 없습니다.'));
    im.src = src;
  }))));
  return cache.get(v.id);
}
function zoom() {
  const scale = Number($('zoom').value);
  for (const card of cards) {
    card.canvas.style.width = DATA.cellWidth * scale + 'px';
    card.canvas.style.height = DATA.cellHeight * scale + 'px';
  }
}
function ms(value) { return value == null ? '기록 없음' : value.toLocaleString('ko-KR', {maximumFractionDigits: 3}) + 'ms'; }
function render() {
  if (!window.reviewReady) return;
  selected.forEach((v, i) => {
    const index = frameAt(v), card = cards[i], ctx = card.canvas.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, DATA.cellWidth, DATA.cellHeight);
    ctx.drawImage(loaded[i][index], 0, 0);
    const sourceIndex = v.sourceIndices[index], sourceTime = v.sourceTimesMs[index];
    const known = Number.isInteger(sourceIndex) && Number.isFinite(sourceTime);
    const lineage = Number.isInteger(sourceIndex) ? `원본 #${sourceIndex}` : '원본 대응 없음 (보간 또는 계보 없음)';
    const range = v.start == null ? '선택 구간: 원본 계보 없음' : `선택 구간: #${v.start}–#${v.end - 1}`;
    card.caption.textContent = `${v.label}\n${index + 1} / ${v.images.length}장 · 셀 ${DATA.cellWidth}×${DATA.cellHeight}\n결과 길이 ${ms(v.durationMs)} · 원본 구간 길이 ${ms(v.sourceDurationMs)}\n${range}\n${lineage}${known ? ' · ' + ms(sourceTime) : ''}\n${v.notes}`;
    card.seek.disabled = !known;
    card.seek.textContent = known ? `원본 #${sourceIndex} 보기` : '원본 이동 없음';
  });
  $('scrub').value = Math.round(phase * 10000);
  $('status').textContent = (phase * 100).toFixed(1) + '%';
  window.reviewState = {mode: activeMode, phase, selected: selected.map(v => v.id), frames: selected.map(frameAt)};
}
function seek(i) {
  const v = selected[i], index = frameAt(v), time = v.sourceTimesMs[index];
  if (!Number.isInteger(v.sourceIndices[index]) || !Number.isFinite(time)) return;
  pause();
  const video = $('video');
  video.pause();
  const seconds = time / 1000;
  if (video.readyState < 1) { $('seek-status').textContent = '원본 MP4 메타데이터를 읽은 뒤 다시 이동해 주세요.'; return; }
  if (!Number.isFinite(video.duration) || seconds < 0 || seconds >= video.duration) {
    $('seek-status').textContent = '기록된 시각이 원본 영상 범위를 벗어납니다. 이동하지 않았습니다.'; return;
  }
  video.currentTime = seconds;
  $('seek-status').textContent = `${v.label} · 원본 #${v.sourceIndices[index]} · ${ms(time)}`;
}
async function setup(ids, mode) {
  const ticket = ++revision;
  pause(); controls(false); window.reviewReady = false;
  phase = 0; loaded = []; selected = ids.map(id => variants.get(id)); activeMode = mode ? mode.id : 'custom';
  $('error').textContent = '';
  $('condition').textContent = mode ? mode.note : '직접 선택한 결과 비교 · 선택 구간과 원래 길이를 카드에서 확인하세요.';
  $('timing').textContent = `1배 재생 기준: 왼쪽 ${ms(selected[0].durationMs)}. 원래 결과 길이: ` + selected.map(v => `${v.label} ${ms(v.durationMs)}`).join(' / ');
  $('evidence').textContent = JSON.stringify({settings: {cellWidth: DATA.cellWidth, cellHeight: DATA.cellHeight}, source: DATA.source, report: DATA.report, selected: selected.map(v => ({id: v.id, sourceIndices: v.sourceIndices, sourceTimesMs: v.sourceTimesMs, evidence: v.evidence}))}, null, 2);
  for (const button of $('modes').children) button.setAttribute('aria-pressed', String(button.dataset.mode === activeMode));
  $('cards').replaceChildren(); $('cards').style.setProperty('--columns', selected.length);
  cards = selected.map((v, i) => {
    const article = document.createElement('article'); article.className = 'card';
    const select = document.createElement('select'); select.setAttribute('aria-label', `${i + 1}번째 비교 결과`);
    for (const option of DATA.variants) select.add(new Option(option.label, option.id, false, option.id === v.id));
    select.onchange = () => { const next = selected.map(item => item.id); next[i] = select.value; setup(next, null); };
    const stage = document.createElement('div'); stage.className = 'stage';
    const canvas = document.createElement('canvas'); canvas.width = DATA.cellWidth; canvas.height = DATA.cellHeight;
    canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', v.label + ' 처리 PNG'); stage.append(canvas);
    const caption = document.createElement('div'); caption.className = 'caption'; caption.textContent = '내장 PNG 읽는 중…';
    const seekButton = document.createElement('button'); seekButton.disabled = true; seekButton.textContent = '원본 이동 없음'; seekButton.onclick = () => seek(i);
    article.append(select, stage, caption, seekButton); $('cards').append(article);
    return {canvas, caption, seek: seekButton};
  });
  zoom();
  try {
    const result = await Promise.all(selected.map(loadImages));
    if (ticket !== revision) return;
    loaded = result; window.reviewReady = true; controls(true); render();
  } catch (error) {
    if (ticket === revision) $('error').textContent = error.message;
  }
}
function step(direction) {
  if (!window.reviewReady) return;
  pause();
  const v = selected[0], index = (frameAt(v) + direction + v.images.length) % v.images.length;
  phase = v.boundaries[index]; render();
}
$('provenance').textContent = DATA.provenance;
$('optional').textContent = DATA.optionalNote;
$('video').src = DATA.video; $('base').src = DATA.base;
$('video-hash').textContent = 'video/original.mp4 · SHA-256 ' + DATA.videoHash;
$('base-hash').textContent = 'video/input-canvas.png · SHA-256 ' + DATA.baseHash;
$('video').onerror = () => { $('seek-status').textContent = '이 브라우저에서 내장 MP4를 재생할 수 없습니다.'; };
if (DATA.diagnostic) { $('diagnostic').hidden = false; $('contact').src = DATA.diagnostic; }
if (DATA.alignment) {
  $('alignment').hidden = false; $('alignment-note').textContent = DATA.alignment.note;
  $('alignment-evidence').textContent = JSON.stringify(DATA.alignment.report, null, 2);
}
for (const mode of DATA.modes) {
  const button = document.createElement('button'); button.textContent = mode.label; button.dataset.mode = mode.id;
  button.onclick = () => setup(mode.ids, mode); $('modes').append(button);
}
$('play').onclick = () => { if (playing) pause(); else { playing = true; last = null; $('play').textContent = '일시정지'; } };
$('prev').onclick = () => step(-1); $('next').onclick = () => step(1);
$('scrub').oninput = () => { pause(); phase = Math.min(Number($('scrub').value) / 10000, 1 - 1e-10); render(); };
$('zoom').onchange = zoom;
$('bg').onchange = () => document.documentElement.style.setProperty('--background', $('bg').value);
$('speed').onchange = () => { last = null; };
document.addEventListener('visibilitychange', () => { last = null; });
function tick(now) {
  if (playing && window.reviewReady && !document.hidden) {
    if (last !== null) { phase = (phase + (now - last) / selected[0].durationMs * Number($('speed').value)) % 1; render(); }
    last = now;
  }
  requestAnimationFrame(tick);
}
setup(DATA.modes[0].ids, DATA.modes[0]); requestAnimationFrame(tick);
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, help="출력 HTML 경로 (기본 ROOT/review.html, 기존 파일 보존)")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    output = args.output.expanduser().resolve() if args.output else root / "review.html"
    if output.suffix.lower() != ".html":
        parser.error("출력은 .html 파일이어야 합니다")
    if output.exists():
        parser.error(f"기존 파일을 보존합니다. --output에 새 경로를 지정하세요: {output}")
    try:
        data = build_data(root)
        # Escape script terminators and JS line separators even inside JSON evidence.
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        document = HTML.replace("__DATA__", payload)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(document)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        parser.exit(1, f"리뷰 HTML 생성 실패: {exc}\n")
    print(output)


if __name__ == "__main__":
    main()
