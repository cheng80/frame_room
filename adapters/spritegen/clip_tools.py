"""Local, non-destructive tools for saved canonical animation cells."""
from __future__ import annotations

import colorsys
import math
import re

import numpy as np
from PIL import Image

from services.api import store as s

VERSION = "clip-tools-v1"
MAX_PIXELS = 16_777_216
PARTS = ("wrist", "hand", "head", "ankle", "body")
VIEWS = ("side", "front", "back", "front_diagonal", "back_diagonal")


def _number(value, low, high, label, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise s.AppError("CLIP_TOOL_SETTING", f"{label}에 유한한 숫자를 입력하세요.")
    if not low <= value <= high or integer and int(value) != value:
        raise s.AppError("CLIP_TOOL_SETTING", f"{label} 범위는 {low}~{high}입니다.")
    return int(value) if integer else float(value)


def _find(rows, field, value, message):
    found = next((r for r in rows if r.get(field) == value), None)
    if found is None:
        raise s.AppError("CLIP_TOOL_SOURCE", message)
    return found


def clip_shape(snapshot, params):
    clip = _find(snapshot.get("clips", []), "clipId", params.get("clipId"), "처리할 동작을 선택하세요.")
    if params.get("clipRevisionId") != clip.get("clipRevisionId"):
        raise s.AppError("CLIP_TOOL_STALE", "동작이 변경되었습니다. 현재 동작으로 다시 시도하세요.", 409)
    slots = clip.get("occurrences", [])
    if not 1 <= len(slots) <= 64:
        raise s.AppError("CLIP_TOOL_LIMIT", "동작 도구는 1~64슬롯을 지원합니다.")
    duration = sum(_number(o.get("durationMs"), 1, 60000, "슬롯 시간", integer=True) for o in slots)
    if duration > 60000:
        raise s.AppError("CLIP_TOOL_LIMIT", "동작은 총 60초 이하여야 합니다.")
    sizes = set()
    for slot in slots:
        _find(snapshot.get("frames", []), "frameVersionId", slot.get("frameVersionId"), "동작의 후보를 찾을 수 없습니다.")
        groups = [g for g in snapshot.get("alignmentGroups", []) if slot["frameVersionId"] in g.get("frameVersionIds", [])]
        if len(groups) != 1:
            raise s.AppError("CLIP_TOOL_SOURCE", "후보의 크기·발 정렬 그룹을 확인하세요.")
        cell = groups[0].get("cell", {})
        sizes.add((_number(cell.get("width"), 2, 1024, "셀 너비", integer=True),
                   _number(cell.get("height"), 2, 1024, "셀 높이", integer=True)))
    if len(sizes) != 1:
        raise s.AppError("CLIP_TOOL_CELL", "모든 슬롯의 출력 셀 크기를 동일하게 맞춰 주세요.")
    width, height = sizes.pop()
    if width * height * len(slots) > MAX_PIXELS:
        raise s.AppError("CLIP_TOOL_LIMIT", "동작 도구의 전체 픽셀 한도를 넘었습니다. 셀 크기나 슬롯 수를 줄이세요.")
    return clip, width, height


def _marker(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise s.AppError("CLIP_TOOL_MARKER", "표식 색을 #RRGGBB 형식으로 지정하세요.")
    rgb = tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    if colorsys.rgb_to_hsv(*(c / 255 for c in rgb))[1] < .2:
        raise s.AppError("CLIP_TOOL_MARKER", "회색·흰색·검정은 구분하기 어렵습니다. 장비에만 있는 채도 있는 색을 선택하세요.")
    return rgb


def validate_params(snapshot, operation, params):
    if not isinstance(params, dict):
        raise s.AppError("CLIP_TOOL_SETTING", "동작 도구 설정을 확인하세요.")
    clip, width, height = clip_shape(snapshot, params)
    out = {"clipId": clip["clipId"], "clipRevisionId": clip["clipRevisionId"]}
    if operation == "preview_follow":
        allowed = set(out) | {"region", "gain", "freq", "damping", "onFold"}
        if not clip.get("loop") or len(clip["occurrences"]) < 4:
            raise s.AppError("CLIP_TOOL_LOOP", "부위 흔들림은 4~64슬롯의 반복 동작에 적용할 수 있습니다.")
        region = params.get("region")
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            raise s.AppError("CLIP_TOOL_REGION", "첫 프레임에서 타원 영역을 지정하세요.")
        cx, cy, rx, ry = [_number(v, 0, max(width, height), "타원 좌표") for v in region]
        if rx <= 0 or ry <= 0 or cx - rx < 0 or cy - ry < 0 or cx + rx > width or cy + ry > height:
            raise s.AppError("CLIP_TOOL_REGION", "양수 반지름의 타원 전체가 출력 셀 안에 있어야 합니다.")
        out.update(region=[cx, cy, rx, ry], gain=_number(params.get("gain", 2.5), 0, 8, "강도"),
                   freq=_number(params.get("freq", 2.4), .2, 12, "탄성 빈도"),
                   damping=_number(params.get("damping", .6), .05, 4, "감쇠"), onFold=params.get("onFold", "lower"))
        if out["onFold"] not in ("lower", "refuse"):
            raise s.AppError("CLIP_TOOL_SETTING", "과도한 변형의 처리 방법을 확인하세요.")
    elif operation == "check_handed":
        allowed = set(out) | {"item", "side", "part", "direction", "facing", "marker", "referenceAssetId"}
        item = params.get("item")
        if not isinstance(item, str) or not 1 <= len(item.strip()) <= 160:
            raise s.AppError("CLIP_TOOL_SETTING", "검사할 장비 이름을 1~160자로 입력하세요.")
        out["item"] = item.strip()
        for field, choices in (("side", ("left", "right")), ("part", PARTS), ("direction", VIEWS), ("facing", ("left", "right"))):
            if params.get(field) not in choices:
                raise s.AppError("CLIP_TOOL_SETTING", "장비의 위치와 캐릭터 방향을 확인하세요.")
            out[field] = params[field]
        _marker(params.get("marker"))
        out["marker"] = params["marker"].lower()
        if params.get("referenceAssetId"):
            ref = _find(snapshot.get("assets", []), "assetId", params["referenceAssetId"], "같은 프로젝트의 기준 그림을 선택하세요.")
            if ref.get("width", 0) * ref.get("height", 0) > MAX_PIXELS:
                raise s.AppError("CLIP_TOOL_LIMIT", "기준 그림의 픽셀 한도를 넘었습니다.")
            if not ref.get("alphaStats", {}).get("transparent"):
                raise s.AppError("CLIP_TOOL_REFERENCE", "배경이 투명하고 장비 표식이 온전히 보이는 기준 그림을 선택하세요.")
            out["referenceAssetId"] = ref["assetId"]
        # The motion state is read from the saved clip, never trusted from a UI override.
        out["state"] = clip.get("stateId") or None
    else:
        raise s.AppError("OPERATION_UNSUPPORTED", "지원하지 않는 동작 도구입니다.")
    if set(params) - allowed:
        raise s.AppError("CLIP_TOOL_SETTING", "알 수 없는 동작 도구 설정입니다.")
    return out


def render_clip(snapshot, params, asset_path):
    from alignment.pipeline import render_occurrence
    clip, width, height = clip_shape(snapshot, params)
    cells, anchors, fids, aids = [], [], [], []
    pending = {"FRAME_UNAPPROVED", "ANCHOR_UNAPPROVED", "BODY_MEASUREMENT_UNAPPROVED"}
    for slot in clip["occurrences"]:
        image, qa = render_occurrence(snapshot, clip, slot, asset_path, include_outline=False)
        errors = [e for e in qa["errors"] if e.get("code") not in pending]
        if errors:
            raise s.AppError("CLIP_TOOL_RENDER", "원본 동작의 잘림·자료·정렬 오류를 먼저 해결하세요.", 422, {"errors": errors})
        cells.append(image)
        anchors.append(dict(zip(("x", "y"), qa["anchor"])))
        fids.append(slot["frameVersionId"])
        aids.append(next(f["imageAssetId"] for f in snapshot["frames"] if f["frameVersionId"] == slot["frameVersionId"]))
    durations = [o["durationMs"] for o in clip["occurrences"]]
    source = {"projectId": snapshot["projectId"], "projectRevision": snapshot["revision"], "clipId": clip["clipId"],
              "clipRevisionId": clip["clipRevisionId"], "occurrenceIds": [o["occurrenceId"] for o in clip["occurrences"]],
              "frameVersionIds": fids, "sourceAssetIds": aids, "anchors": anchors,
              "cell": {"width": width, "height": height}, "loop": bool(clip.get("loop")),
              "stateId": clip.get("stateId"), "referenceRevisionId": clip.get("referenceRevisionId"),
              "defaultFps": clip.get("defaultFps", 10), "durationMs": sum(durations)}
    return cells, durations, source


def _response(motion, durations, *, freq, zeta, gain):
    from sprite_gen.video.follow import follow_offsets
    total = sum(durations) / 1000
    if len(set(durations)) == 1:
        return follow_offsets(motion, len(motion) / total, freq=freq, zeta=zeta, gain=gain)
    # Interpolate the periodic body signal on time, not on uneven slot indices.
    times = np.cumsum([0, *durations[:-1]], dtype=float) / 1000
    count = max(64, len(durations) * 8)
    even = np.arange(count) * total / count
    sampled = np.interp(even, np.r_[times, total], np.r_[motion, motion[0]])
    offsets = follow_offsets(sampled, count / total, freq=freq, zeta=zeta, gain=gain)
    return np.interp(times, np.r_[even, total], np.r_[offsets, offsets[0]])


def follow_frames(cells, durations, params):
    from sprite_gen.video import follow
    try:
        rows, cols, _ = follow.body_motion(cells)
    except ValueError as exc:
        raise s.AppError("CLIP_TOOL_BODY", "몸 움직임을 측정할 불투명한 그림이 필요합니다.") from exc
    region = tuple(params["region"])
    cx, cy, rx, ry = region
    width, height = cells[0].size
    shifts = np.column_stack((cols - cols[0], rows - rows[0]))
    if any(cx + x - rx < 0 or cy + y - ry < 0 or cx + x + rx > width or cy + y + ry > height for x, y in shifts):
        raise s.AppError("CLIP_TOOL_REGION", "움직이는 타원이 셀 밖으로 나갑니다. 영역을 줄이거나 위치를 옮겨 주세요.")
    settings = dict(freq=params["freq"], zeta=params["damping"], gain=1.0)
    dx = _response(cols, durations, **settings)
    dy = _response(rows, durations, **settings)
    per_gain = float(np.max(np.hypot(dx, dy)))
    gain = requested = params["gain"]
    radius = min(rx, ry)
    if follow.fold_ratio(per_gain * gain, radius) >= 1:
        if params["onFold"] == "refuse":
            raise s.AppError("CLIP_TOOL_FOLD", "영역이 접힐 정도로 강도가 큽니다. 강도를 낮추거나 영역을 넓혀 주세요.")
        gain = follow.lowered_gain(gain, per_gain, radius)
        if gain < follow.GAIN_MEASURED:
            raise s.AppError("CLIP_TOOL_FOLD", "강도를 낮춰도 영역이 너무 작습니다. 영역을 넓혀 주세요.")
    dx, dy = dx * gain, dy * gain
    # Gain zero and a rigid body must be an exact identity, including invisible RGB.
    out = [cell.copy() if abs(x) + abs(y) < 1e-10 else follow.move_regions(cell, [region], tuple(shift), (float(x), float(y)))
           for cell, shift, x, y in zip(cells, shifts, dx, dy)]
    report = {"gainRequested": requested, "gainApplied": gain, "foldLimited": gain != requested,
              "reachPx": round(float(np.max(np.hypot(dx, dy))), 5), "bodyMotionPx": [round(float(np.ptp(cols)), 5), round(float(np.ptp(rows)), 5)],
              "offsets": [{"x": round(float(x), 6), "y": round(float(y), 6)} for x, y in zip(dx, dy)],
              "regionShifts": [{"x": float(x), "y": float(y)} for x, y in shifts],
              "unchanged": all(a.tobytes() == b.tobytes() for a, b in zip(cells, out)),
              "timingMethod": "uniform" if len(set(durations)) == 1 else "time-weighted-periodic",
              "durationMs": sum(durations), "frameCount": len(cells)}
    return out, report


def _reason(text):
    if "places" in text:
        return "장비 표식이 두 곳 이상에서 보입니다."
    if "at or behind" in text:
        return "먼쪽 손의 표식이 몸 뒤나 가운데에 나타납니다."
    if "in full view" in text:
        return "먼쪽 장비 표식이 기준보다 크게 드러납니다."
    if "expected" in text:
        return "장비 표식이 지정한 쪽의 반대편에 보입니다."
    return "표식 위치를 직접 확인해 주세요."


def check_frames(cells, params, references=None):
    from sprite_gen.gen.handedness import Handed
    from sprite_gen.qa import handed
    try:
        result = handed.check(cells, item=Handed(params["item"], params["side"], params["part"]),
                              view=params["direction"], facing=params["facing"], marker=_marker(params["marker"]),
                              references=references or [], state=params.get("state"))
    except (ValueError, SystemExit) as exc:
        raise s.AppError("CLIP_TOOL_MARKER", "표식을 판정할 수 없습니다. 불투명한 캐릭터와 기준 그림의 표식 색을 확인하세요.") from exc
    suspects = {row["frame"]: [_reason(why) for why in row["why"]] for row in result["fails"]}
    shown = result["frames_shown"]
    for key in ("near_shown", "far_shown"):
        if result["rules"].get(key, {}).get("ok") is False and shown:
            for index, row in enumerate(result["per_frame"]):
                if not row["blobs"]:
                    suspects.setdefault(index, []).append("장비 표식이 보이는 프레임이 부족합니다.")
    unchecked = []
    if not shown:
        unchecked.append("표식을 찾지 못했습니다. 장비에만 있는 색인지 확인하세요.")
    if any(rule.get("checked") is False for rule in result["rules"].values() if isinstance(rule, dict)):
        unchecked.append("측면의 장비 크기 또는 노출 빈도는 기준 그림·동작 정보가 부족해 일부 판정하지 못했습니다.")
    verdict = "inconclusive" if not shown else "suspect" if not result["ok"] else "inconclusive" if unchecked else "clear"
    return {"verdict": verdict, "framesShown": shown, "frameCount": len(cells),
            "suspectFrames": [{"index": index, "reasons": list(dict.fromkeys(reasons))} for index, reasons in sorted(suspects.items())],
            "unchecked": unchecked, "engineReport": result}
