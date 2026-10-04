"""Product rendering contract. No per-pose fitting or engine curation fallback.

Pixels flow once through crop -> shared scale/anchor -> canvas edits -> affine
transform -> outline -> unbounded overflow check -> normalized bake -> atlas.
Positive rotation is counter-clockwise in screen coordinates, as in sprite-gen.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

import numpy as np
from PIL import Image

from alignment.animation_exports import AnimationExportError, build_animation_exports

ENGINE_COMMIT = "b058341f7543f3adcbea227bd4e6b7587895b1bc"
ADAPTER_VERSION = "alignment-v1"
ENGINE_ROOT = Path(__file__).resolve().parents[1] / "engine" / "sprite-gen"
MAX_PIXELS = 64_000_000


class PipelineError(Exception):
    def __init__(self, code, message, details=None):
        self.code, self.message, self.details = code, message, details or {}
        super().__init__(message)


def _error(code, message, **details):
    return {"code": code, "message": message, **details}


def _engine(module):
    # Never accidentally import the user's shared skill installation.
    if not (ENGINE_ROOT / "sprite_gen").is_dir():
        raise PipelineError("ENGINE_UNAVAILABLE", "프로젝트 전용 엔진이 없습니다.")
    for name, loaded in list(sys.modules.items()):
        if name == "sprite_gen" or name.startswith("sprite_gen."):
            origin = getattr(loaded, "__file__", None)
            if origin and not Path(origin).resolve().is_relative_to(ENGINE_ROOT.resolve()):
                raise PipelineError("ENGINE_SOURCE_MISMATCH", "공용 엔진을 사용할 수 없습니다.")
    root = str(ENGINE_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module("sprite_gen." + module)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _image_hash(image):
    return _hash(image.convert("RGBA").tobytes())


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PipelineError("INVALID_GEOMETRY", f"{name}: 유한한 숫자가 필요합니다.")
    return float(value)


def _integer(value, name, low=0, high=16384):
    number = _number(value, name)
    if number != int(number) or not low <= number <= high:
        raise PipelineError("INVALID_VALUE", f"{name}: {low}–{high} 정수가 필요합니다.")
    return int(number)


def _round(value):
    return math.floor(value + 0.5)


def _size(width, height):
    if width < 1 or height < 1 or width * height > MAX_PIXELS or max(width, height) > 32768:
        raise PipelineError("IMAGE_LIMIT", "출력 이미지 크기 제한을 초과했습니다.")
    return width, height


def _open(path):
    try:
        with Image.open(path) as im:
            _size(*im.size)
            im.load()
            return im.convert("RGBA")
    except PipelineError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise PipelineError("INVALID_IMAGE", "이미지를 읽을 수 없습니다.") from exc


def _stats(image):
    alpha = np.asarray(image)[..., 3]
    return {"transparent": int(np.count_nonzero(alpha == 0)),
            "partial": int(np.count_nonzero((alpha > 0) & (alpha < 255))),
            "opaque": int(np.count_nonzero(alpha == 255))}


def inspect_image(path):
    image = _open(path)
    return {"width": image.width, "height": image.height,
            "alphaStats": _stats(image), "decodedHash": _image_hash(image)}


def _normalize(image):
    pixels = np.array(image.convert("RGBA"))
    pixels[pixels[..., 3] == 0, :3] = 0
    return Image.fromarray(pixels)


def _components(image):
    # Upstream uses alpha>16. Give its connectivity algorithm an alpha>0 mask,
    # then copy original RGBA, preserving even alpha=1 detached weapon pixels.
    mask = Image.new("RGBA", image.size)
    mask.putalpha(Image.fromarray(np.where(np.asarray(image)[..., 3] > 0, 255, 0).astype("uint8")))
    return _engine("frames.extract").connected_components(mask)


def _rect(box):
    x, y, right, bottom = box
    return {"x": x, "y": y, "width": right - x, "height": bottom - y}


def _region(region, size):
    x, y = (_integer(region.get(k), k) for k in ("x", "y"))
    w, h = (_integer(region.get(k), k, 1) for k in ("width", "height"))
    if x + w > size[0] or y + h > size[1]:
        raise PipelineError("REGION_OUT_OF_BOUNDS", "추출 영역이 원본 밖입니다.", {"rect": region})
    return x, y, x + w, y + h


def extract_regions(path, params):
    image = _open(path)
    mode = params.get("mode", "whole")
    entries = []
    if mode == "whole":
        entries = [(image.copy(), (0, 0, *image.size), {})]
    elif mode == "regions":
        for region in params.get("regions", []):
            box = _region(region, image.size)
            entries.append((image.crop(box), box, {"manualRegion": True}))
    elif mode == "components":
        minimum = _integer(params.get("minArea", 4), "minArea", 1, MAX_PIXELS)
        extractor = _engine("frames.extract")
        for i, component in enumerate(_components(image)):
            # minArea is a review flag, never a licence to throw away equipment.
            entries.append((extractor.component_group_image(image, [component], padding=0),
                            component["bbox"], {"componentIndex": i, "area": component["area"],
                            "belowMinArea": component["area"] < minimum,
                            "reviewRequired": True}))
    elif mode == "grid":
        rows = _integer(params.get("rows", 1), "rows", 1, image.height)
        columns = _integer(params.get("columns", 1), "columns", 1, image.width)
        components = _components(image)
        # A component crossing a nominal cell is retained whole and flagged.
        # Overlapping proposals are intentional; adoption/merging is manual.
        for row in range(rows):
            for col in range(columns):
                nominal = (col * image.width // columns, row * image.height // rows,
                           (col + 1) * image.width // columns, (row + 1) * image.height // rows)
                x, y, right, bottom = nominal
                crossing = []
                for i, component in enumerate(components):
                    a, b, c, d = component["bbox"]
                    if a < nominal[2] and c > nominal[0] and b < nominal[3] and d > nominal[1]:
                        if a < x or b < y or c > right or d > bottom:
                            crossing.append(i)
                        x, y, right, bottom = min(x, a), min(y, b), max(right, c), max(bottom, d)
                box = (x, y, right, bottom)
                entries.append((image.crop(box), box, {"nominalRect": _rect(nominal),
                               "crossingComponents": crossing, "reviewRequired": bool(crossing)}))
    else:
        raise PipelineError("UNSUPPORTED_EXTRACTION", "지원하지 않는 추출 방식입니다.")
    return [{"rect": _rect(box), "image": crop,
             "sourceToFrameTransform": {"scaleX": 1, "scaleY": 1, "offsetX": -box[0], "offsetY": -box[1]},
             "extractionVersion": "raw-v1", "alphaStats": _stats(crop),
             "warnings": ([{"code": "EXTRACTION_REVIEW_REQUIRED", "message": "성분 경계/작은 조각을 검수해 주세요.", **meta}] if meta.get("reviewRequired") else []), **meta}
            for crop, box, meta in entries]


def suggest_anchor(image):
    alpha = np.asarray(image.convert("RGBA"))[..., 3]
    ys, xs = np.where(alpha >= 16)
    if not len(xs):
        raise PipelineError("ANCHOR_UNMEASURABLE", "alpha≥16인 발 후보가 없습니다.")
    bottom = int(ys.max()) + 1
    height = bottom - int(ys.min())
    band = max(4, _round(height * .12))
    band_x = xs[ys >= bottom - band]
    return {"x": float((int(band_x.min()) + int(band_x.max())) / 2), "y": bottom}


def cutout_image(input_path, output_path, params):
    source, target = Path(input_path), Path(output_path)
    if source.resolve() == target.resolve() or target.exists():
        raise PipelineError("IMMUTABLE_ASSET", "원본 또는 기존 산출물을 덮어쓸 수 없습니다.")
    before = inspect_image(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=".png", dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        if before["alphaStats"]["transparent"] + before["alphaStats"]["partial"] > 0:
            _open(source).save(temporary)
            result = {"skipped": True, "reason": "native-alpha"}
        else:
            try:
                result = _engine("frames.cutout").cutout(source, temporary,
                    key=params.get("key", "auto"), tolerance=_integer(params.get("tolerance", 24), "tolerance", 0, 255))
            except (SystemExit, ValueError) as exc:
                raise PipelineError("CUTOUT_FAILED", str(exc)) from exc
        after = inspect_image(temporary)
        os.link(temporary, target)  # no overwrite, including concurrent publication
        return {**result, "out": str(target), **after, "reviewRequired": not result.get("skipped", False)}
    finally:
        temporary.unlink(missing_ok=True)


def _find(items, key, value, code):
    found = [item for item in items if item.get(key) == value]
    if len(found) != 1:
        raise PipelineError(code, f"{key} 항목을 하나로 확인할 수 없습니다.", {key: value})
    return found[0]


def _point(point, name):
    if not isinstance(point, dict):
        raise PipelineError("INVALID_GEOMETRY", f"{name} 좌표가 필요합니다.")
    return np.array([_number(point.get("x"), name + ".x"), _number(point.get("y"), name + ".y")])


def _canvas_tile(image, origin, edits, cell_size):
    if not edits:
        return image, origin
    ops = {}
    for edit in edits:
        x = _integer(edit.get("x"), "pixel.x", 0, cell_size[0] - 1)
        y = _integer(edit.get("y"), "pixel.y", 0, cell_size[1] - 1)
        color = edit.get("color")
        if not isinstance(color, (list, tuple)) or len(color) != 4:
            raise PipelineError("INVALID_PIXEL_EDIT", "픽셀 색상은 RGBA 4개 값이어야 합니다.")
        color = [_integer(c, "color", 0, 255) for c in color]
        ops[(x, y)] = "#" + "".join(f"{c:02x}" for c in color)
    left = min(origin[0], min(x for x, y in ops))
    top = min(origin[1], min(y for x, y in ops))
    right = max(origin[0] + image.width, max(x for x, y in ops) + 1)
    bottom = max(origin[1] + image.height, max(y for x, y in ops) + 1)
    canvas = Image.new("RGBA", _size(right - left, bottom - top))
    canvas.paste(image, (origin[0] - left, origin[1] - top))
    encoded = {f"{x-left},{y-top}": value for (x, y), value in ops.items()}
    return _engine("curate.curation").apply_pixel_edits(canvas, encoded), (left, top)


def _affine(image, origin, transform, cell_size):
    t = transform or {}
    sx = _number(t.get("scaleX", 1), "scaleX")
    sy = _number(t.get("scaleY", 1), "scaleY")
    if sx <= 0 or sy <= 0:
        raise PipelineError("INVALID_TRANSFORM", "변형 배율은 양수여야 합니다.")
    # Reuse the pinned engine's rotate/shear convention, extending anisotropic
    # scale, flipY, and explicit pivot without its fixed-canvas clipping.
    matrix = _engine("curate.curation").transform_matrix({"scale": 1,
        "rotate": _number(t.get("rotationDeg", 0), "rotationDeg"),
        "shx": _number(t.get("shearX", 0), "shearX"),
        "shy": _number(t.get("shearY", 0), "shearY"), "flipX": False})
    linear = np.array(matrix).reshape(2, 2) @ np.diag([
        -sx if t.get("flipX", False) else sx, -sy if t.get("flipY", False) else sy])
    if abs(np.linalg.det(linear)) < 1e-10:
        raise PipelineError("INVALID_TRANSFORM", "역변환할 수 없는 shear입니다.")
    pivot = _point(t.get("pivot", {"x": cell_size[0] / 2, "y": cell_size[1] / 2}), "pivot")
    offset = np.array([_number(t.get("dx", 0), "dx"), _number(t.get("dy", 0), "dy")])
    shift = pivot + offset - linear @ pivot
    corners = np.array([[0, 0], [image.width, 0], [0, image.height], list(image.size)]) + origin
    bounds = corners @ linear.T + shift
    # Remove floating noise at quarter rotations before outward rounding.
    bounds = np.round(bounds, 10)
    left, top = np.floor(bounds.min(axis=0)).astype(int)
    right, bottom = np.ceil(bounds.max(axis=0)).astype(int)
    inverse = np.linalg.inv(linear)
    translation = inverse @ (np.array([left, top]) - shift) - origin
    coefficients = tuple(np.column_stack([inverse, translation]).ravel())
    result = image.transform(_size(int(right-left), int(bottom-top)), Image.Transform.AFFINE,
                             coefficients, resample=Image.Resampling.NEAREST)
    return result, (int(left), int(top)), linear, shift


def _outline(image, origin, recipe):
    thickness = _integer(recipe.get("thicknessPx", 2), "thicknessPx", 1, 16)
    directions = recipe.get("directions", 8)
    if directions not in (4, 8) or recipe.get("rendererVersion", "outline-v1") != "outline-v1":
        raise PipelineError("UNSUPPORTED_OUTLINE", "지원하지 않는 아웃라인입니다.")
    opacity = _number(recipe.get("opacityPerCopy", .8), "opacityPerCopy")
    color = recipe.get("colorRGBA", [66, 190, 255, 255])
    if not 0 <= opacity <= 1 or not isinstance(color, (list, tuple)) or len(color) != 4:
        raise PipelineError("INVALID_OUTLINE", "아웃라인 색상/불투명도가 잘못되었습니다.")
    color = tuple(_integer(c, "outline.color", 0, 255) for c in color)
    silhouette = Image.new("RGBA", image.size, color)
    alpha = np.floor(np.asarray(image)[..., 3].astype(float) * opacity * color[3] / 255 + .5).astype("uint8")
    silhouette.putalpha(Image.fromarray(alpha))
    result = Image.new("RGBA", _size(image.width + 2 * thickness, image.height + 2 * thickness))
    offsets = [(0, -1), (1, 0), (0, 1), (-1, 0)]
    if directions == 8:
        offsets += [(1, -1), (1, 1), (-1, 1), (-1, -1)]
    for dx, dy in offsets:
        result.alpha_composite(silhouette, (thickness + dx * thickness, thickness + dy * thickness))
    result.alpha_composite(image, (thickness, thickness))
    return result, (origin[0] - thickness, origin[1] - thickness)


def render_occurrence(snapshot, clip, occurrence, asset_path, include_outline=True):
    errors, warnings, stages = [], [], []
    frame = _find(snapshot.get("frames", []), "frameVersionId", occurrence.get("frameVersionId"), "FRAME_MISSING")
    groups = [g for g in snapshot.get("alignmentGroups", []) if frame["frameVersionId"] in g.get("frameVersionIds", [])]
    if len(groups) != 1:
        raise PipelineError("ALIGNMENT_GROUP_MISSING", "프레임의 공통 배율 그룹을 확인해 주세요.")
    group = groups[0]
    alignment = snapshot.get("alignments", {}).get(frame["frameVersionId"])
    if not alignment:
        raise PipelineError("ALIGNMENT_MISSING", "프레임 앵커가 없습니다.")
    asset = _find(snapshot.get("assets", []), "assetId", frame.get("imageAssetId"), "ASSET_MISSING")
    try:
        path = Path(asset_path(asset["assetId"]))
        raw = path.read_bytes()
    except (OSError, KeyError, TypeError) as exc:
        raise PipelineError("ASSET_MISSING", "프레임 이미지 파일이 없습니다.") from exc
    image = _open(io.BytesIO(raw))
    source_hash = _image_hash(image)
    for name, actual in (("sha256", _hash(raw)), ("decodedHash", source_hash)):
        if asset.get(name) and asset[name] != actual:
            errors.append(_error("ASSET_HASH_MISMATCH", "저장된 자산 해시가 다릅니다.", assetId=asset["assetId"], field=name))
    if frame.get("review") != "approved":
        errors.append(_error("FRAME_UNAPPROVED", "프레임 검수가 필요합니다."))
    if alignment.get("approval") != "approved":
        errors.append(_error("ANCHOR_UNAPPROVED", "앵커 승인이 필요합니다."))
    if alignment.get("groupRevisionId") != group.get("groupRevisionId") or alignment.get("frameVersionId") != frame["frameVersionId"]:
        errors.append(_error("STALE_ALIGNMENT", "현재 프레임/그룹에 대한 앵커 승인이 아닙니다."))
    if group.get("referenceRevisionId") and group["referenceRevisionId"] != clip.get("referenceRevisionId"):
        errors.append(_error("STALE_REFERENCE", "정렬 그룹과 동작의 기준이 다릅니다."))
    if alignment.get("imageAssetId", asset["assetId"]) != asset["assetId"] or alignment.get("decodedHash", source_hash) != source_hash:
        errors.append(_error("STALE_ALIGNMENT", "앵커가 승인된 이미지가 변경되었습니다."))
    if group.get("resampler", "nearest") != "nearest" or group.get("roundingVersion", "js-round-v1") != "js-round-v1":
        raise PipelineError("UNSUPPORTED_RENDER_RECIPE", "지원하지 않는 정렬 샘플링입니다.")
    scale = _number(group.get("sharedScale", 1), "sharedScale")
    if scale <= 0:
        raise PipelineError("INVALID_SCALE", "공통 배율은 양수여야 합니다.")
    mode = group.get("mode", "preserve-source-scale")
    if mode not in ("preserve-source-scale", "shared-scale-foot-anchor"):
        raise PipelineError("UNSUPPORTED_ALIGNMENT", "포즈별 자동 fit은 지원하지 않습니다.")
    measurement = group.get("bodyMeasurement")
    if mode == "shared-scale-foot-anchor":
        if not measurement or measurement.get("approved") is not True:
            errors.append(_error("BODY_MEASUREMENT_UNAPPROVED", "몸 landmark 승인이 필요합니다."))
        else:
            body = _number(measurement.get("bottomY"), "bottomY") - _number(measurement.get("topY"), "topY")
            target_height = _number(measurement.get("targetHeight"), "targetHeight")
            if body <= 0 or target_height <= 0 or not math.isclose(scale, target_height / body, rel_tol=1e-9):
                errors.append(_error("STALE_BODY_SCALE", "공통 배율이 승인된 몸 landmark와 일치하지 않습니다."))
    cell = group.get("cell", {})
    width = _integer(cell.get("width", 512), "cell.width", 1)
    height = _integer(cell.get("height", 512), "cell.height", 1)
    edge = _integer(cell.get("edge", 0), "cell.edge", 0, (min(width, height) - 1) // 2)
    target = _point(group.get("targetAnchor"), "targetAnchor")
    contact = alignment.get("contactMode", "grounded")
    if contact not in ("grounded", "airborne"):
        raise PipelineError("INVALID_CONTACT_MODE", "접지 또는 공중 모드가 필요합니다.")
    if contact == "airborne":
        if not alignment.get("rootAnchor"):
            raise PipelineError("ROOT_ANCHOR_REQUIRED", "공중 프레임은 승인된 root anchor가 필요합니다.")
        anchor = _point(alignment["rootAnchor"], "rootAnchor")
    else:
        anchor = _point(alignment.get("sourceAnchor"), "sourceAnchor")
    space = alignment.get("anchorSpace", "crop")
    if space == "raw":
        mapping = frame.get("sourceToFrameTransform", {})
        anchor = anchor * [_number(mapping.get("scaleX", 1), "mapping.scaleX"), _number(mapping.get("scaleY", 1), "mapping.scaleY")] + [_number(mapping.get("offsetX", 0), "mapping.offsetX"), _number(mapping.get("offsetY", 0), "mapping.offsetY")]
    elif space != "crop":
        raise PipelineError("UNSUPPORTED_ANCHOR_SPACE", "raw/crop 앵커 좌표가 필요합니다.")
    authored = _point(alignment.get("authoredOffsetPx", {"x": 0, "y": 0}), "authoredOffsetPx")
    placement = target - scale * anchor + authored
    origin = tuple(_round(float(v)) for v in placement)
    residual = {"x": origin[0] - float(placement[0]), "y": origin[1] - float(placement[1])}
    stages.append({"stage": "raw-crop", "inputHash": source_hash, "outputHash": source_hash,
                   "recipeHash": _hash(_json({"frameVersionId": frame["frameVersionId"], "sourceRect": frame.get("sourceRect"), "mapping": frame.get("sourceToFrameTransform")}))})
    scaled = image.resize(_size(max(1, _round(image.width * scale)), max(1, _round(image.height * scale))), Image.Resampling.NEAREST)
    stages.append({"stage": "shared-scale-anchor", "inputHash": source_hash, "outputHash": _image_hash(scaled), "recipeHash": _hash(_json({"group": group, "alignment": alignment})), "origin": list(origin)})
    edited, origin = _canvas_tile(scaled, origin, occurrence.get("pixelEdits", []), (width, height))
    transformed, origin, linear, shift = _affine(edited, origin, occurrence.get("transform"), (width, height))
    stages.append({"stage": "occurrence", "inputHash": _image_hash(scaled), "outputHash": _image_hash(transformed), "recipeHash": _hash(_json({"transform": occurrence.get("transform", {}), "pixelEdits": occurrence.get("pixelEdits", [])})), "origin": list(origin)})
    rendered_anchor = linear @ (target + authored + np.array([residual["x"], residual["y"]])) + shift
    outline = snapshot.get("outline", {})
    outlined = bool(include_outline and outline.get("enabled") and outline.get("mode", "bake") == "bake")
    if outlined:
        before_outline = _image_hash(transformed)
        transformed, origin = _outline(transformed, origin, outline)
        stages.append({"stage": "outline", "inputHash": before_outline, "outputHash": _image_hash(transformed), "recipeHash": _hash(_json(outline)), "origin": list(origin)})
    support = transformed.getchannel("A").getbbox()
    overflow = {"left": 0, "top": 0, "right": 0, "bottom": 0}
    if not support:
        errors.append(_error("EMPTY_ALPHA", "가시 픽셀이 없는 프레임입니다."))
        bounds = None
    else:
        bounds = (support[0] + origin[0], support[1] + origin[1], support[2] + origin[0], support[3] + origin[1])
        overflow = dict(zip(overflow, [max(0, edge-bounds[0]), max(0, edge-bounds[1]), max(0, bounds[2]-(width-edge)), max(0, bounds[3]-(height-edge))]))
        if any(overflow.values()):
            errors.append(_error("FRAME_OVERFLOW", "alpha>0 픽셀이 safeRect를 벗어납니다.", overflowPx=overflow))
    alpha = np.asarray(image)[..., 3]
    faint = int(np.count_nonzero((alpha > 0) & (alpha < 16)))
    if faint:
        warnings.append(_error("LOW_ALPHA_SUPPORT", "낮은 알파 픽셀을 원본에서 확인해 주세요.", pixelCount=faint))
    canvas = Image.new("RGBA", _size(width, height))
    canvas.paste(transformed, origin)  # preview may clip, but QA above retains unbounded evidence
    canvas = _normalize(canvas)
    stages.append({"stage": "normalize-bake", "inputHash": _image_hash(transformed), "outputHash": _image_hash(canvas), "recipeHash": _hash(b"alpha0-rgb-zero-v1")})
    return canvas, {"frameVersionId": frame["frameVersionId"], "occurrenceId": occurrence.get("occurrenceId"),
        "errors": errors, "warnings": warnings, "residual": residual, "overflowPx": overflow,
        "safeRect": {"x": edge, "y": edge, "width": width-2*edge, "height": height-2*edge},
        "supportBounds": list(bounds) if bounds else None, "sharedScale": scale,
        "anchor": rendered_anchor.tolist(), "contactMode": contact, "outlineBaked": outlined,
        "decodedHash": _image_hash(canvas), "stages": stages}


def _clip_gates(snapshot, clip):
    errors = []
    if not clip.get("occurrences"):
        errors.append(_error("EMPTY_TIMELINE", "빈 타임라인은 출력할 수 없습니다."))
    if clip.get("review") != "approved":
        errors.append(_error("CLIP_UNAPPROVED", "동작 검수가 필요합니다."))
    references = [r for r in snapshot.get("references", []) if r.get("referenceRevisionId") == clip.get("referenceRevisionId")]
    if len(references) != 1 or references[0].get("approval") != "approved":
        errors.append(_error("REFERENCE_UNAPPROVED", "동작에 고정된 승인 기준이 필요합니다."))
    if clip.get("endBehavior", "hold-last") != "hold-last":
        errors.append(_error("UNSUPPORTED_TIMING", "단발 재생은 hold-last만 지원합니다."))
    fps = clip.get("defaultFps", 10)
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 1 <= fps <= 60:
        errors.append(_error("UNSUPPORTED_TIMING", "FPS는 1–60이어야 합니다."))
    ids = set()
    for occurrence in clip.get("occurrences", []):
        oid = occurrence.get("occurrenceId")
        if not oid or oid in ids:
            errors.append(_error("INVALID_OCCURRENCE", "슬롯 ID가 없거나 중복됩니다.", occurrenceId=oid))
        ids.add(oid)
        duration = occurrence.get("durationMs")
        if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 60000:
            errors.append(_error("UNSUPPORTED_TIMING", "확정 durationMs는 1–60000 정수여야 합니다.", occurrenceId=oid))
        mode = occurrence.get("timingMode", "explicit")
        if mode not in ("explicit", "fps"):
            errors.append(_error("UNSUPPORTED_TIMING", "지원하지 않는 timingMode입니다.", occurrenceId=oid))
        elif mode == "fps" and isinstance(fps, (int, float)) and math.isfinite(fps) and 1 <= fps <= 60 and duration != _round(1000 / fps):
            errors.append(_error("STALE_TIMING", "FPS와 저장된 기본 슬롯 시간이 다릅니다.", occurrenceId=oid))
    return [{"clipId": clip.get("clipId"), **error} for error in errors]


def _engine_fingerprint():
    lock_path = ENGINE_ROOT.parent / "engine-lock.json"
    try:
        lock = json.loads(lock_path.read_bytes())
    except (OSError, ValueError) as exc:
        raise PipelineError("ENGINE_UNAVAILABLE", "전용 엔진 pin 기록이 없습니다.") from exc
    if lock.get("engineCommit") != ENGINE_COMMIT:
        raise PipelineError("ENGINE_SOURCE_MISMATCH", "승인된 엔진 source pin이 아닙니다.")
    sources = {}
    for relative in ("sprite_gen/frames/extract.py", "sprite_gen/frames/cutout.py", "sprite_gen/curate/curation.py"):
        sources[relative] = _hash((ENGINE_ROOT / relative).read_bytes())
    return {"engineVersion": lock.get("engineVersion"), "engineSourceHash": _hash(_json(sources)),
            "enginePatchHash": _hash(_json(lock.get("patches", []))),
            "adapterSourceHash": _hash(Path(__file__).read_bytes())}


def _verify_zip(path, entries):
    expected = dict(entries)
    try:
        with zipfile.ZipFile(path) as archive:
            if len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(expected):
                raise ValueError("ZIP member mismatch")
            for name, data in expected.items():
                if archive.read(name) != data:
                    raise ValueError("ZIP content mismatch")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        raise PipelineError("ARTIFACT_HASH_MISMATCH", "ZIP 내부 파일 검증에 실패했습니다.") from exc


def _write_json(path, value):
    path.write_bytes(_json(value) + b"\n")


def _zip(path, entries):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


def _asset_gate(snapshot, asset_ids, asset_path):
    errors = []
    for asset_id in sorted(set(asset_ids)):
        try:
            asset = _find(snapshot.get("assets", []), "assetId", asset_id, "ASSET_MISSING")
            path = Path(asset_path(asset_id))
            raw = path.read_bytes()
            if not asset.get("sha256") or asset["sha256"] != _hash(raw):
                errors.append(_error("ASSET_HASH_MISMATCH", "자산 해시가 없거나 일치하지 않습니다.", assetId=asset_id))
            if asset.get("decodedHash") and asset["decodedHash"] != inspect_image(path)["decodedHash"]:
                errors.append(_error("ASSET_HASH_MISMATCH", "자산 픽셀 해시가 다릅니다.", assetId=asset_id))
        except (PipelineError, OSError, KeyError, TypeError):
            errors.append(_error("ASSET_MISSING", "필수 원본/기준 이미지가 없습니다.", assetId=asset_id))
    return errors


def build_bundle(snapshot, clip_ids, asset_path, output_dir, export_id, strict=True, outline_mode="bake"):
    """Build once in a private staging directory, verify, then atomically publish.

    output_dir is the final per-export directory (absent or empty). No existing
    export can be overwritten. Only the selected clips participate in gates.
    A non-strict bake is explicitly needs_review and is never a verified export.
    """
    locked = copy.deepcopy(snapshot)
    destination = Path(output_dir)
    if destination.is_symlink() or (destination.exists() and (not destination.is_dir() or any(destination.iterdir()))):
        raise PipelineError("IMMUTABLE_EXPORT", "기존 출력은 덮어쓸 수 없습니다.")
    if locked.get("schemaVersion", 1) != 1:
        raise PipelineError("UNSUPPORTED_SCHEMA", "지원하지 않는 프로젝트 schemaVersion입니다.")
    if outline_mode not in ("bake", "preview-only"):
        raise PipelineError("UNSUPPORTED_OUTLINE", "출력 outlineMode가 잘못되었습니다.")
    if not clip_ids:
        raise PipelineError("EMPTY_TIMELINE", "출력할 동작을 선택해 주세요.")
    if len(set(clip_ids)) != len(clip_ids):
        raise PipelineError("INVALID_CLIP_SELECTION", "같은 동작이 중복 선택되었습니다.")
    clips = [_find(locked.get("clips", []), "clipId", cid, "CLIP_MISSING") for cid in clip_ids]
    errors = []
    for field in ("savedRevision", "inputRevision", "engineRevision"):
        if field in locked and locked[field] != locked.get("revision"):
            errors.append(_error("STALE_SAVE", "저장/실행 revision이 일치하지 않습니다.", field=field))
    if locked.get("dirty") or locked.get("savePending"):
        errors.append(_error("STALE_SAVE", "저장 완료 전 출력할 수 없습니다."))
    reference_ids = {c.get("referenceRevisionId") for c in clips}
    frame_ids = {o.get("frameVersionId") for c in clips for o in c.get("occurrences", [])}
    source_ids = []
    for frame in locked.get("frames", []):
        if frame.get("frameVersionId") in frame_ids:
            source_ids.extend([frame.get("rawAssetId"), frame.get("imageAssetId")])
    for reference in locked.get("references", []):
        if reference.get("referenceRevisionId") in reference_ids:
            source_ids.extend([reference.get("identityAssetId"), *reference.get("styleAssetIds", []), *reference.get("poseAssetIds", [])])
    # Retain raw provider/upload ancestry beyond intermediate cutout assets.
    ancestry = list(source_ids)
    seen_assets = set(source_ids)
    while ancestry:
        aid = ancestry.pop()
        source = next((a for a in locked.get("assets", []) if a["assetId"] == aid), None)
        parent = (source or {}).get("provenance", {}).get("parentAssetId")
        if parent and parent not in seen_assets:
            seen_assets.add(parent); source_ids.append(parent); ancestry.append(parent)
    if any(a is None for a in source_ids):
        errors.append(_error("ASSET_MISSING", "원본 또는 기준 이미지 연결이 누락되었습니다."))
    errors.extend(_asset_gate(locked, [a for a in source_ids if a is not None], asset_path))
    for clip in clips:
        errors.extend(_clip_gates(locked, clip))
    # Empty selection and invalid timing cannot produce a playable preview either.
    structural = [e for e in errors if e["code"] in {"EMPTY_TIMELINE", "UNSUPPORTED_TIMING", "STALE_TIMING", "INVALID_OCCURRENCE"}]
    if structural or (strict and errors):
        first = (structural or errors)[0]
        raise PipelineError(first["code"], first["message"], {"errors": errors})

    rendered, frame_qa, runtime_clips, dedup = [], [], [], {}
    for clip in clips:
        timeline = []
        for occurrence in clip["occurrences"]:
            bitmap, qa = render_occurrence(locked, clip, occurrence, asset_path, include_outline=outline_mode == "bake")
            frame_qa.append({"clipId": clip["clipId"], **qa})
            errors.extend({"clipId": clip["clipId"], "occurrenceId": occurrence["occurrenceId"], **e} for e in qa["errors"])
            # Pixel sharing never merges slots, anchors, frame lineage or timing.
            key = (bitmap.size, qa["decodedHash"])
            if key not in dedup:
                rid = "rendered-" + str(len(rendered) + 1)
                dedup[key] = rid
                rendered.append({"id": rid, "bitmap": bitmap, "frameVersionId": occurrence["frameVersionId"],
                                 "decodedHash": qa["decodedHash"], "anchor": qa["anchor"]})
            timeline.append({"id": occurrence["occurrenceId"], "occurrenceId": occurrence["occurrenceId"],
                "frameVersionId": occurrence["frameVersionId"], "renderedFrameId": dedup[key],
                "durationMs": occurrence["durationMs"], "timingMode": occurrence.get("timingMode", "explicit"),
                "anchor": qa["anchor"], "contactMode": qa["contactMode"]})
        runtime_clips.append({"id": clip["clipId"], "clipId": clip["clipId"], "clipRevisionId": clip.get("clipRevisionId"),
            "name": clip.get("name", ""), "stateId": clip.get("stateId"), "facing": clip.get("facing", "right"),
            "referenceRevisionId": clip.get("referenceRevisionId"), "loop": bool(clip.get("loop", True)),
            "endBehavior": clip.get("endBehavior", "hold-last"), "defaultFps": clip.get("defaultFps", 10),
            "durationMs": sum(o["durationMs"] for o in timeline), "occurrences": timeline})
    if strict and errors:
        raise PipelineError(errors[0]["code"], errors[0]["message"], {"errors": errors, "frames": frame_qa})
    qa = {"status": "verified" if strict and not errors else "needs_review", "errors": errors,
          "warnings": [w for f in frame_qa for w in f["warnings"]], "frames": frame_qa,
          "projectRevision": locked.get("revision"), "fullRGBAParity": False}
    effective_outline = locked.get("outline", {})
    if not (outline_mode == "bake" and effective_outline.get("enabled") and effective_outline.get("mode", "bake") == "bake"):
        effective_outline = {"enabled": False}
    fingerprint = _engine_fingerprint()
    recipe = {"adapterVersion": ADAPTER_VERSION, "engineCommit": ENGINE_COMMIT, **fingerprint,
              "frames": [{"clipId": f["clipId"], "occurrenceId": f["occurrenceId"], "stages": f["stages"]} for f in frame_qa],
              "clips": runtime_clips, "outline": effective_outline, "alphaNormalization": "alpha0-rgb-zero-v1"}
    recipe_hash = _hash(_json(recipe))
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".bake-", dir=destination.parent))
    try:
        # Deterministic shelf packing; full cells retained, no alpha crop or fit.
        max_width = max(item["bitmap"].width for item in rendered)
        total_area = sum(item["bitmap"].width * item["bitmap"].height for item in rendered)
        shelf_width = max(max_width, min(8192, math.ceil(math.sqrt(total_area))))
        x = y = row_height = used_width = 0
        for item in rendered:
            im = item["bitmap"]
            if x and x + im.width > shelf_width:
                x, y, row_height = 0, y + row_height, 0
            item["rect"] = {"x": x, "y": y, "width": im.width, "height": im.height}
            x += im.width
            row_height = max(row_height, im.height)
            used_width = max(used_width, x)
        atlas = Image.new("RGBA", _size(used_width, y + row_height))
        for item in rendered:
            atlas.paste(item["bitmap"], (item["rect"]["x"], item["rect"]["y"]))
        atlas.save(staging / "atlas.png")
        decoded_atlas = _open(staging / "atlas.png")
        png_data, frames = {}, []
        for item in rendered:
            rect = item["rect"]
            recrop = decoded_atlas.crop((rect["x"], rect["y"], rect["x"]+rect["width"], rect["y"]+rect["height"]))
            stream = io.BytesIO()
            recrop.save(stream, format="PNG")
            data = stream.getvalue()
            if _open(io.BytesIO(data)).tobytes() != item["bitmap"].tobytes():
                raise PipelineError("RGBA_PARITY_FAILED", "atlas와 PNG의 전체 RGBA가 다릅니다.")
            png_data[item["id"]] = data
            frames.append({key: value for key, value in item.items() if key != "bitmap"} | {"png": f"frames/{item['id']}.png", "pngSha256": _hash(data)})
        qa["fullRGBAParity"] = True
        qa["recipeHash"] = recipe_hash
        manifest = {"schemaVersion": 1, "version": 1, "exportId": export_id, "projectId": locked.get("projectId"),
            "projectRevision": locked.get("revision"), "clipRevisionIds": [c.get("clipRevisionId") for c in clips],
            "referenceRevisionIds": sorted(r for r in reference_ids if r is not None),
            "engineCommit": ENGINE_COMMIT, "adapterVersion": ADAPTER_VERSION, **fingerprint,
            "recipeHash": recipe_hash, "renderRecipeHash": recipe_hash, "qaStatus": qa["status"],
            "coordinateConvention": "top-left; right/bottom exclusive; anchor in baked cell; transforms already baked",
            "alphaNormalization": "alpha0-rgb-zero-v1", "outlineMode": "bake" if effective_outline.get("enabled") else "preview-only",
            "outline": effective_outline,
            "sourceAssets": [{"assetId": a["assetId"], "sha256": a.get("sha256"), "decodedHash": a.get("decodedHash"), "provenance": a.get("provenance", {})} for a in locked.get("assets", []) if a["assetId"] in source_ids],
            "frameSources": [{k: f.get(k) for k in ("frameId", "frameVersionId", "parentFrameVersionId", "generationVersionId", "rawAssetId", "imageAssetId", "sourceRect", "sourceToFrameTransform", "sourceVideoId", "sourceFrameIndex", "sourceTimeMs", "interpolated", "interpolation", "sourceProcessing")} for f in locked.get("frames", []) if f["frameVersionId"] in frame_ids],
            "sourceVideos": [{k: v.get(k) for k in ("videoId", "sha256", "originalFilename", "width", "height", "fps", "frameCount", "durationMs", "provenance")} for v in locked.get("videos", []) if any(f.get("sourceVideoId") == v["videoId"] and f["frameVersionId"] in frame_ids for f in locked.get("frames", []))],
            "atlas": {"file": "atlas.png", "width": atlas.width, "height": atlas.height, "sha256": _hash((staging / "atlas.png").read_bytes())},
            "frames": frames, "clips": runtime_clips}
        sequence = {"schemaVersion": 1, "exportId": export_id, "recipeHash": recipe_hash,
                    "projectRevision": locked.get("revision"), "clips": []}
        sequence_entries = [(f["png"], png_data[f["id"]]) for f in frames]
        ase_frames, tags = [], []
        frame_map = {f["id"]: f for f in frames}
        for ci, clip in enumerate(runtime_clips):
            slots = []
            start = len(ase_frames)
            for oi, occurrence in enumerate(clip["occurrences"]):
                frame = frame_map[occurrence["renderedFrameId"]]
                filename = f"sequences/{ci:03d}/{oi:05d}.png"
                sequence_entries.append((filename, png_data[frame["id"]]))
                slots.append({**occurrence, "file": filename, "sha256": frame["pngSha256"]})
                r = frame["rect"]
                ase_frames.append({"filename": filename, "frame": {"x": r["x"], "y": r["y"], "w": r["width"], "h": r["height"]},
                    "rotated": False, "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": r["width"], "h": r["height"]},
                    "sourceSize": {"w": r["width"], "h": r["height"]}, "duration": occurrence["durationMs"]})
            sequence["clips"].append({**clip, "occurrences": slots})
            tags.append({"name": clip["name"] or clip["id"], "from": start, "to": len(ase_frames)-1, "direction": "forward"})
        _zip(staging / "pngs.zip", sequence_entries + [("manifest.json", _json(sequence))])
        aseprite = {"frames": ase_frames, "meta": {"app": "sprite-editor", "version": ADAPTER_VERSION, "image": "atlas.png",
            "format": "RGBA8888", "size": {"w": atlas.width, "h": atlas.height}, "scale": "1", "frameTags": tags,
            "runtime": "runtime.json", "note": "Aseprite-compatible JSON; loop, endBehavior and anchors are in runtime.json"}}
        _write_json(staging / "aseprite.json", aseprite)
        try:
            animation_manifest, animation_entries = build_animation_exports(runtime_clips, png_data,
                export_id=export_id, recipe_hash=recipe_hash, project_revision=locked.get("revision"))
        except AnimationExportError as exc:
            raise PipelineError("ANIMATION_PARITY_FAILED", str(exc)) from exc
        _write_json(staging / "animation-manifest.json", animation_manifest)
        animation_entries.append(("manifest.json", (staging / "animation-manifest.json").read_bytes()))
        _zip(staging / "animations.zip", animation_entries)
        _verify_zip(staging / "animations.zip", animation_entries)
        manifest["animationExports"] = {"version": animation_manifest["version"],
            "archive": "animations.zip", "manifest": "animation-manifest.json",
            "warnings": animation_manifest["warnings"]}
        qa["warnings"].extend(animation_manifest["warnings"])
        _write_json(staging / "qa.json", qa)
        # runtime cannot contain its own digest (or the containing ZIP digest).
        manifest["files"] = [{"name": name, "sha256": _hash((staging/name).read_bytes())} for name in ("atlas.png", "pngs.zip", "aseprite.json", "qa.json", "animations.zip", "animation-manifest.json")]
        _write_json(staging / "runtime.json", manifest)
        names = ["atlas.png", "pngs.zip", "runtime.json", "aseprite.json", "qa.json", "animations.zip", "animation-manifest.json"]
        bundle_entries = [(name, (staging/name).read_bytes()) for name in names] + [(f["png"], png_data[f["id"]]) for f in frames]
        _zip(staging / "bundle.zip", bundle_entries)
        names.append("bundle.zip")
        _verify_zip(staging / "pngs.zip", sequence_entries + [("manifest.json", _json(sequence))])
        _verify_zip(staging / "bundle.zip", bundle_entries)
        for item in manifest["files"]:
            if _hash((staging/item["name"]).read_bytes()) != item["sha256"]:
                raise PipelineError("ARTIFACT_HASH_MISMATCH", "출력 파일 해시가 다릅니다.")
        file_hashes = [{"name": name, "sha256": _hash((staging/name).read_bytes())} for name in names]
        # On POSIX rename replaces only an empty directory. Existing exports,
        # including concurrently completed ones, therefore remain immutable.
        try:
            staging.rename(destination)
        except OSError as exc:
            raise PipelineError("IMMUTABLE_EXPORT", "출력 위치를 다른 작업이 사용 중입니다.") from exc
        return {"manifest": manifest, "qa": qa, "files": names, "fileHashes": file_hashes,
                "status": "succeeded" if qa["status"] == "verified" else "needs_review"}
    finally:
        if staging.exists():
            shutil.rmtree(staging)
