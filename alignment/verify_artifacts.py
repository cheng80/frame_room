"""Read-only final-export oracle; no renderer, database, server or provider imports.

Run: engine/sprite-gen/.venv/bin/python -m alignment.verify_artifacts [OUTPUT_DIR]
JSON goes to stdout. Exit 0=PASS, 1=FAIL, 2=BLOCKED (missing output files).
Parent hashes are checked through sourceAssets, not against unavailable originals.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

import numpy as np
from PIL import Image

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "artifacts/acceptance/real-character/output"
FILES = ("atlas.png", "pngs.zip", "runtime.json", "aseprite.json", "qa.json", "bundle.zip")
ANIMATION_FILES = ("animations.zip", "animation-manifest.json")
PIN = "b058341f7543f3adcbea227bd4e6b7587895b1bc"
MAX_BYTES = 512 * 1024 * 1024
MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024
MAX_PIXELS = 64_000_000


class ArtifactValidationError(Exception):
    def __init__(self, code, message, details=None, status="FAIL"):
        self.code, self.message, self.details, self.status = code, message, details or {}, status
        super().__init__(message)


def require(condition, code, message, **details):
    if not condition:
        raise ArtifactValidationError(code, message, details)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hash_value(value, where):
    require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None,
            "HASH_MISSING", "SHA-256 기록이 없거나 형식이 잘못되었습니다.", field=where)
    return value


def integer(value, low, high, where):
    require(type(value) is int and low <= value <= high, "INVALID_NUMBER", "정수 범위가 잘못되었습니다.", field=where)
    return value


def finite(value, where):
    require(type(value) in (int, float) and math.isfinite(value), "INVALID_NUMBER", "유한한 숫자가 필요합니다.", field=where)
    return value


def indexed(items, key, where):
    require(isinstance(items, list), "INVALID_SCHEMA", "목록이 필요합니다.", field=where)
    result = {}
    for item in items:
        require(isinstance(item, dict), "INVALID_SCHEMA", "객체가 필요합니다.", field=where)
        ident = item.get(key)
        require(isinstance(ident, str) and bool(ident) and ident not in result,
                "DUPLICATE_OR_MISSING_ID", "ID가 없거나 중복됩니다.", field=where, id=ident)
        result[ident] = item
    return result


def parse_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "INVALID_JSON", "JSON 키가 중복됩니다.", key=key)
            result[key] = value
        return result
    def nonfinite(value):
        raise ArtifactValidationError("INVALID_JSON", "JSON의 NaN/Infinity는 허용하지 않습니다.")
    return json.loads(data, object_pairs_hook=unique, parse_constant=nonfinite)


def image(data, where):
    with Image.open(io.BytesIO(data)) as opened:
        require(opened.format == "PNG" and opened.width * opened.height <= MAX_PIXELS,
                "INVALID_IMAGE", "유효한 크기의 PNG가 필요합니다.", file=where)
        opened.load()
        return opened.convert("RGBA")


def archive(stack, data, where):
    zipped = stack.enter_context(zipfile.ZipFile(io.BytesIO(data)))
    members = zipped.infolist()
    names = [member.filename for member in members]
    require(len(names) == len(set(names)), "DUPLICATE_ZIP_MEMBER", "ZIP 경로가 중복됩니다.", file=where)
    require(sum(m.file_size for m in members) <= MAX_ZIP_BYTES, "ZIP_LIMIT", "ZIP 크기 제한을 초과했습니다.", file=where)
    for member in members:
        path = PurePosixPath(member.filename)
        require(not path.is_absolute() and ".." not in path.parts and "\\" not in member.filename
                and ":" not in member.filename and not stat.S_ISLNK(member.external_attr >> 16)
                and not member.is_dir() and member.file_size <= MAX_BYTES,
                "INVALID_ZIP_MEMBER", "ZIP 파일 경로/크기가 잘못되었습니다.", file=where, member=member.filename)
    return zipped


def member(zipped, name):
    require(isinstance(name, str) and name in zipped.namelist(), "ZIP_MEMBER_MISSING", "ZIP 내부 파일이 없습니다.", member=name)
    return zipped.read(name)


def same_rgba(actual, expected, where):
    require(actual.size == expected.size, "RGBA_MISMATCH", "PNG와 atlas crop 크기가 다릅니다.", occurrence=where)
    a, b = np.asarray(actual), np.asarray(expected)
    count = int(np.count_nonzero(np.any(a != b, axis=2)))
    require(count == 0, "RGBA_MISMATCH", "PNG와 atlas crop 전체 RGBA가 다릅니다.", occurrence=where, differingPixels=count)


def lineage(runtime):
    assets = indexed(runtime.get("sourceAssets"), "assetId", "sourceAssets")
    sources = indexed(runtime.get("frameSources"), "frameVersionId", "frameSources")
    require(bool(assets) and bool(sources), "LINEAGE_MISSING", "sourceAssets와 frameSources가 필요합니다.")
    parents, edges = {}, []
    for aid, asset in assets.items():
        hash_value(asset.get("sha256"), f"sourceAssets.{aid}.sha256")
        hash_value(asset.get("decodedHash"), f"sourceAssets.{aid}.decodedHash")
        provenance = asset.get("provenance", {})
        require(isinstance(provenance, dict), "INVALID_SCHEMA", "provenance 객체가 필요합니다.", assetId=aid)
        parent = provenance.get("parentAssetId")
        require(parent is None or (isinstance(parent, str) and bool(parent)), "PARENT_ASSET_MISSING", "부모 자산 ID가 잘못되었습니다.", assetId=aid)
        if provenance.get("kind") in ("cutout", "raw-crop"):
            require(bool(parent), "PARENT_ASSET_MISSING", "파생 자산의 부모 연결이 없습니다.", assetId=aid)
        if parent:
            require(parent in assets, "PARENT_ASSET_MISSING", "부모 자산/해시 기록이 없습니다.", assetId=aid, parentAssetId=parent)
            parent_hash = hash_value(assets[parent].get("sha256"), f"sourceAssets.{parent}.sha256")
            if "parentSha256" in provenance:
                require(provenance["parentSha256"] == parent_hash, "PARENT_HASH_MISMATCH", "부모 해시 기록이 다릅니다.", assetId=aid)
            parents[aid] = parent
            edges.append({"assetId": aid, "parentAssetId": parent, "parentSha256": parent_hash})
    chains = {}
    for aid in assets:
        chain, current = [], aid
        while current is not None:
            require(current not in chain, "LINEAGE_CYCLE", "자산 부모 연결이 순환합니다.", assetId=aid)
            chain.append(current)
            current = parents.get(current)
        chains[aid] = chain
    external_parents = set()
    for fid, source in sources.items():
        require(isinstance(source.get("frameId"), str) and bool(source["frameId"]), "LINEAGE_MISSING", "논리 frameId가 없습니다.", frameVersionId=fid)
        raw, processed = source.get("rawAssetId"), source.get("imageAssetId")
        require(raw in assets and processed in assets, "FRAME_SOURCE_MISSING", "프레임 원본/이미지 자산 해시가 없습니다.", frameVersionId=fid)
        require(raw in chains[processed], "FRAME_ANCESTRY_MISMATCH", "프레임 이미지의 부모 계보가 rawAssetId로 연결되지 않습니다.", frameVersionId=fid)
        rect = source.get("sourceRect", {})
        for key in ("x", "y", "width", "height"):
            integer(rect.get(key), 1 if key in ("width", "height") else 0, 32768, f"{fid}.sourceRect.{key}")
        mapping = source.get("sourceToFrameTransform", {})
        for key in ("scaleX", "scaleY", "offsetX", "offsetY"):
            value = finite(mapping.get(key), f"{fid}.sourceToFrameTransform.{key}")
            if key.startswith("scale"):
                require(value > 0, "INVALID_NUMBER", "원본 좌표 배율이 양수여야 합니다.", frameVersionId=fid)
        parent_frame = source.get("parentFrameVersionId")
        if parent_frame:
            require(isinstance(parent_frame, str) and parent_frame != fid, "FRAME_ANCESTRY_MISMATCH", "부모 프레임 ID가 잘못되었습니다.", frameVersionId=fid)
            if parent_frame not in sources:
                external_parents.add(parent_frame)
        generation = source.get("generationVersionId")
        if generation:
            recorded = {assets[a].get("provenance", {}).get("generationVersionId") for a in chains[raw]}
            require(generation in recorded, "GENERATION_LINEAGE_MISMATCH", "원본 계보에서 generationVersionId를 확인할 수 없습니다.", frameVersionId=fid)
        interpolated = source.get("interpolated")
        require(interpolated is None or type(interpolated) is bool, "INTERPOLATION_LINEAGE_MISMATCH", "보간 여부는 boolean이어야 합니다.", frameVersionId=fid)
        interpolation = source.get("interpolation")
        if interpolated:
            require(isinstance(interpolation, dict) and isinstance(interpolation.get("method"), str) and bool(interpolation["method"]),
                    "INTERPOLATION_LINEAGE_MISMATCH", "보간 방식 기록이 없습니다.", frameVersionId=fid)
            fraction = finite(interpolation.get("fraction"), f"{fid}.interpolation.fraction")
            indices = interpolation.get("sourceFrameIndices")
            require(0 < fraction < 1 and isinstance(indices, list) and len(indices) == 2
                    and all(type(index) is int and index >= 0 for index in indices) and indices[0] != indices[1],
                    "INTERPOLATION_LINEAGE_MISMATCH", "보간 비율/원본 프레임 연결이 잘못되었습니다.", frameVersionId=fid)
        else:
            require(interpolation is None, "INTERPOLATION_LINEAGE_MISMATCH", "원본 프레임에 보간 기록이 붙어 있습니다.", frameVersionId=fid)
    return assets, sources, edges, sorted(external_parents)


def animation_timeline(data, format, metadata, cells, durations, loop, where):
    """Independent decoder oracle. Do not import the writer or re-render cells."""
    boundaries, elapsed = [], 0
    for duration in durations:
        elapsed += duration
        boundaries.append(elapsed)
    frame_durations, mappings, changed = [], [], [None] * len(cells)
    cursor = source_index = 0
    with Image.open(io.BytesIO(data)) as decoded:
        require(decoded.format == format and decoded.size == cells[0].size,
                "ANIMATION_MISMATCH", "애니메이션 형식/셀 크기가 다릅니다.", file=where)
        expected_loop = (0 if loop else 1) if format == "WEBP" else (0 if loop else None)
        require(decoded.info.get("loop") == expected_loop, "ANIMATION_TIMING_MISMATCH", "애니메이션 반복/단발 설정이 다릅니다.", file=where)
        for i in range(decoded.n_frames):
            decoded.seek(i); decoded.load()
            duration = integer(decoded.info.get("duration"), 1, 2**31-1, f"{where}.{i}.duration")
            actual = decoded.convert("RGBA")
            pixels = np.asarray(actual)
            if format == "GIF":
                require(np.all((pixels[..., 3] == 0) | (pixels[..., 3] == 255))
                        and len(np.unique(pixels[pixels[..., 3] != 0, :3], axis=0)) <= 255,
                        "ANIMATION_MISMATCH", "GIF 색상/알파 제약이 다릅니다.", file=where)
            end, covered = cursor + duration, []
            j = source_index
            while j < len(cells) and (boundaries[j-1] if j else 0) < end:
                if boundaries[j] > cursor:
                    covered.append(j)
                    if format == "WEBP":
                        same_rgba(actual, cells[j], f"{where}/{j}")
                    else:
                        original = np.asarray(cells[j])
                        require(np.array_equal(pixels[..., 3] != 0, original[..., 3] > 128),
                                "ANIMATION_MISMATCH", "GIF 알파 임계값 결과가 다릅니다.", file=where, occurrenceIndex=j)
                        count = int(np.count_nonzero(np.any(pixels != original, axis=2)))
                        require(changed[j] in (None, count), "ANIMATION_MISMATCH", "같은 슬롯의 GIF 픽셀이 재생 도중 달라집니다.", file=where)
                        changed[j] = count
                        if np.all((original[..., 3] == 0) | (original[..., 3] == 255)) and len(np.unique(original[original[..., 3] != 0, :3], axis=0)) <= 255:
                            same_rgba(actual, cells[j], f"{where}/{j}")
                if boundaries[j] <= end:
                    source_index = j + 1
                j += 1
            require(bool(covered) and end <= elapsed, "ANIMATION_TIMING_MISMATCH", "애니메이션 프레임의 재생 구간이 다릅니다.", file=where)
            cursor = end
            frame_durations.append(duration); mappings.append(covered)
    require(cursor == elapsed and source_index == len(cells), "ANIMATION_TIMING_MISMATCH", "애니메이션 전체 시간이 다릅니다.", file=where)
    require(metadata.get("decodedFrameCount") == len(frame_durations) and metadata.get("decodedDurationsMs") == frame_durations
            and metadata.get("decodedSourceIndices") == mappings and metadata.get("durationMs") == elapsed
            and metadata.get("loop") is loop and metadata.get("playCount") == (0 if loop else 1)
            and metadata.get("verified") is True, "ANIMATION_METADATA_MISMATCH", "애니메이션 디코딩 결과와 manifest가 다릅니다.", file=where)
    if format == "GIF":
        require(metadata.get("changedPixelsPerOccurrence") == changed and metadata.get("pixelLossDetected") is any(changed),
                "ANIMATION_METADATA_MISMATCH", "GIF 색상 손실 기록이 다릅니다.", file=where)
    else:
        require(metadata.get("fullRGBAParity") is True and metadata.get("lossy") is False and metadata.get("timingLossy") is False,
                "ANIMATION_METADATA_MISMATCH", "무손실 WebP 검증 기록이 다릅니다.", file=where)


def animations(stack, data, runtime, clips, crops):
    zipped = archive(stack, data["animations.zip"], "animations.zip")
    metadata = parse_json(data["animation-manifest.json"])
    require(member(zipped, "manifest.json") == data["animation-manifest.json"],
            "ANIMATION_MANIFEST_MISMATCH", "애니메이션 ZIP의 manifest가 독립 파일과 다릅니다.")
    for key in ("schemaVersion", "exportId", "projectRevision", "recipeHash"):
        require(metadata.get(key) == runtime.get(key), "SNAPSHOT_MISMATCH", "애니메이션 출력의 snapshot이 다릅니다.", field=key)
    summary = runtime["animationExports"]
    require(metadata.get("version") == summary.get("version") == "canonical-animation-v1"
            and metadata.get("source") == "canonical-bake-cells", "ANIMATION_METADATA_MISMATCH", "애니메이션 출력 버전/원본이 다릅니다.")
    anim_clips = indexed(metadata.get("clips"), "id", "animations.clips")
    require(list(anim_clips) == list(clips), "TIMELINE_MISMATCH", "애니메이션 동작 순서가 다릅니다.")
    expected_files, expected_warnings, reports = {"manifest.json"}, [], []
    for cid, clip in clips.items():
        exported = anim_clips[cid]
        for key in ("clipId", "clipRevisionId", "name", "loop", "endBehavior", "durationMs"):
            require(exported.get(key) == clip.get(key), "ANIMATION_METADATA_MISMATCH", "애니메이션 동작 정보가 다릅니다.", clipId=cid, field=key)
        slots = clip["occurrences"]
        width = max(crops[slot["renderedFrameId"]].width for slot in slots)
        height = max(crops[slot["renderedFrameId"]].height for slot in slots)
        columns = math.ceil(math.sqrt(len(slots)))
        require(exported.get("cell") == {"width": width, "height": height} and exported.get("frameCount") == len(slots),
                "ANIMATION_METADATA_MISMATCH", "애니메이션 셀/프레임 수가 다릅니다.", clipId=cid)
        exported_slots = exported.get("occurrences")
        require(isinstance(exported_slots, list) and len(exported_slots) == len(slots), "TIMELINE_MISMATCH", "애니메이션 슬롯 수가 다릅니다.", clipId=cid)
        cells = []
        for i, slot in enumerate(slots):
            cell = crops[slot["renderedFrameId"]]
            padded = Image.new("RGBA", (width, height)); padded.paste(cell, (0, 0)); cells.append(padded)
            expected = {**slot, "index": i, "sourceCell": {"width": cell.width, "height": cell.height},
                        "stripRect": {"x": i * width, "y": 0, "width": width, "height": height},
                        "gridRect": {"x": i % columns * width, "y": i // columns * height, "width": width, "height": height}}
            require(exported_slots[i] == expected, "TIMELINE_MISMATCH", "애니메이션 슬롯의 순서/시간/앵커/rect가 다릅니다.", clipId=cid, occurrenceIndex=i)
        durations = [slot["durationMs"] for slot in slots]
        formats = exported.get("formats", {})
        require(set(formats) == {"stripPng", "gridPng", "gif", "webp"}, "ANIMATION_METADATA_MISMATCH", "애니메이션 형식 목록이 다릅니다.", clipId=cid)
        report = {"clipId": cid, "formatsChecked": [], "omittedFormats": []}
        for kind, record in formats.items():
            if record.get("status") == "omitted":
                reason = record.get("reason", {})
                code = reason.get("code")
                valid = ((kind == "gif" and code == "GIF_TIMING_UNREPRESENTABLE" and any(d < 10 for d in durations))
                         or (kind == "webp" and code == "WEBP_UNAVAILABLE")
                         or (kind == "webp" and code == "WEBP_DIMENSION_LIMIT" and max(width, height) > 16383)
                         or (kind in ("stripPng", "gridPng") and code == "SHEET_TOO_LARGE"
                             and width * height * (len(slots) if kind == "stripPng" else columns * math.ceil(len(slots) / columns)) > MAX_PIXELS))
                require(valid and isinstance(reason.get("message"), str) and bool(reason["message"]) and "file" not in record,
                        "ANIMATION_METADATA_MISMATCH", "형식 제외 이유가 잘못되었습니다.", clipId=cid, format=kind)
                expected_warnings.append({"clipId": cid, "format": kind, **reason})
                report["omittedFormats"].append(kind)
                continue
            require(record.get("status") == "created", "ANIMATION_METADATA_MISMATCH", "형식 생성 상태가 잘못되었습니다.", clipId=cid, format=kind)
            name = record.get("file")
            require(isinstance(name, str) and name.startswith("clips/") and name not in expected_files,
                    "INVALID_ZIP_MEMBER", "애니메이션 파일 경로가 없거나 중복됩니다.", file=name)
            content = member(zipped, name)
            require(hash_value(record.get("sha256"), name) == sha(content), "FILE_HASH_MISMATCH", "애니메이션 내부 파일 해시가 다릅니다.", file=name)
            expected_files.add(name)
            if kind in ("stripPng", "gridPng"):
                cols = len(slots) if kind == "stripPng" else columns
                rows = math.ceil(len(slots) / cols)
                sheet = image(content, name)
                require(sheet.size == (cols * width, rows * height) and record.get("columns") == cols and record.get("rows") == rows
                        and record.get("width") == sheet.width and record.get("height") == sheet.height and record.get("fullRGBAParity") is True,
                        "ANIMATION_METADATA_MISMATCH", "PNG 시트 크기/격자 기록이 다릅니다.", file=name)
                for i in range(cols * rows):
                    x, y = i % cols * width, i // cols * height
                    wanted = cells[i] if i < len(cells) else Image.new("RGBA", (width, height))
                    same_rgba(sheet.crop((x, y, x + width, y + height)), wanted, f"{name}/{i}")
            else:
                require(record.get("sourceDurationsMs") == durations, "ANIMATION_TIMING_MISMATCH", "애니메이션 원본 시간이 다릅니다.", file=name)
                encoded_durations = durations
                if kind == "gif":
                    encoded_durations, previous, elapsed = [], 0, 0
                    for duration in durations:
                        elapsed += duration
                        rounded = (elapsed + 5) // 10 * 10
                        encoded_durations.append(rounded - previous); previous = rounded
                    require(min(durations) >= 10 and record.get("encodedDurationsMs") == encoded_durations
                            and record.get("timingLossy") is (durations != encoded_durations)
                            and record.get("totalDurationErrorMs") == sum(encoded_durations) - sum(durations)
                            and record.get("lossy") is True and record.get("maxOpaqueColors") == 255
                            and record.get("alphaThreshold") == 128 and record.get("transparentWhen") == "alpha<=128",
                            "ANIMATION_METADATA_MISMATCH", "GIF 시간/색상/알파 제약 기록이 다릅니다.", file=name)
                animation_timeline(content, "GIF" if kind == "gif" else "WEBP", record, cells, encoded_durations, clip["loop"], name)
            report["formatsChecked"].append(kind)
        reports.append(report)
    require(set(zipped.namelist()) == expected_files, "ZIP_MEMBER_MISMATCH", "애니메이션 ZIP 파일 목록이 다릅니다.")
    # JSON objects are sorted when saved, so warning order is not format order.
    order = lambda warning: (warning["clipId"], warning["format"])
    require(sorted(metadata.get("warnings", []), key=order) == sorted(expected_warnings, key=order)
            and summary.get("warnings") == metadata.get("warnings"), "ANIMATION_METADATA_MISMATCH", "형식 제외 경고 기록이 다릅니다.")
    return reports


def _verify(directory):
    missing = [name for name in FILES if not (directory / name).is_file()]
    if missing:
        raise ArtifactValidationError("ARTIFACTS_MISSING", "검사할 최종 파일이 아직 없습니다.", {"missing": missing}, "BLOCKED")
    data = {}
    def read_file(name):
        path = directory / name
        if not path.is_file():
            raise ArtifactValidationError("ARTIFACTS_MISSING", "검사할 최종 파일이 아직 없습니다.", {"missing": [name]}, "BLOCKED")
        require(not path.is_symlink() and path.stat().st_size <= MAX_BYTES, "INVALID_ARTIFACT", "일반 크기 제한 내 파일이 필요합니다.", file=name)
        return path.read_bytes()
    for name in FILES:
        data[name] = read_file(name)
    runtime, qa, aseprite = (parse_json(data[name]) for name in ("runtime.json", "qa.json", "aseprite.json"))
    require(runtime.get("schemaVersion") == 1 and runtime.get("engineCommit") == PIN, "VERSION_MISMATCH", "schemaVersion/source pin이 다릅니다.")
    require(runtime.get("qaStatus") == qa.get("status") == "verified" and qa.get("errors") == [] and qa.get("fullRGBAParity") is True,
            "QA_NOT_VERIFIED", "승인된 최종 bake QA가 아닙니다.")
    hash_value(runtime.get("recipeHash"), "recipeHash")
    require(runtime["recipeHash"] == runtime.get("renderRecipeHash") == qa.get("recipeHash")
            and runtime.get("projectRevision") == qa.get("projectRevision"), "SNAPSHOT_MISMATCH", "recipe/project revision이 다릅니다.")
    integer(runtime.get("projectRevision"), 1, 2**63-1, "projectRevision")
    require(isinstance(runtime.get("exportId"), str) and bool(runtime["exportId"]), "INVALID_SCHEMA", "exportId가 필요합니다.")
    hashes = indexed(runtime.get("files"), "name", "files")
    animation_output = ("animationExports" in runtime or bool(set(hashes) & set(ANIMATION_FILES))
                        or any((directory / name).exists() for name in ANIMATION_FILES))
    file_names = FILES
    if animation_output:
        summary = runtime.get("animationExports")
        require(isinstance(summary, dict) and summary.get("archive") == "animations.zip"
                and summary.get("manifest") == "animation-manifest.json",
                "ANIMATION_METADATA_MISMATCH", "runtime의 애니메이션 출력 연결이 잘못되었습니다.")
        for name in ANIMATION_FILES:
            data[name] = read_file(name)
        file_names = FILES[:-1] + ANIMATION_FILES + FILES[-1:]
    expected_hashes = set(file_names) - {"runtime.json", "bundle.zip"}
    require(set(hashes) == expected_hashes, "FILE_HASH_MISMATCH", "runtime의 파일 해시 목록이 다릅니다.")
    for name in expected_hashes:
        require(name in hashes and hash_value(hashes[name].get("sha256"), name) == sha(data[name]),
                "FILE_HASH_MISMATCH", "최종 파일 해시가 다릅니다.", file=name)
    atlas = image(data["atlas.png"], "atlas.png")
    meta = runtime.get("atlas", {})
    require(meta.get("file") == "atlas.png" and meta.get("sha256") == sha(data["atlas.png"])
            and (meta.get("width"), meta.get("height")) == atlas.size, "ATLAS_MISMATCH", "atlas 크기/해시 기록이 다릅니다.")
    pixels = np.asarray(atlas)
    require(not np.any(pixels[pixels[..., 3] == 0, :3]), "ALPHA_NORMALIZATION_FAILED", "alpha=0의 숨은 RGB가 정규화되지 않았습니다.")
    require(runtime.get("alphaNormalization") == "alpha0-rgb-zero-v1", "ALPHA_NORMALIZATION_FAILED", "알파 정규화 버전이 다릅니다.")
    frames = indexed(runtime.get("frames"), "id", "frames")
    clips = indexed(runtime.get("clips"), "id", "clips")
    require(bool(frames) and bool(clips), "EMPTY_TIMELINE", "프레임과 동작이 필요합니다.")
    assets, sources, edges, external_parents = lineage(runtime)
    require(runtime.get("clipRevisionIds") == [c.get("clipRevisionId") for c in clips.values()], "SNAPSHOT_MISMATCH", "동작 revision 목록이 다릅니다.")
    qa_frames = {}
    for frame in qa.get("frames", []):
        key = (frame.get("clipId"), frame.get("occurrenceId"))
        require(key not in qa_frames, "DUPLICATE_OR_MISSING_ID", "QA 슬롯이 중복됩니다.")
        qa_frames[key] = frame
    total = 0
    clip_reports, animation_reports = [], []
    used_frames, used_sources = set(), set()
    expected_sequences = {"manifest.json"}
    with ExitStack() as stack:
        pngs = archive(stack, data["pngs.zip"], "pngs.zip")
        packed = archive(stack, data["bundle.zip"], "bundle.zip")
        sequence = parse_json(member(pngs, "manifest.json"))
        for key in ("schemaVersion", "exportId", "projectRevision", "recipeHash"):
            require(sequence.get(key) == runtime.get(key), "SNAPSHOT_MISMATCH", "PNG sequence의 snapshot이 다릅니다.", field=key)
        seq_clips = indexed(sequence.get("clips"), "id", "pngs.manifest.clips")
        require(list(seq_clips) == list(clips), "TIMELINE_MISMATCH", "동작 순서가 다릅니다.")
        for name in file_names[:-1]:
            require(member(packed, name) == data[name], "BUNDLE_MISMATCH", "bundle 내부 파일이 독립 파일과 다릅니다.", file=name)
        crops = {}
        for fid, frame in frames.items():
            r = frame.get("rect", {})
            x, y = (integer(r.get(k), 0, 32768, f"{fid}.{k}") for k in ("x", "y"))
            w, h = (integer(r.get(k), 1, 32768, f"{fid}.{k}") for k in ("width", "height"))
            require(x+w <= atlas.width and y+h <= atlas.height, "RECT_OUT_OF_BOUNDS", "atlas rect가 이미지 밖입니다.", frameId=fid)
            crop = atlas.crop((x, y, x+w, y+h))
            require(hash_value(frame.get("decodedHash"), f"{fid}.decodedHash") == sha(crop.tobytes()), "DECODED_HASH_MISMATCH", "atlas crop의 픽셀 해시가 다릅니다.", frameId=fid)
            require(crop.getchannel("A").getbbox() is not None, "EMPTY_ALPHA", "빈 알파 프레임입니다.", frameId=fid)
            name = frame.get("png")
            png = member(pngs, name)
            require(hash_value(frame.get("pngSha256"), f"{fid}.pngSha256") == sha(png), "PNG_HASH_MISMATCH", "PNG 파일 해시가 다릅니다.", frameId=fid)
            same_rgba(image(png, name), crop, fid)
            require(member(packed, name) == png, "BUNDLE_MISMATCH", "bundle의 frame PNG가 다릅니다.", frameId=fid)
            expected_sequences.add(name)
            crops[fid] = crop
        ase_frames, tags = aseprite.get("frames"), aseprite.get("meta", {}).get("frameTags")
        require(isinstance(ase_frames, list) and isinstance(tags, list) and len(tags) == len(clips), "ASEPRITE_MISMATCH", "Aseprite 프레임/tag 목록이 다릅니다.")
        ase_meta = aseprite.get("meta", {})
        require(ase_meta.get("image") == "atlas.png" and ase_meta.get("runtime") == "runtime.json"
                and ase_meta.get("size") == {"w": atlas.width, "h": atlas.height}, "ASEPRITE_MISMATCH", "Aseprite atlas/companion 정보가 다릅니다.")
        for ci, (cid, clip) in enumerate(clips.items()):
            seq_clip = seq_clips[cid]
            require({k:v for k,v in seq_clip.items() if k != "occurrences"} == {k:v for k,v in clip.items() if k != "occurrences"},
                    "TIMING_MISMATCH", "PNG sequence의 동작 설정/loop/duration이 다릅니다.", clipId=cid)
            require(type(clip.get("loop")) is bool and clip.get("endBehavior") == "hold-last", "INVALID_TIMING", "loop/hold-last 설정이 잘못되었습니다.", clipId=cid)
            require(isinstance(clip.get("clipRevisionId"), str) and bool(clip["clipRevisionId"]), "SNAPSHOT_MISMATCH", "clipRevisionId가 필요합니다.", clipId=cid)
            fps = finite(clip.get("defaultFps"), "defaultFps")
            require(1 <= fps <= 60, "INVALID_TIMING", "FPS 범위가 잘못되었습니다.", clipId=cid)
            slots = indexed(clip.get("occurrences"), "id", cid)
            seq_slots = indexed(seq_clip.get("occurrences"), "id", f"pngs.{cid}")
            require(bool(slots) and list(slots) == list(seq_slots), "TIMELINE_MISMATCH", "빈 동작이거나 슬롯 순서가 다릅니다.", clipId=cid)
            boundaries, elapsed, start = [], 0, total
            for oid, occurrence in slots.items():
                seq_occ = seq_slots[oid]
                require({k:v for k,v in seq_occ.items() if k not in ("file", "sha256")} == occurrence,
                        "TIMELINE_MISMATCH", "슬롯 순서/시간/앵커/계보가 다릅니다.", clipId=cid, occurrenceId=oid)
                require(occurrence.get("occurrenceId") == oid, "TIMELINE_MISMATCH", "occurrence ID alias가 다릅니다.", occurrenceId=oid)
                duration = integer(occurrence.get("durationMs"), 1, 60000, f"{oid}.durationMs")
                mode = occurrence.get("timingMode")
                require(mode in ("fps", "explicit") and (mode != "fps" or duration == math.floor(1000 / fps + .5)), "INVALID_TIMING", "확정 FPS 시간이 다릅니다.", occurrenceId=oid)
                rid, source_id = occurrence.get("renderedFrameId"), occurrence.get("frameVersionId")
                require(rid in frames and source_id in sources, "FRAME_SOURCE_MISSING", "슬롯의 rendered frame/lineage가 없습니다.", occurrenceId=oid)
                used_frames.add(rid); used_sources.add(source_id)
                name = seq_occ.get("file")
                require(name not in expected_sequences, "TIMELINE_MISMATCH", "슬롯 PNG 경로가 중복됩니다.", occurrenceId=oid)
                expected_sequences.add(name)
                png = member(pngs, name)
                require(hash_value(seq_occ.get("sha256"), f"{oid}.sha256") == sha(png), "PNG_HASH_MISMATCH", "슬롯 PNG 해시가 다릅니다.", occurrenceId=oid)
                same_rgba(image(png, name), crops[rid], f"{cid}/{oid}")
                q = qa_frames.get((cid, oid), {})
                require(q.get("frameVersionId") == source_id and q.get("decodedHash") == frames[rid]["decodedHash"]
                        and q.get("anchor") == occurrence.get("anchor") and q.get("errors") == []
                        and q.get("overflowPx") == {"left":0,"top":0,"right":0,"bottom":0},
                        "QA_FRAME_MISMATCH", "QA 슬롯의 픽셀/계보/overflow 기록이 다릅니다.", occurrenceId=oid)
                require(total < len(ase_frames), "ASEPRITE_MISMATCH", "Aseprite 슬롯이 누락되었습니다.")
                af, r = ase_frames[total], frames[rid]["rect"]
                require(af.get("duration") == duration and type(af.get("duration")) is int and af.get("filename") == name
                        and af.get("frame") == {"x":r["x"],"y":r["y"],"w":r["width"],"h":r["height"]}
                        and af.get("sourceSize") == {"w":r["width"],"h":r["height"]}
                        and af.get("spriteSourceSize") == {"x":0,"y":0,"w":r["width"],"h":r["height"]}
                        and af.get("trimmed") is False and af.get("rotated") is False,
                        "ASEPRITE_MISMATCH", "Aseprite 슬롯의 시간/rect가 다릅니다.", occurrenceId=oid)
                elapsed += duration
                boundaries.append(elapsed)
                total += 1
            require(type(clip.get("durationMs")) is int and clip["durationMs"] == elapsed, "INVALID_TIMING", "동작의 누적 시간이 다릅니다.", clipId=cid)
            require(tags[ci] == {"name":clip.get("name") or cid,"from":start,"to":total-1,"direction":"forward"}, "ASEPRITE_MISMATCH", "Aseprite tag 범위가 다릅니다.", clipId=cid)
            clip_reports.append({"clipId":cid,"occurrences":len(slots),"durationMs":elapsed,"boundariesMs":boundaries,
                                 "loop":clip["loop"],"endBehavior":clip["endBehavior"]})
        require(len(ase_frames) == len(qa_frames) == total, "TIMELINE_MISMATCH", "QA/Aseprite 슬롯 수가 다릅니다.")
        require(used_frames == set(frames) and used_sources == set(sources), "LINEAGE_MISMATCH", "선택된 슬롯과 frame/lineage 목록이 다릅니다.")
        require(set(pngs.namelist()) == expected_sequences, "ZIP_MEMBER_MISMATCH", "PNG ZIP 파일 목록이 다릅니다.")
        require(set(packed.namelist()) == set(file_names[:-1]) | {f["png"] for f in frames.values()}, "ZIP_MEMBER_MISMATCH", "bundle 파일 목록이 다릅니다.")
        if animation_output:
            animation_reports = animations(stack, data, runtime, clips, crops)
            require(all(warning in qa.get("warnings", []) for warning in runtime["animationExports"]["warnings"]),
                    "ANIMATION_METADATA_MISMATCH", "QA에 형식 제외 이유가 누락되었습니다.")
    for name in file_names:
        require(sha((directory/name).read_bytes()) == sha(data[name]), "ARTIFACT_CHANGED", "검사 중 파일이 변경되었습니다.", file=name)
    return {"status":"PASS","exportId":runtime["exportId"],"projectRevision":runtime["projectRevision"],
        "recipeHash":runtime["recipeHash"],"engineCommit":runtime["engineCommit"],
        "occurrencesChecked":total,"renderedFramesChecked":len(frames),"fullRGBAParity":True,
        "clips":clip_reports,"frameSourcesChecked":len(sources),"sourceAssetsChecked":len(assets),
        "interpolatedFrameSourcesChecked":sum(source.get("interpolated") is True for source in sources.values()),
        "animationClips":animation_reports,
        "parentHashLinks":edges,"externalParentFrameVersionIds":external_parents,
        "files":[{"name":name,"sha256":sha(data[name])} for name in file_names],
        "limits":["원본 asset bytes는 출력 묶음에 없으므로 부모 ID/해시 기록의 연결만 검증합니다.",
                  "외부 parentFrameVersionId의 과거 프레임과 실제 생성/외형/브라우저 재생은 검증하지 않습니다."]}


def verify_artifacts(directory=DEFAULT_OUTPUT):
    """Verify saved files only; return report or raise ArtifactValidationError."""
    try:
        return _verify(Path(directory))
    except ArtifactValidationError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError,
            zipfile.BadZipFile, RuntimeError, Image.DecompressionBombError) as exc:
        raise ArtifactValidationError("INVALID_ARTIFACT", "파일이 손상되었거나 artifact schema가 잘못되었습니다.", {"reason":type(exc).__name__}) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", nargs="?", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        result = verify_artifacts(args.output_dir)
        code = 0
    except ArtifactValidationError as exc:
        result = {"status":exc.status,"code":exc.code,"message":exc.message,"details":exc.details}
        code = 2 if exc.status == "BLOCKED" else 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
