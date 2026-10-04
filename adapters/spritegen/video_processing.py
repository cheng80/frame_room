"""Local video processing; never submits a generation or imports account state.

The caller owns media validation, jobs, DB imports and final body/cell fitting.
Paths in frames/previewPath are absolute; files are relative to ``work``.
raw/keyed PNGs retain the complete source canvas. ``anchor`` and standingHeight
are measured once on source frame zero (not the first selected pose).

Extraction caches depend on the clip/key/reference, not the selected range or
output cell settings. New/failed attempts get new directories; extraction must
never receive a directory containing an earlier attempt's raw frames.
"""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageSequence

ENGINE_ROOT = Path(__file__).resolve().parents[2] / "engine" / "sprite-gen"
VERSION = "video-processing-v3"
STATES = ("idle", "walk", "run", "jump", "attack", "dance", "wave", "cheer")
DIRECTIONS = ("side", "front", "back", "front_diagonal", "back_diagonal")
KEYS = ("auto", "green", "magenta", "cyan", "white")
RIFE_ROOT = ENGINE_ROOT.parents[1] / ".data" / "tools" / "rife"


class VideoProcessingError(Exception):
    def __init__(self, code: str, message: str, payload: dict | None = None):
        super().__init__(message)
        self.code, self.message = code, message
        self.payload = self.details = payload or {}
        self.retryable = False  # Never interpret a local refusal as a generation retry.


def _engine(module: str):
    # Same source guard as alignment.pipeline; no shared skill import/fallback.
    for name, loaded in list(sys.modules.items()):
        if name == "sprite_gen" or name.startswith("sprite_gen."):
            origin = getattr(loaded, "__file__", None)
            if origin and not Path(origin).resolve().is_relative_to(ENGINE_ROOT.resolve()):
                raise VideoProcessingError("VIDEO_ENGINE_MISMATCH", "프로젝트 전용 엔진이 필요합니다.")
    if not (ENGINE_ROOT / "sprite_gen").is_dir():
        raise VideoProcessingError("VIDEO_ENGINE_UNAVAILABLE", "프로젝트 전용 엔진이 없습니다.")
    if str(ENGINE_ROOT) not in sys.path:
        sys.path.insert(0, str(ENGINE_ROOT))
    return importlib.import_module("sprite_gen." + module)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _finite(value):
    # Engine diagnostics can include inf for an entirely motionless clip.
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


def _encoded(value) -> bytes:
    return json.dumps(_finite(value), ensure_ascii=False, sort_keys=True,
                      allow_nan=False, indent=2).encode("utf-8")


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replacing our checkpoint is atomic even if the worker is interrupted.
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        pending = Path(stream.name)
        stream.write(_encoded(value))
        stream.flush()
        os.fsync(stream.fileno())
    pending.replace(path)


def _choice(params: dict, name: str, choices, default):
    value = params.get(name, default)
    if value not in choices:
        raise VideoProcessingError("VIDEO_INVALID_PARAMS", f"{name} 설정이 올바르지 않습니다.",
                                   {"field": name, "allowed": list(choices)})
    return value


def _integer(value, name: str, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise VideoProcessingError("VIDEO_INVALID_PARAMS", f"{name}: {lo}–{hi} 정수가 필요합니다.",
                                   {"field": name})
    return value


def _round(value: float) -> int:
    return math.floor(value + 0.5)


def rife_interpolator():
    """Locate the project install first; never install or call a remote service."""
    engine = _engine("video.rife")
    binary = engine.installed_binary(RIFE_ROOT)
    model = binary.parent / engine.MODEL
    if binary.is_file():
        if not os.access(binary, os.X_OK) or not all((model / name).is_file() for name in ("flownet.param", "flownet.bin")):
            raise engine.RifeNotInstalled("프로젝트 RIFE 실행 파일 또는 모델이 불완전합니다.")
        return engine.Rife(binary=binary.resolve(), model=model.resolve())
    return engine.Rife()


def rife_capability() -> dict:
    """Read-only installation check, not a claim that the current job was repaired."""
    engine = _engine("video.rife")
    try:
        located = rife_interpolator()
    except engine.RifeNotInstalled as exc:
        return {"available": False, "reason": str(exc), "release": engine.RELEASE, "model": engine.MODEL}
    return {"available": True, "release": engine.RELEASE, "model": engine.MODEL,
            "binary": str(located.binary), "modelPath": str(located.model), "localOnly": True}


def prepare_still(source: Path, dest: Path, params: dict) -> dict:
    """Prepare a >=512px nearest-neighbour still and return its effective key.

    Alpha input is composited onto magenta, never converted directly to RGB.
    Opaque flat inputs use the engine's canvas normalization and cutout, retaining
    their chroma family (white becomes magenta after matting). The source and an
    existing different destination are never overwritten. Jump/attack get the
    engine's extra head/weapon room around the 512px base. Returns a sidecar with
    the source hash, crop, scale, offset and engine normalization statistics.
    """
    source, dest = Path(source).expanduser().resolve(), Path(dest).expanduser().resolve()
    key = _choice(params, "key", KEYS, "auto")
    state = _choice(params, "state", STATES, "walk")
    facing = _choice(params, "facing", ("right", "left"), "right")
    if source in (dest, dest.with_name(dest.name + ".prepare.json")):
        raise VideoProcessingError("VIDEO_SOURCE_OVERWRITE", "준비 이미지는 원본과 다른 경로여야 합니다.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        digest = _sha(source)
        with Image.open(source) as original:
            rgba = original.convert("RGBA")
        transparent = rgba.getchannel("A").getextrema()[0] < 255
        stats = {"sourceSize": list(rgba.size), "sourceHadTransparency": transparent}
        output_key = "magenta"
        if not transparent:
            canvas, cutout = _engine("video.canvas"), _engine("frames.cutout")
            corner = canvas.corner_key(rgba)
            detected = cutout._detect_key_kind(corner)
            chosen = detected if key == "auto" else key
            if chosen != detected:
                raise VideoProcessingError("VIDEO_KEY_MISMATCH", "그림 모서리와 지정한 배경 키가 다릅니다.",
                                           {"detectedKey": detected, "requestedKey": key})
            if chosen == "white" and min(corner) < cutout.CORNER_MIN_BRIGHT:
                raise VideoProcessingError("VIDEO_BACKGROUND_UNSUPPORTED", "밝은 단색 또는 크로마 키 배경이 필요합니다.")
            if chosen in cutout.KEY_TARGETS:
                normalized, normalization = canvas.normalize_key(rgba, chosen)
                output_key = chosen
            else:
                normalized, normalization = rgba, {"key": "white", "normalized_px": 0}
            with tempfile.TemporaryDirectory(prefix="still-", dir=dest.parent) as scratch:
                intermediate, keyed = Path(scratch) / "normalized.png", Path(scratch) / "keyed.png"
                normalized.save(intermediate)
                matte = cutout.cutout(intermediate, keyed, key=chosen, decontam="auto")
                with Image.open(keyed) as im:
                    rgba = im.convert("RGBA")
            # Drop the temporary filename from otherwise useful processing statistics.
            stats.update(normalization=normalization, cutout={k: v for k, v in matte.items() if k != "out"})
        box = rgba.getchannel("A").getbbox()
        if box is None:
            raise VideoProcessingError("VIDEO_EMPTY_STILL", "기준 그림에 보이는 캐릭터가 없습니다.")
        subject = rgba.crop(box)
        fit = min(384 / subject.width, 384 / subject.height)
        scale = float(max(1, math.floor(fit))) if fit >= 1 else fit
        size = (max(1, _round(subject.width * scale)), max(1, _round(subject.height * scale)))
        scaled = subject.resize(size, Image.Resampling.NEAREST)
        fill = _engine("frames.cutout").KEY_TARGETS[output_key]
        prepared = Image.new("RGBA", (512, 512), (*fill, 255))
        offset = ((512 - size[0]) // 2, (512 - size[1]) // 2)
        prepared.alpha_composite(scaled, offset)
        prepared = prepared.convert("RGB")
        canvas = _engine("video.canvas")
        # The RGB background is already exact. The engine's white/no-normalize
        # route pads with the actual corner RGB without matting alpha edges twice.
        prepared, canvas_stats = canvas.pad_canvas(prepared, canvas.profile_for(state), facing=facing, key="white")
        offset = (offset[0] + canvas_stats["offset"][0], offset[1] + canvas_stats["offset"][1])
        data = io.BytesIO()
        prepared.save(data, format="PNG")
        content = data.getvalue()
        if dest.exists() and dest.read_bytes() != content:
            raise VideoProcessingError("VIDEO_DESTINATION_EXISTS", "다른 준비 이미지가 이미 있습니다.", {"path": str(dest)})
        if not dest.exists():
            with dest.open("xb") as stream:
                stream.write(content)
        result = {"version": VERSION, "path": str(dest), "sourcePath": str(source),
                  "sourceSha256": digest, "sha256": hashlib.sha256(content).hexdigest(),
                  "key": output_key, "keyRgb": list(fill), "width": prepared.width, "height": prepared.height,
                  "canvas": canvas_stats,
                  "crop": list(box), "scale": scale, "scaledSize": list(size), "offset": list(offset),
                  "resampler": "nearest", **stats}
        _write(dest.with_name(dest.name + ".prepare.json"), result)
        return result
    except (OSError, ValueError, SystemExit) as exc:
        raise VideoProcessingError("VIDEO_STILL_FAILED", "기준 그림을 영상 입력으로 준비하지 못했습니다.",
                                   {"reason": str(exc)}) from exc


def build_motion_prompt(params: dict) -> str:
    """Local prompt only, adapted from Apache-2.0 sprite-gen v2.19.0 batch.py.

    Incorporates the measured Lite calm-walk clause, view locks and grip rules.
    A caller's explicit motion replaces the default gait; the calm clause must
    not contradict a requested march/sneak. No import of remote batch runners.
    """
    state = _choice(params, "state", STATES, "walk")
    direction = _choice(params, "direction", DIRECTIONS, "side")
    facing = _choice(params, "facing", ("right", "left"), "right")
    custom = params.get("motionPrompt", "")
    if not isinstance(custom, str):
        raise VideoProcessingError("VIDEO_INVALID_PARAMS", "motionPrompt는 문자열이어야 합니다.")
    custom = " ".join(custom.split())
    motions = {
        "idle": "The character stands still with both feet planted, gently breathing and settling its loose cloth. "
                "The feet never step, shuffle or slide; no walking or turning.",
        "walk": "The character walks naturally in place, as if on a treadmill.",
        "run": "The character runs naturally in place, as if on a treadmill.",
        "jump": "The character performs a modest vertical hop in place: compress, spring up, land softly and return "
                "to the exact starting stance; repeat at an even rhythm and the same height.",
        "attack": "The character performs one melee attack with what it already holds: a windup, one clean strike, "
                  "a held impact pose, then a recovery to the exact starting stance.",
        "dance": "The character dances in place with a small, evenly repeated rhythmic step and gentle body sway, "
                 "returning to the starting stance without turning or travelling.",
        "wave": "The character waves in place: raises one free hand for a friendly wave, then settles back to the "
                "exact starting stance. Any held equipment stays in its original grip.",
        "cheer": "The character celebrates in place: rises into a raised, spread-out cheer pose, holds it for a beat, "
                 "then settles back to the exact starting stance at an even rhythm.",
    }
    views = {
        "side": f"Keep the input image's side-view angle, facing {facing} throughout; no turning or drifting across the screen.",
        "front": "Keep facing the viewer directly throughout, without coming any closer or turning to the side.",
        "back": "Keep facing directly away from the viewer throughout; the face stays hidden, without moving farther away.",
        "front_diagonal": f"Keep the exact three-quarter front angle of the image throughout, heading diagonally "
                          f"toward the viewer and to the {facing}, like moving down and to the {facing} in an isometric game. "
                          "Never turn into a side view or move across the screen.",
        "back_diagonal": f"Keep the exact three-quarter back angle of the image throughout, heading diagonally away "
                         f"from the viewer toward the upper {facing}, like moving up and to the {facing} in an isometric game. "
                         "The face stays hidden; never turn into a side view or move across the screen.",
    }
    parts = ["2D game sprite animation.", custom or motions[state], views[direction]]
    if state in ("walk", "run"):
        parts.append("Stay in place as if on a treadmill; do not draw a treadmill or ground line.")
    if state == "walk" and params.get("model") == "grok-imagine-video-1.5-lite" and not custom:
        parts.append("A slow, relaxed, unhurried walk: small, low steps with the feet barely leaving the ground, "
                     "a gentle arm swing close to the body and no bounce — never running, jogging, skipping or hopping.")
    if state == "walk" and params.get("model") == "grok-imagine-video-1.5-lite" and direction == "back_diagonal":
        parts.append("The head stays level and steady over the body the whole time: it does not bob, nod, tilt or sway "
                     "from side to side; only the legs, arms and the ends of the hair move.")
    parts += [
        "Every grip stays as shown in the image. Keep equipment in the same hand; never switch, drop or add gear. "
        "A hand the action does not use stays with its equipment. Preserve the design, colors, proportions and clothing.",
        "The full body, hair and all equipment stay inside the frame with margin and constant scale. "
        "Camera completely locked: no zoom, pan, rotation or reframing.",
        "Keep the input's perfectly flat background color for the whole clip: no shadows, particles, lighting changes or effects. "
        "Crisp frames without motion blur, smears or afterimages.",
        "Return to the starting pose at the end." if state in ("idle", "attack") or
        (state in ("walk", "run") and direction in ("front_diagonal", "back_diagonal")) else
        "Consistent, evenly paced motion so the animation can loop.",
    ]
    return " ".join(parts)


def _timing(clip: Path) -> dict:
    """Read display timestamps as well as fps; MP4 duration is not n / fps by definition."""
    binary = shutil.which("ffprobe")
    if not binary:
        raise VideoProcessingError("VIDEO_FFMPEG_UNAVAILABLE", "ffprobe가 필요합니다.")
    proc = subprocess.run([binary, "-v", "error", "-select_streams", "v:0", "-show_frames",
                           "-show_entries", "frame=best_effort_timestamp_time,duration_time,pkt_duration_time:"
                           "stream=width,height,r_frame_rate,duration", "-of", "json", str(clip)],
                          capture_output=True, text=True, timeout=60)
    try:
        data = json.loads(proc.stdout)
        stream = data["streams"][0]
        num, den = stream["r_frame_rate"].split("/")
        fps = float(num) / float(den)
        rows = data["frames"]
        pts = [float(row["best_effort_timestamp_time"]) * 1000 for row in rows]
        pts = [p - pts[0] for p in pts]
        last_duration = float(rows[-1].get("duration_time") or rows[-1].get("pkt_duration_time") or 0) * 1000
        # Some muxers omit per-frame duration. The video stream's own duration is
        # preferred over the format/audio duration for the final display boundary.
        end = float(stream.get("duration") or 0) * 1000
        if end <= pts[-1]:
            end = pts[-1] + (last_duration or 1000 / fps)
        times = pts + [end]
        if proc.returncode or not math.isfinite(fps) or fps <= 0 or not all(math.isfinite(p) for p in times):
            raise ValueError("invalid fps/timestamps")
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("non-monotonic timestamps")
        # Same 100ms muxer-padding allowance as the API's 15s validation.
        if not 1 <= len(rows) <= 600 or not 0 < end <= 15100 or not 1 <= max(stream["width"], stream["height"]) <= 2048:
            raise ValueError("video limits exceeded")
        cfr = all(abs((b - a) - 1000 / fps) < 1.5 for a, b in zip(pts, pts[1:]))
        return {"width": stream["width"], "height": stream["height"], "fps": fps,
                "frameCount": len(rows), "durationMs": end, "timesMs": times, "constantFrameRate": cfr}
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise VideoProcessingError("VIDEO_INVALID_MEDIA", "영상 프레임과 재생 시각을 확인할 수 없습니다.",
                                   {"reason": str(exc), "probeError": proc.stderr[:300]}) from exc


def _manifest(work: Path, paths: list[Path]) -> list[dict]:
    return [{"file": p.relative_to(work).as_posix(), "sha256": _sha(p)} for p in paths]


def _valid_manifest(work: Path, manifest: list[dict]) -> bool:
    if not manifest:
        return False
    for entry in manifest:
        path = (work / entry["file"]).resolve()
        if not path.is_relative_to(work) or not path.is_file() or _sha(path) != entry["sha256"]:
            return False
    return True


def _spill_decision(directory: Path, options: dict, first_frame: Path) -> dict:
    """Adapt alpha references to the engine's opaque-key still contract.

    Use the video's key, never hidden RGB under alpha. Keep the reference's
    native pixels and the engine's material threshold/fringe policy; a one-pixel
    key ring gives even tightly cropped references a real background border.
    Opaque prepared canvases pass through unchanged.
    """
    reference = Path(options["referencePath"]) if options["referencePath"] else None
    if reference is None:
        return {"mode": "small", "reason": "no reference"}
    engine, cutout = _engine("video.frames"), _engine("frames.cutout")
    key = options["key"]
    if key == "auto":
        with Image.open(first_frame) as image:
            key = cutout._detect_key_kind(cutout._corner_average(image))
    with Image.open(reference) as image:
        rgba = image.convert("RGBA")
    transparent = rgba.getchannel("A").getextrema()[0] < 255
    prepared = reference
    if transparent:
        if rgba.getchannel("A").getbbox() is None:
            raise VideoProcessingError("VIDEO_EMPTY_STILL", "기준 그림에 보이는 캐릭터가 없습니다.")
        margin = engine.SPILL_REFERENCE_MARGIN
        canvas = Image.new("RGBA", (rgba.width + 2 * margin, rgba.height + 2 * margin),
                           (*cutout.KEY_TARGETS.get(key, (255, 255, 255)), 255))
        canvas.alpha_composite(rgba, (margin, margin))
        prepared = directory / "spill-reference.png"
        canvas.convert("RGB").save(prepared)
    decision = engine.decide_spill(prepared, key)
    decision.update(referenceSourceSha256=options["referenceSha256"],
                    referencePreparedSha256=_sha(prepared), referenceHadTransparency=transparent,
                    referencePreparation="alpha-composite-key-ring" if transparent else "unchanged",
                    key=key, keySource="first-video-frame" if options["key"] == "auto" else "explicit")
    return decision


def _run_extraction(clip: Path, directory: Path, options: dict, source: dict) -> dict:
    engine = _engine("video.frames")
    if source["constantFrameRate"]:
        files = engine.extract(clip, directory / "raw")
    else:
        # The engine's default ffmpeg image output can duplicate/drop VFR frames.
        # Keep display order exactly, then reuse its keying and spill decisions.
        raw = directory / "raw"
        raw.mkdir()
        binary = shutil.which("ffmpeg")
        if not binary:
            raise VideoProcessingError("VIDEO_FFMPEG_UNAVAILABLE", "ffmpeg가 필요합니다.")
        proc = subprocess.run([binary, "-v", "error", "-i", str(clip), "-map", "0:v:0", "-fps_mode", "passthrough",
                               str(raw / "frame-%04d.png")], capture_output=True, text=True, timeout=60)
        if proc.returncode:
            raise VideoProcessingError("VIDEO_EXTRACTION_FAILED", "원시 프레임을 추출하지 못했습니다.",
                                       {"reason": proc.stderr[:300]})
        files = sorted(raw.glob("frame-*.png"))
    if not files:
        raise VideoProcessingError("VIDEO_EXTRACTION_FAILED", "원시 프레임을 추출하지 못했습니다.")
    decision = _spill_decision(directory, options, files[0])
    report = engine.key_frames(files, directory / "keyed", key=options["key"],
                               spill=decision["mode"], allow_subject=True, decontam="auto")
    report.update(kind="sprite-gen-video-frames-report", clip=str(clip), out_dir=str(directory),
                  raw_dir=str(directory / "raw"), keyed_dir=str(directory / "keyed"),
                  width=source["width"], height=source["height"], fps=source["fps"],
                  nb_frames=source["frameCount"], duration=source["durationMs"] / 1000,
                  spill=decision, key=options["key"],
                  extractionMode="engine-cfr" if source["constantFrameRate"] else "timestamp-passthrough")
    _write(directory / "frames.report.json", report)
    return report


def _gait_fallback(files, source, profile, directory, first_error):
    """One bounded, recorded re-search; never replaces a successful first cut."""
    loop, fallback = _engine("video.loop"), _engine("video.gait_fallback")
    automatic, local_cycle = _engine("video.auto_motion"), _engine("video.local_cycle")
    images = []
    for path in files:
        with Image.open(path) as im:
            images.append(im.convert("RGBA"))
    drift = fallback.scale_drift(images)
    record = {"reason": str(first_error), "scaleDrift": {k: drift[k] for k in ("height_first_px", "height_last_px", "drift")},
              "scaleDriftMin": fallback.SCALE_DRIFT_MIN, "scaleUndone": False, "attempts": 1}
    lo, _ = profile.window(len(files), source["fps"])
    hi = fallback.long_window(lo, len(files), source["fps"])
    record.update(window=[lo, hi], maxFraction=fallback.LONG_CYCLE_FRACTION)
    if abs(drift["drift"]) >= fallback.SCALE_DRIFT_MIN:
        images = fallback.undo_scale(images, drift)
        files = fallback.write_frames(images, [p.name for p in files], directory / "scale-corrected")
        record["scaleUndone"] = True
        reference_height = float(drift["height"][0])
        transformations = []
        for index, height in enumerate(drift["height"]):
            scale = reference_height / float(height)
            ax, ay = float(drift["foot_x"][index]), float(drift["foot_y"][index])
            transformations.append({"sourceFrameIndex": index, "fittedHeightPx": float(height),
                                    "footAnchor": {"x": ax, "y": ay},
                                    "sourceTransform": {"scaleX": scale, "scaleY": scale,
                                                        "offsetX": ax * (1 - scale), "offsetY": ay * (1 - scale)}})
        record["scaleCorrection"] = {"method": "fitted-height-about-fitted-foot-v1",
                                     "sourceCoordinateSpace": "decoded-video-canvas", "coordinateSpace": "processed-video-canvas",
                                     "referenceSourceFrameIndex": 0, "referenceFittedHeightPx": reference_height,
                                     "resampler": "premultiplied-bicubic", "frames": transformations}
    try:
        distances, trajectory, analysis = automatic.analyse(images, fps=source["fps"])
        cycle = local_cycle.detect(distances, trajectory, min_len=lo, max_len=hi,
                                   gait_floor=round(profile.min_seconds * source["fps"]),
                                   periodicity_min=loop.PERIODICITY_MIN,
                                   double_tolerance=loop.GAIT_DOUBLE_TOL, double_search=loop.GAIT_DOUBLE_SEARCH,
                                   max_fraction=fallback.LONG_CYCLE_FRACTION)
        # Analysis removes drift, but accepting it alone is not a rendered loop.
        # Keep the conservative source-pixel seam gate until an explicit motion
        # correction contract can preserve its padded canvas/anchor mapping.
        start, length = cycle["start"], cycle["length"]
        visible = loop.fixed_cycle(loop.distance_matrix(files[start:start + length]), start=0, length=length)
        if not math.isfinite(visible["ratio"]) or visible["ratio"] > loop.SEAM_RATIO_MAX:
            raise ValueError("fallback rendered seam ratio exceeds threshold")
        cycle.update(analysisRatio=cycle["ratio"], ratio=visible["ratio"], seam=visible["seam"],
                     inner_mean_adjacent=visible["inner_mean_adjacent"], gaitFallback=record,
                     automaticMotionAnalysis=analysis)
        return cycle, files
    except (SystemExit, ValueError) as exc:
        raise VideoProcessingError("VIDEO_NO_PERIODIC_MATCH", "제한된 재탐색에서도 반복 동작을 확인하지 못했습니다. 수동 구간을 선택하세요.",
                                   {"gaitFallback": {**record, "failure": str(exc)},
                                    "reason": str(first_error), "metrics": getattr(exc, "diagnostics", None)}) from exc


def _select(files: list[Path], source: dict, options: dict, directory: Path | None = None) -> dict:
    loop = _engine("video.loop")
    mode, n = options["loopMode"], len(files)
    if mode == "auto":
        if not source["constantFrameRate"]:
            raise VideoProcessingError("VIDEO_VARIABLE_RATE_AUTO", "가변 프레임률 영상은 전체 또는 수동 구간을 선택하세요.")
        profile = loop.profile_for(options["state"])
        lo, hi = profile.window(n, source["fps"])
        cycle, periodic_attempt, corrected = None, None, None
        try:
            distances = loop.distance_matrix(files)
            # Idle/attack generation is pinned by the parent. For idle, verify
            # the observed pin before retaining the whole clip minus its duplicate
            # last pose. Merely asking the model to pin is not evidence it did.
            if options["state"] == "idle" and n >= 3:
                pinned = loop.pinned_cycle(distances, seam_max=loop.SEAM_RATIO_MAX)
                if pinned["pin_error"] <= pinned["pin_tolerance"]:
                    cycle = pinned
            if options["state"] == "attack":
                # One windup/strike/recovery, not a gait. This also refuses a
                # static held weapon or an excursion that never returns.
                cycle = loop.detect_one_shot(distances, min_len=4, max_len=n,
                                             frame_mass=loop.frame_masses(files))
            if cycle is None:
                try:
                    cycle = loop.detect_cycle(distances, min_len=lo, max_len=hi,
                                              gait_floor=round(profile.min_seconds * source["fps"]) if profile.gait else None)
                    floor = loop.periodicity_floor(n, cycle["period_global"], partial_repeat=profile.action_seconds is not None)
                    cycle["periodicity_min"] = floor
                    cycle["kind"] = "periodic" if cycle["periodicity"] >= floor else "idle-window"
                    if profile.periodic and cycle["periodicity"] < floor:
                        raise ValueError("periodicity below threshold")
                    if profile.one_shot_ok:
                        # A long resting hold with camera/keying jitter can pass
                        # the global period floor while omitting the sole jump.
                        # Require the cut to retain the clip's motion envelope;
                        # this is pixel excursion, never an anatomical judgment.
                        first, last = cycle["start"], cycle["start"] + cycle["length"]
                        excursion, total = float(distances[first:last, first:last].max()), float(distances.max())
                        share = excursion / total if total > 0 else 0.0
                        cycle["excursionCoverage"] = {"selected": excursion, "clip": total, "share": share, "minShare": 0.5}
                        if share < 0.5:
                            raise ValueError("periodic candidate omits the main action excursion")
                except (SystemExit, ValueError) as exc:
                    if not profile.one_shot_ok:
                        raise
                    # Public run_loop policy: an action can be performed once.
                    # Keep the rejected periodic evidence and do local analysis
                    # only; never silently regenerate or fabricate missing poses.
                    periodic_attempt = {"metrics": getattr(exc, "diagnostics", cycle), "reason": str(exc)}
                    cycle = loop.detect_one_shot(distances, min_len=4, max_len=n,
                                                 frame_mass=loop.frame_masses(files))
            # An entirely static idle is a valid hold, not a divide-by-zero seam.
            ratio = cycle["ratio"]
            if cycle["seam"] == 0 and cycle["inner_mean_adjacent"] == 0:
                ratio = cycle["ratio"] = 0.0
            # A pinned idle uses the actual last->first pin error rather than
            # magnifying re-render noise by a near-zero breathing playback step.
            if cycle["kind"] != "pinned" and (not math.isfinite(ratio) or ratio > loop.SEAM_RATIO_MAX):
                raise ValueError("seam ratio exceeds threshold")
        except (SystemExit, ValueError) as exc:
            if profile.gait and directory is not None:
                try:
                    cycle, corrected = _gait_fallback(files, source, profile, directory, exc)
                except VideoProcessingError as failure:
                    failure.payload.update(window=[lo, hi], metrics=_finite(getattr(exc, "diagnostics", cycle)),
                                           seamRatioMax=loop.SEAM_RATIO_MAX)
                    raise
            else:
                code = "VIDEO_NO_ACTION_MATCH" if profile.one_shot_ok else "VIDEO_NO_PERIODIC_MATCH"
                raise VideoProcessingError(code, "사용할 동작 구간을 확인하지 못했습니다. 보존된 영상에서 수동 구간을 선택하세요.",
                                           {"window": [lo, hi], "metrics": _finite(getattr(exc, "diagnostics", cycle)),
                                            "periodicAttempt": _finite(periodic_attempt),
                                            "seamRatioMax": loop.SEAM_RATIO_MAX, "reason": str(exc)}) from exc
        start, end = cycle["start"], cycle["start"] + cycle["length"]
        metrics = {k: v for k, v in cycle.items() if k != "candidates"}
        if periodic_attempt is not None:
            metrics["periodicAttempt"] = {**periodic_attempt, "metrics": {
                k: v for k, v in (periodic_attempt["metrics"] or {}).items() if k != "candidates"}}
        kind = cycle["kind"]
    else:
        start = options["startFrame"] if mode == "manual" else 0
        end = options["endFrame"] if mode == "manual" else n
        # Strict bounds; never clamp an invalid explicit request to the source.
        if not 0 <= start < end <= n:
            raise VideoProcessingError("VIDEO_INVALID_RANGE", "수동 구간은 0 ≤ startFrame < endFrame ≤ frameCount여야 합니다.",
                                       {"startFrame": start, "endFrame": end, "frameCount": n})
        distances = loop.distance_matrix(files[start:end])
        if end - start >= 2:
            cycle = loop.fixed_cycle(distances, start=0, length=end - start)
            metrics = {k: v for k, v in cycle.items() if k not in ("start", "length")}
        else:
            metrics = {"ratio": None, "periodicity": None}
        kind = "full" if mode == "full" else "manual"
    result = _finite({"mode": mode, "kind": kind, "startFrame": start, "endFrame": end,
                    "loop": mode != "full" and kind != "one-shot",
                    "verifiedPeriodic": mode == "auto" and kind == "periodic", "reviewRequired": True,
                    "seamRatio": metrics.get("ratio"), "seamRatioMax": loop.SEAM_RATIO_MAX,
                    "periodicity": metrics.get("periodicity"), "metrics": metrics})
    if mode == "auto" and corrected is not None:
        result["_processedKeyedPaths"] = [str(p) for p in corrected]
    return result


def _repair_selection(files, selection, options, directory):
    """Repair only explicitly enabled gait loops; all sources stay immutable."""
    mode = options["repairMode"]
    if options["state"] not in ("walk", "run") or not selection["loop"]:
        return files, {"applied": False, "mode": mode, "reason": "not a gait loop", "replaced": []}
    start, end = selection["startFrame"], selection["endFrame"]
    if end - start < 4:
        return files, {"applied": False, "mode": mode, "reason": "fewer than four frames", "replaced": []}
    images = []
    for path in files[start:end]:
        with Image.open(path) as image:
            images.append(image.convert("RGBA"))
    repair, rife = _engine("video.repair"), _engine("video.rife")
    record = {"applied": False, "mode": mode, "reason": "disabled", "replaced": []}
    if mode != "off":
        located = None
        def interpolate(a, b, t):
            nonlocal located
            if located is None:
                located = rife_interpolator()
            return located(a, b, t)
        try:
            updated, facts = repair.repair_jumps(images, interpolate, facing=options["facing"])
        except rife.RifeNotInstalled as exc:
            if mode == "on":
                raise VideoProcessingError("VIDEO_RIFE_UNAVAILABLE", "RIFE 설치를 확인하세요. 원본 프레임은 보존했습니다.", {"reason": str(exc)}) from exc
            record.update(reason="RIFE unavailable; original frames retained", warning=str(exc))
        except (rife.RifeUnavailable, subprocess.SubprocessError) as exc:
            raise VideoProcessingError("VIDEO_RIFE_FAILED", "RIFE 보간이 실패했습니다. 원본 프레임은 보존했습니다.", {"reason": str(exc)}) from exc
        else:
            record.update(facts, applied=bool(facts["replaced"]), reason="repaired" if facts["replaced"] else "no jump frames")
            if located is not None:
                record["interpolator"] = {"kind": "rife-ncnn-vulkan", **located.describe()}
            if record["applied"]:
                target = directory / "repaired"
                target.mkdir()
                updated_files = []
                for i, path in enumerate(files):
                    dest = target / path.name
                    if start <= i < end and i - start in facts["replaced"]:
                        updated[i - start].save(dest)
                    else:
                        shutil.copy2(path, dest)
                    updated_files.append(dest)
                files, images = updated_files, updated
    jolt = repair.measure_jolt(images, facing=options["facing"])
    record["jolt"] = {**jolt, "warnings": repair.jolt_verdict(jolt), "gated": False}
    record["sourceFrameIndices"] = [start + i for i in record["replaced"]]
    return files, _finite(record)


def _align_selected_cycle(raw, keyed, original_keyed, source, selection, options, directory):
    """Resample an explicitly matched cycle, preserving exact original samples."""
    align, rife = _engine("video.align"), _engine("video.rife")
    if not selection["loop"]:
        raise VideoProcessingError("VIDEO_ALIGN_NOT_LOOP", "주기 맞춤은 반복 동작에서 사용할 수 있습니다.")
    start, end = selection["startFrame"], selection["endFrame"]
    count, length = options["targetFrameCount"], end - start
    images = []
    for path in keyed[start:end]:
        with Image.open(path) as image:
            images.append(image.convert("RGBA"))
    located = None
    def interpolate(a, b, t):
        nonlocal located
        if located is None:
            located = rife_interpolator()
        return located(a, b, t)
    try:
        aligned, facts = align.resample(images, count, interpolate)
        turned = align.foot_strike_start(aligned)
    except rife.RifeNotInstalled as exc:
        raise VideoProcessingError("VIDEO_RIFE_UNAVAILABLE", "프레임 수를 맞추려면 RIFE 보간이 필요합니다.", {"reason": str(exc)}) from exc
    except (rife.RifeUnavailable, subprocess.SubprocessError) as exc:
        raise VideoProcessingError("VIDEO_RIFE_FAILED", "주기 맞춤 보간에 실패했습니다. 원본 프레임은 보존했습니다.", {"reason": str(exc)}) from exc
    times = source["timesMs"]
    duration = options.get("targetDurationMs", _round(times[end] - times[start]))
    boundaries = [_round(k * duration / count) for k in range(count + 1)]
    target = directory / "aligned"
    target.mkdir()
    frames = []
    repaired = selection["repair"].get("sourceFrameIndices", [])
    for output_index in range(count):
        sample_index = (output_index + turned) % count
        t = sample_index * length / count
        i, fraction = math.floor(t), t % 1
        if fraction < align.SNAP:
            primary, fraction = start + i % length, 0.0
        elif fraction > 1 - align.SNAP:
            primary, fraction = start + (i + 1) % length, 0.0
        else:
            primary = start + i % length
        second = start + (i + 1) % length
        made = fraction != 0.0
        path = target / f"frame-{output_index:04d}.png"
        aligned[sample_index].save(path)
        existing_repair = primary in repaired
        interpolation = ({"method": "rife-cycle-align", "sourceFrameIndices": [primary, second],
                          "fraction": fraction, "sourceTimeMs": [times[primary], times[second]],
                          "inputJumpRepairSourceFrameIndices": [v for v in (primary, second) if v in repaired]}
                         if made else {"method": "rife-jump-repair", "sourceFrameIndices":
                                       [start + (primary - start - 1) % length, start + (primary - start + 1) % length],
                                       "fraction": 0.5} if existing_repair else None)
        frame = {"rawPath": str(raw[primary]), "keyedPath": str(path), "originalKeyedPath": str(original_keyed[primary]),
                 "outputFrameIndex": output_index, "sourceFrameIndex": primary,
                 "sourceTimeMs": times[primary] + fraction * (times[primary + 1] - times[primary]),
                 "durationMs": boundaries[output_index + 1] - boundaries[output_index],
                 "interpolated": made or existing_repair, "processing": {"kind": "cycle-alignment", "sampleIndex": sample_index}}
        if interpolation:
            frame["interpolation"] = interpolation
            frame["processing"]["interpolation"] = interpolation
        frames.append(frame)
    record = {**facts, "turnedBy": turned, "durationMs": duration,
              "sourceDurationMs": times[end] - times[start], "sourceFrameCount": length,
              "referencePhaseChanged": False, "phase": "new cycle starts at detected foot strike"}
    if located:
        record["interpolator"] = {"kind": "rife-ncnn-vulkan", **located.describe()}
    return frames, record


def _describe_source_processing(frame, selection):
    """Coordinate evidence only: never claim an interpolated image is affine raw pixels."""
    processing = frame["processing"]
    correction = selection.get("metrics", {}).get("gaitFallback", {}).get("scaleCorrection")
    processing["sourceCoordinateSpace"] = "decoded-video-canvas"
    processing["coordinateSpace"] = "processed-video-canvas" if correction or frame["interpolated"] else "decoded-video-canvas"
    if frame["interpolated"]:
        processing["rawToProcessedMapping"] = "non-affine-interpolation"
    if correction:
        processing["scaleCorrection"] = {k: v for k, v in correction.items() if k != "frames"}
        if frame["interpolated"]:
            indices = frame["interpolation"]["sourceFrameIndices"]
            processing["preInterpolationSourceTransforms"] = [correction["frames"][i] for i in indices]
        else:
            measured = correction["frames"][frame["sourceFrameIndex"]]
            processing["sourceTransform"] = measured["sourceTransform"]
            processing["scaleCorrection"].update(fittedHeightPx=measured["fittedHeightPx"], footAnchor=measured["footAnchor"])
            processing["rawToProcessedMapping"] = "affine-before-normalization"


def _preview(frames: list[dict], directory: Path, loop: bool) -> dict:
    """Small full-canvas previews only; exact RGBA candidates are never resized."""
    gif_engine = _engine("util.gif_utils")
    images = []
    for frame in frames:
        with Image.open(frame["keyedPath"]) as im:
            image = im.convert("RGBA")
        image.thumbnail((256, 256), Image.Resampling.NEAREST)
        images.append(image)
    prepared = [gif_engine._prepare_transparent_frame(im, 8) for im in images]
    elapsed, previous, delays = 0, 0, []
    for frame in frames:
        elapsed += frame["durationMs"]
        boundary = _round(elapsed / 10) * 10
        delays.append(boundary - previous)
        previous = boundary
    # GIF cannot represent sub-10ms holds. The PNGs and JSON remain authoritative.
    if min(delays) <= 0:
        return {"warning": "GIF 시간 단위보다 짧은 프레임이 있어 미리보기를 생략했습니다."}
    gif = directory / "preview.gif"
    prepared[0].save(gif, save_all=True, append_images=prepared[1:], duration=delays,
                     disposal=2, transparency=255, optimize=False, **({"loop": 0} if loop else {}))
    w, h = images[0].size
    columns = min(8, len(images))
    sheet = Image.new("RGBA", (w * columns, h * math.ceil(len(images) / columns)))
    for i, im in enumerate(images):
        sheet.paste(im, ((i % columns) * w, (i // columns) * h))
    sheet.save(directory / "preview.sheet.png")
    with Image.open(gif) as encoded:
        actual_duration = sum(frame.info.get("duration", 0) for frame in ImageSequence.Iterator(encoded))
        actual_frames = encoded.n_frames  # Encoders may merge identical consecutive images.
    if actual_duration != sum(delays):
        raise VideoProcessingError("VIDEO_PREVIEW_TIMING", "GIF 재생 시간이 원본 구간과 다릅니다.")
    return {"path": str(gif), "sheetPath": str(directory / "preview.sheet.png"),
            "cellWidth": w, "cellHeight": h, "columns": columns, "durationMs": actual_duration,
            "encodedFrameCount": actual_frames, "selectedFrameCount": len(frames),
            "kind": "full-canvas-thumbnail", "resampler": "nearest"}


def process_clip(clip: Path, work: Path, params: dict, on_progress=None) -> dict:
    """Extract/key once and select a range, retaining evidence even on refusal.

    params: contract state/key/loopMode/startFrame/endFrame/maxFrames, plus optional
    internal ``referencePath`` for engine spill=auto. Without a reference spill
    stays conservative (small). bodyHeight/cellWidth/cellHeight are caller-owned.
    Manual endFrame is exclusive. Auto requires a gait repeat, or a complete
    one-shot action (attack / nonperiodic jump). Pinned idle retains the whole
    observed return. Full and one-shot play once; manual loops with review pending.
    Callback: (stage: str, message: str); cancellation exceptions propagate.
    """
    clip, work = Path(clip).expanduser().resolve(), Path(work).expanduser().resolve()
    state = _choice(params, "state", STATES, "walk")
    key = _choice(params, "key", KEYS, "auto")
    mode = _choice(params, "loopMode", ("auto", "full", "manual"), "auto")
    limit = _integer(params.get("maxFrames", 32), "maxFrames", 4, 64)
    options = {"state": state, "key": key, "loopMode": mode, "maxFrames": limit,
               "repairMode": _choice(params, "repairMode", ("off", "auto", "on"), "off"),
               "facing": _choice(params, "facing", ("right", "left"), "right")}
    if params.get("targetFrameCount") is not None:
        options["targetFrameCount"] = _integer(params["targetFrameCount"], "targetFrameCount", 4, 64)
        if params.get("targetDurationMs") is not None:
            options["targetDurationMs"] = _integer(params["targetDurationMs"], "targetDurationMs", options["targetFrameCount"], 60000)
    elif params.get("targetDurationMs") is not None:
        raise VideoProcessingError("VIDEO_INVALID_PARAMS", "targetDurationMs에는 targetFrameCount가 필요합니다.")
    if mode == "manual":
        for field in ("startFrame", "endFrame"):
            options[field] = _integer(params.get(field), field, 0, 600)
        if options["startFrame"] >= options["endFrame"]:
            raise VideoProcessingError("VIDEO_INVALID_RANGE", "endFrame은 startFrame보다 커야 합니다.")
    reference = params.get("referencePath")
    reference = Path(reference).expanduser().resolve() if reference else None
    work.mkdir(parents=True, exist_ok=True)
    stage, artifact_dir = "extract", work
    checkpoint = work / "video-processing.json"
    extraction = None
    def progress(name, message):
        if on_progress:
            on_progress(name, message)
    try:
        digest = _sha(clip)
        extraction_options = {"version": VERSION, "sourceSha256": digest, "key": key, "decontam": "auto",
                              "referencePath": str(reference) if reference else None,
                              "referenceSha256": _sha(reference) if reference else None}
        extraction_id = hashlib.sha256(_encoded(extraction_options)).hexdigest()[:24]
        cache = work / "extractions" / extraction_id
        marker = cache / "complete.json"
        if marker.is_file():
            cached = json.loads(marker.read_text())
            if _valid_manifest(work, cached.get("manifest", [])):
                extraction = cached
        if extraction is None:
            source = _timing(clip)
            if mode == "manual" and options["endFrame"] > source["frameCount"]:
                raise VideoProcessingError("VIDEO_INVALID_RANGE", "수동 구간이 영상 프레임 수를 초과합니다.",
                                           {"frameCount": source["frameCount"], **options})
            cache.mkdir(parents=True, exist_ok=True)
            artifact_dir = Path(tempfile.mkdtemp(prefix="attempt-", dir=cache))
            _write(checkpoint, {"stage": stage, "status": "running", "options": options,
                                "extraction": extraction_options, "artifactDir": str(artifact_dir)})
            progress(stage, "원본 프레임을 보존하고 배경을 제거합니다.")
            report = _run_extraction(clip, artifact_dir, extraction_options, source)
            raw, keyed = sorted((artifact_dir / "raw").glob("frame-*.png")), sorted((artifact_dir / "keyed").glob("frame-*.png"))
            if len(raw) != source["frameCount"] or len(keyed) != len(raw):
                raise VideoProcessingError("VIDEO_FRAME_COUNT_MISMATCH", "원본 시각과 추출 프레임 수가 일치하지 않습니다.",
                                           {"source": source["frameCount"], "raw": len(raw), "keyed": len(keyed)})
            for path in raw + keyed:
                with Image.open(path) as image:
                    if image.size != (source["width"], source["height"]):
                        raise VideoProcessingError("VIDEO_CANVAS_MISMATCH", "추출 캔버스 크기가 원본과 다릅니다.")
            report_path = artifact_dir / "frames.report.json"
            extraction = {"source": source, "options": extraction_options, "rawDir": str(artifact_dir / "raw"),
                          "keyedDir": str(artifact_dir / "keyed"), "reportPath": str(report_path),
                          "spill": report["spill"], "edgeContacts": report.get("edge_contacts", []),
                          "manifest": _manifest(work, [*raw, *keyed, report_path,
                                                       *artifact_dir.glob("spill-reference.png")])}
            _write(marker, extraction)
        else:
            progress(stage, "보존된 원본·배경 제거 프레임을 재사용합니다.")
        source = extraction["source"]
        raw, keyed = sorted(Path(extraction["rawDir"]).glob("frame-*.png")), sorted(Path(extraction["keyedDir"]).glob("frame-*.png"))
        stage = "select_cycle"
        selections = work / "selections"
        selections.mkdir(exist_ok=True)
        artifact_dir = Path(tempfile.mkdtemp(prefix="selection-", dir=selections))
        _write(checkpoint, {"stage": stage, "status": "running", "options": options,
                            "extractionId": extraction_id, "artifactDir": str(artifact_dir)})
        progress(stage, "재생 구간과 프레임 시간을 분석합니다.")
        selection = _select(keyed, source, options, artifact_dir)
        original_keyed = keyed
        if selection.get("_processedKeyedPaths"):
            keyed = [Path(p) for p in selection.pop("_processedKeyedPaths")]
        keyed, repair = _repair_selection(keyed, selection, options, artifact_dir)
        selection["repair"] = repair
        loop_engine = _engine("video.loop")
        with Image.open(original_keyed[0]) as im:
            first = im.convert("RGBA")
        box = first.getchannel("A").point(lambda a: 255 if a >= 8 else 0).getbbox()
        if box is None:
            raise VideoProcessingError("VIDEO_EMPTY_FIRST_FRAME", "첫 프레임에서 몸 높이와 앵커를 측정할 수 없습니다.")
        standing = box[3] - box[1]
        anchor = {"x": loop_engine.foot_centre(first, box), "y": box[3]}
        start, end = selection["startFrame"], selection["endFrame"]
        count = min(limit, end - start)
        indices = [start + i * (end - start) // count for i in range(count)]
        times = source["timesMs"]
        boundaries = [_round(times[i] - times[start]) for i in [*indices, end]]
        frames = [{"rawPath": str(raw[i]), "keyedPath": str(keyed[i]), "sourceFrameIndex": i,
                   "outputFrameIndex": k,
                   "sourceTimeMs": times[i], "durationMs": boundaries[k + 1] - boundaries[k],
                   "originalKeyedPath": str(original_keyed[i]),
                   "interpolated": i in repair.get("sourceFrameIndices", []),
                   "processing": {"kind": "rife-jump-repair" if i in repair.get("sourceFrameIndices", []) else
                                  "scale-drift-correction" if selection.get("metrics", {}).get("gaitFallback", {}).get("scaleUndone") else "chroma-key",
                                  **({"interpolation": {"method": "rife-ncnn-vulkan", "fraction": 0.5,
                                                       "sourceFrameIndices": [start + (i - start - 1) % (end - start),
                                                                              start + (i - start + 1) % (end - start)]}}
                                     if i in repair.get("sourceFrameIndices", []) else {})}}
                  for k, i in enumerate(indices)]
        for frame in frames:
            if frame["interpolated"]:
                frame["interpolation"] = frame["processing"]["interpolation"]
        if "targetFrameCount" in options:
            frames, alignment = _align_selected_cycle(raw, keyed, original_keyed, source, selection, options, artifact_dir)
            selection["cycleAlignment"] = alignment
            count = len(frames)
            boundaries = [0, alignment["durationMs"]]
        for frame in frames:
            _describe_source_processing(frame, selection)
        if any(frame["durationMs"] <= 0 for frame in frames):
            raise VideoProcessingError("VIDEO_TIMING_TOO_SHORT", "밀리초 단위로 보존할 수 없는 프레임 시간입니다.")
        selection.update(sourceDurationMs=times[end] - times[start], durationMs=boundaries[-1],
                         sampledFrameCount=count, sourceFrameCount=end - start)
        preview = _preview(frames, artifact_dir, selection["loop"])
        files = [extraction["reportPath"], str(marker), str(artifact_dir / "processing.report.json"), str(checkpoint)]
        files += [preview[k] for k in ("path", "sheetPath") if k in preview]
        result = {"frames": frames, "source": {k: v for k, v in source.items() if k != "timesMs"},
                  "selection": selection, "standingHeight": standing, "anchor": anchor,
                  "boundsPaths": [str(f["keyedPath"]) for f in frames] if "targetFrameCount" in options else
                                 [str(p) for p in keyed[start:end]],
                  "anchorSourceFrameIndex": 0, "sourceSha256": digest, "preview": preview,
                  "extraction": {k: v for k, v in extraction.items() if k not in ("source", "manifest", "options")},
                  "files": [Path(p).relative_to(work).as_posix() for p in files]}
        if keyed != original_keyed:
            result["extraction"]["processedKeyedDir"] = str(keyed[0].parent)
        if "path" in preview:
            result["previewPath"] = preview["path"]
        _write(artifact_dir / "processing.report.json", result)
        _write(checkpoint, {"stage": "complete", "status": "complete", "options": options,
                            "extractionId": extraction_id, "report": str(artifact_dir / "processing.report.json")})
        progress("complete", "전체 캔버스의 프레임 후보와 처리 보고서를 준비했습니다.")
        return result
    except (VideoProcessingError, SystemExit, OSError, ValueError, subprocess.SubprocessError) as exc:
        error = exc if isinstance(exc, VideoProcessingError) else VideoProcessingError(
            "VIDEO_PROCESSING_FAILED", "로컬 영상 처리에 실패했습니다. 보존된 파일로 다시 처리할 수 있습니다.", {"reason": str(exc)})
        error.payload.update(stage=stage, work=str(work), artifactDir=str(artifact_dir), regenerationRequired=False)
        if extraction:
            error.payload.update(rawDir=extraction["rawDir"], keyedDir=extraction["keyedDir"])
        failure = {"stage": stage, "status": "failed", "options": options, "code": error.code,
                   "message": error.message, "payload": _finite(error.payload)}
        _write(artifact_dir / "failure.report.json", failure)
        _write(checkpoint, failure)
        raise error from (exc if error is not exc else None)
