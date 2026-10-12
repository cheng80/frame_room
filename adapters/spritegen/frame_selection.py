"""Optional candidate selection around the uniform sample positions.

measure (code) -> observe (newest Luna in the local Codex catalog at medium, cached JSON) ->
judge (FrameRoom code policy + rules) -> pick one candidate per uniform slot -> sequence checks.

``keep/reject/review`` are recommendations recorded beside a frame; they never set
``Frame.review``, ``reviewReason`` or ``hidden`` and never delete a candidate.
An empty (blank) frame is ``reject`` by FrameRoom code; any other missing/unknown/conflicting/
failed observation becomes ``review``. A slot without a ``keep`` alternative keeps the original
uniform frame, so the output count, order, loop flag and total duration of the existing path are
preserved. Without a usable Luna in the catalog nothing is observed: empty frames reject, the
rest review, and every slot keeps its uniform frame.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from functools import partial
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

VERSION = "frame-selection-v2"
# Fixed allowlist for an explicit, manual per-request comparison only (model + effort); it is
# never an automatic fallback. The automatic default is not in here: it is the newest Luna of
# the local Codex catalog (``latest_luna``), always at medium, and is never swapped for another
# model on failure. A different observer is a different cache key and receipt; ``gpt-6-luna``
# keeps the id (and cache keys) it had before.
OBSERVERS = {"gpt-6-luna-medium": ("gpt-6-luna", "medium"), "gpt-6.1-sol-medium": ("gpt-6.1-sol", "medium")}
# ASCII digits with bounded parts: a malformed or oversized version never matches (so int() cannot fail).
LUNA = re.compile(r"gpt-([0-9]{1,4}(?:\.[0-9]{1,4}){0,3})-luna")
OBSERVER_EFFORT = "medium"
OBSERVER_TIMEOUT_SECONDS = 300
PROMPT_VERSION = "frame-observation-v2"
# Codex sends local images fitted inside 2048px (the 448px-cell sheet of v1 arrived as 503x2048,
# about 234px per cell). Every image here keeps its long side <= 2048 and its short side <= 768
# (the high-detail vision limit), so neither Codex nor the service has to shrink it again.
IMAGE_MAX_EDGE = 2048
IMAGE_SHORT_EDGE = 768
DETAIL_MAX_CELL = 720
RULES_VERSION = "frame-rules-v1"
MAX_CANDIDATES = 32
MAX_RADIUS = 2
LABELS = ("keep", "reject", "review")
# Field -> the answer that means "defect". Anything other than yes/no is unknown.
PROBLEM = {"same_character": "no", "extra_or_missing_parts": "yes", "body_cropped": "yes",
           "blur_or_smear": "yes", "background_residue": "yes", "colour_contamination": "yes",
           "pose_fits_neighbors": "no"}
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["frames"],
    "properties": {"frames": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["id", *PROBLEM, "note"],
        "properties": {"id": {"type": "string"}, "note": {"type": "string"},
                       **{k: {"type": "string", "enum": ["yes", "no", "unknown"]} for k in PROBLEM}}}}}}
PROMPT = """You are an image observer for sprite animation frames. Do not edit, generate or judge quality overall.
Image 1 is an overview sheet for whole-body context and pose order: each row is one output slot in time order;
cells in a row are neighbouring source frames, left to right, and rows continue into the next row.
Images 2 to {last} are the same rows drawn large, one image per row in the same order, for close inspection.
{reference}
Every candidate cell is labelled with its id (for example F012). The sheet ids are: {ids}.
For EVERY id return one object with these fields, each "yes", "no" or "unknown":
- same_character: same character design/colours/equipment as the {basis}
- extra_or_missing_parts: a limb, weapon or body part is duplicated, missing, melted or fused
- body_cropped: part of the character is cut off by the cell border or erased by background removal
- blur_or_smear: motion blur, ghosting or a smeared in-between makes the pose unclear
- background_residue: leftover background colour or blotches remain around the character's outline
- colour_contamination: a patch on the character has a colour that the same body part does not have in the {basis}
  (a stain, tint or blotch). A colour that part really has in the {basis} is not contamination.
  Inspect every part in the large images, small ones too (hands, feet, hair, face, weapon, accessories).
- pose_fits_neighbors: the pose is a plausible step between the cells before and after it
Use "unknown" when you cannot see enough to answer. Never guess hidden parts.
note: at most 12 words describing any defect and where it is, or "" if none. Answer with JSON only."""
REFERENCE_TEXT = {True: "In each large image the leftmost cell labelled REF is the character reference; compare each part with it.",
                  False: "There is no reference image; compare each cell with the other cells of the same character."}


class ObservationCacheMiss(Exception):
    """``observation_cache_only`` was requested and the observation is not cached: nothing is observed."""


# ---------- observer choice (local Codex catalog, no network) ----------

def catalog_path() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "models_cache.json"


def latest_luna() -> tuple[str | None, str | None]:
    """(model, None) for the newest listed Luna that takes images at medium, else (None, reason).

    Preflight only: the Codex CLI must be on PATH (looked up, never spawned) and the catalog Codex
    keeps locally is re-read on every call. It is never fetched or refreshed here, so "newest" means
    newest in that file. Only well-formed rows count, and no other model family is ever chosen."""
    if shutil.which("codex") is None:
        return None, "CODEX_CLI_MISSING"
    try:
        models = json.loads(catalog_path().read_text(encoding="utf-8"))["models"]
    except (OSError, ValueError, TypeError, KeyError):
        return None, "LUNA_CATALOG_UNREADABLE"
    found = []
    for m in models if isinstance(models, list) else []:
        if not isinstance(m, dict) or not isinstance(m.get("slug"), str):
            continue
        match = LUNA.fullmatch(m["slug"])
        modalities, levels = m.get("input_modalities"), m.get("supported_reasoning_levels")
        if (match and m.get("visibility") == "list" and isinstance(modalities, list) and "image" in modalities
                and isinstance(levels, list) and any(isinstance(r, dict) and r.get("effort") == OBSERVER_EFFORT for r in levels)):
            found.append((tuple(map(int, match[1].split("."))), m["slug"]))
    return (max(found)[1], None) if found else (None, "LUNA_NOT_IN_CATALOG")


# ---------- candidates and code measurements ----------

def uniform(start: int, end: int, count: int) -> list[int]:
    return [start + i * (end - start) // count for i in range(count)]


def windows(start: int, end: int, count: int, limit: int = MAX_CANDIDATES) -> list[list[int]]:
    """Disjoint neighbourhoods of each uniform position, so slot order is invariant."""
    base = uniform(start, end, count)
    radius = max(0, min(MAX_RADIUS, (limit // count - 1) // 2))
    out = []
    for k, centre in enumerate(base):
        lo = max(start, centre - radius, (base[k - 1] + centre) // 2 + 1 if k else start)
        hi = min(end - 1, centre + radius, (centre + base[k + 1] - 1) // 2 if k + 1 < count else end - 1)
        out.append(list(range(lo, hi + 1)))
    return out


def _alpha(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGBA"))


def measure(paths: dict[int, Path]) -> dict[int, dict]:
    """Cheap pixel facts. These are hints and code flags, never anatomy."""
    raw = {}
    for i, path in paths.items():
        rgba = _alpha(path)
        mask = rgba[..., 3] >= 8
        if not mask.any():
            raw[i] = {"empty": True, "edgeTouch": False, "area": 0, "height": 0, "sharpness": 0.0}
            continue
        ys, xs = np.nonzero(mask)
        grey = rgba[..., :3].astype(np.float32).mean(axis=2)
        grad = np.abs(np.diff(grey, axis=1))[mask[:, 1:] & mask[:, :-1]]
        raw[i] = {"empty": False, "area": int(mask.sum()), "height": int(ys.max() - ys.min() + 1),
                  "edgeTouch": bool(xs.min() == 0 or ys.min() == 0 or xs.max() == mask.shape[1] - 1 or ys.max() == mask.shape[0] - 1),
                  "sharpness": float(grad.mean()) if grad.size else 0.0}
    full = [m for m in raw.values() if not m["empty"]]
    med = {k: float(np.median([m[k] for m in full])) if full else 0.0 for k in ("area", "height", "sharpness")}
    for m in raw.values():
        for k in ("area", "height", "sharpness"):
            m[k + "Ratio"] = round(m[k] / med[k], 3) if med[k] else None
    return raw


def _crop_box(paths: dict[int, Path]) -> tuple[int, int, int, int]:
    """One union crop for every candidate, so size changes between cells stay visible."""
    boxes = []
    for path in paths.values():
        box = Image.fromarray(_alpha(path)[..., 3]).point(lambda a: 255 if a >= 8 else 0).getbbox()
        if box:
            boxes.append(box)
    with Image.open(next(iter(paths.values()))) as first:
        width, height = first.size
    if not boxes:
        return (0, 0, width, height)
    return (max(0, min(b[0] for b in boxes) - 6), max(0, min(b[1] for b in boxes) - 6),
            min(width, max(b[2] for b in boxes) + 6), min(height, max(b[3] for b in boxes) + 6))


def _tile(path: Path, box, size) -> Image.Image:
    with Image.open(path) as im:
        crop = im.convert("RGBA").crop(box)
    down = size[1] < crop.size[1]
    crop = crop.resize(size, Image.Resampling.LANCZOS if down else Image.Resampling.NEAREST)
    tile = Image.new("RGBA", crop.size, (200, 200, 200, 255))
    tile.alpha_composite(crop)
    return tile.convert("RGB")


def _save_bounded(sheet: Image.Image, dest: Path) -> dict:
    """Last-resort cap for degenerate inputs (e.g. a 5000x2 candidate): shrink the composed image to the
    edge limits. Normal sheets already fit and are saved untouched; a shrunk sheet records it."""
    w, h = sheet.size
    scale = min(1.0, IMAGE_MAX_EDGE / max(w, h), IMAGE_SHORT_EDGE / min(w, h))
    if scale < 1:
        sheet = sheet.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    return {"size": list(sheet.size), "downscaledToFit": scale < 1}


def _row_image(cells: list[tuple[str, Image.Image]], dest: Path) -> dict:
    label_h = 26
    sheet = Image.new("RGB", (sum(t.size[0] + 4 for _, t in cells), max(t.size[1] for _, t in cells) + label_h), (255, 255, 255))
    draw, font, x = ImageDraw.Draw(sheet), ImageFont.load_default(size=20), 0
    for label, tile in cells:
        sheet.paste(tile, (x, label_h))
        draw.text((x + 4, 2), label, fill=(0, 0, 0), font=font)
        x += tile.size[0] + 4
    return _save_bounded(sheet, dest)


def contact_sheet(paths: dict[int, Path], rows: list[list[int]], dest: Path, cell_height: int = 448) -> dict:
    """Overview sheet: every slot row with the same crop, fitted so Codex does not shrink it again."""
    box = _crop_box(paths)
    label_h = 26
    crop_w, crop_h = box[2] - box[0], box[3] - box[1]
    columns = max(len(r) for r in rows)
    # Both edges are capped (a wide crop is width-bound); rounding is settled by stepping down.
    cell_height = max(1, min(cell_height, IMAGE_MAX_EDGE // len(rows) - label_h - 4,
                             int((IMAGE_MAX_EDGE // columns - 4) * crop_h / crop_w)))
    def size(h):
        return columns * (max(1, round(crop_w * h / crop_h)) + 4), len(rows) * (h + label_h + 4)
    while cell_height > 1 and (max(size(cell_height)) > IMAGE_MAX_EDGE or min(size(cell_height)) > IMAGE_SHORT_EDGE):
        cell_height -= 1
    scale = cell_height / crop_h
    cell_w = max(1, round(crop_w * scale))
    sheet = Image.new("RGB", (columns * (cell_w + 4), len(rows) * (cell_height + label_h + 4)), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=20)
    for r, row in enumerate(rows):
        for c, index in enumerate(row):
            x, y = c * (cell_w + 4), r * (cell_height + label_h + 4)
            sheet.paste(_tile(paths[index], box, (cell_w, cell_height)), (x, y + label_h))
            draw.text((x + 4, y + 2), f"F{index:03d}", fill=(0, 0, 0), font=font)
    return {**_save_bounded(sheet, dest), "crop": list(box), "cellWidth": cell_w, "cellHeight": cell_height, "background": [200, 200, 200],
            "imageStage": "keyed-after-size-hold-and-repair"}


def detail_sheets(paths: dict[int, Path], rows: list[list[int]], reference: Path | None, directory: Path) -> dict:
    """One large image per slot row (REF cell first when a reference exists), each <= 2048 x 768."""
    box = _crop_box(paths)
    crop_w, crop_h = box[2] - box[0], box[3] - box[1]
    ref = None
    if reference:
        with Image.open(reference) as im:
            ref = im.convert("RGBA")
        rgba = np.asarray(ref)
        if rgba[..., 3].min() < 8:
            mask = rgba[..., 3] >= 8
        else:  # opaque reference on a flat canvas: crop to what differs from the corner colour
            mask = np.abs(rgba[..., :3].astype(np.int16) - rgba[0, 0, :3].astype(np.int16)).max(axis=2) > 40
        ys, xs = np.nonzero(mask)
        if xs.size:
            ref = ref.crop((max(0, xs.min() - 6), max(0, ys.min() - 6), min(ref.size[0], xs.max() + 7), min(ref.size[1], ys.max() + 7)))
    ref_aspect = ref.size[0] / ref.size[1] if ref else 0.0
    out = []
    for r, row in enumerate(rows):
        gaps = 4 * (len(row) + (1 if ref else 0))
        cell_h = max(1, int(min(DETAIL_MAX_CELL, (IMAGE_MAX_EDGE - gaps) / (len(row) * crop_w / crop_h + ref_aspect))))
        width = lambda h: len(row) * (max(1, round(crop_w * h / crop_h)) + 4) + (max(1, round(ref_aspect * h)) + 4 if ref else 0)
        while cell_h > 1 and width(cell_h) > IMAGE_MAX_EDGE:  # rounding can add a pixel or two per cell
            cell_h -= 1
        cell_w = max(1, round(crop_w * cell_h / crop_h))
        cells = []
        if ref:  # an extremely wide reference is squeezed into what is left rather than overflow
            ref_w = max(1, min(round(ref_aspect * cell_h), IMAGE_MAX_EDGE - len(row) * (cell_w + 4) - 4))
            ref_tile = Image.new("RGBA", (ref_w, cell_h), (200, 200, 200, 255))
            ref_tile.alpha_composite(ref.resize(ref_tile.size, Image.Resampling.LANCZOS))
            cells.append(("REF", ref_tile.convert("RGB")))
        cells += [(f"F{i:03d}", _tile(paths[i], box, (cell_w, cell_h))) for i in row]
        dest = directory / f"candidates.slot{r:02d}.png"
        out.append({"path": dest, "cellHeight": cell_h, "cellWidth": cell_w, **_row_image(cells, dest)})
    return {"crop": list(box), "reference": bool(ref), "images": out}


# ---------- observation (Luna, cached) ----------

def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _usage(stdout: str) -> tuple[dict | None, str | None, list[str]]:
    usage, thread, errors = None, None, []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        thread = event.get("thread_id") or thread
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        if event.get("type") in ("turn.failed", "error"):
            errors.append(str((event.get("error") or {}).get("message") or event.get("message"))[:500])
    return usage, thread, errors


def _rollout_model(thread: str | None) -> str | None:
    """Read which model the session actually ran from its rollout (not the request)."""
    if not thread:
        return None
    root = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    for path in sorted(root.rglob(f"*{thread}*.jsonl"), reverse=True)[:1]:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            payload = event.get("payload") if isinstance(event, dict) else None
            if isinstance(payload, dict) and event.get("type") == "turn_context" and payload.get("model"):
                return payload["model"]
    return None


def codex_observe(images: list[Path], prompt: str, directory: Path, model: str, effort: str) -> dict:
    """One ChatGPT-subscription Codex call, pinned to the requested model. No retry or fallback model."""
    try:
        allowed = _observer(f"{model}-{effort}") == (model, effort)
    except ValueError:
        allowed = False
    if not allowed:
        raise RuntimeError(json.dumps({"code": "OBSERVER_NOT_ALLOWED", "model": model, "effort": effort}))
    from sprite_gen.gen.base import provider_binary, provider_subprocess_env
    directory.mkdir(parents=True, exist_ok=True)
    schema = directory / "schema.json"
    schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
    answer = directory / "answer.json"
    with tempfile.TemporaryDirectory(prefix="observe-") as cwd:
        command = [provider_binary("codex"), "exec", "--ignore-user-config",
                   "-c", 'model_provider="openai"', "-c", 'forced_login_method="chatgpt"',
                   "-c", f'model_reasoning_effort="{effort}"',
                   "--json", "--sandbox", "read-only", "--skip-git-repo-check", "--color", "never",
                   "-m", model, "--output-schema", str(schema), "-o", str(answer), "-C", cwd]
        for image in images:
            command += ["-i", str(Path(image).resolve())]
        command.append("-")
        env = provider_subprocess_env()
        for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "CODEX_THREAD_ID",
                    "CODEX_INTERNAL_ORIGINATOR_OVERRIDE", "TYPESAFE_API_KEY"):  # removed judge's key, if still exported
            env.pop(key, None)
        (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
        started = time.monotonic()
        completed = subprocess.run(command, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                   env=env, timeout=OBSERVER_TIMEOUT_SECONDS)
    elapsed = round(time.monotonic() - started, 3)
    (directory / "codex-stdout.jsonl").write_text(completed.stdout or "", encoding="utf-8")
    (directory / "codex-stderr.txt").write_text(completed.stderr or "", encoding="utf-8")
    usage, thread, errors = _usage(completed.stdout or "")
    receipt = {"transport": "codex-exec", "billingRoute": "chatgpt-subscription", "requestedModel": model,
               "reasoningEffort": effort, "actualModel": _rollout_model(thread), "threadId": thread,
               "elapsedSeconds": elapsed, "usage": usage, "exitCode": completed.returncode, "errors": errors,
               "automaticRetry": False, "fallbackModel": None}
    if completed.returncode or not answer.is_file():
        raise RuntimeError(json.dumps({"code": "OBSERVER_FAILED", **receipt}, ensure_ascii=False))
    if receipt["actualModel"] not in (None, model):
        raise RuntimeError(json.dumps({"code": "OBSERVER_MODEL_MISMATCH", **receipt}, ensure_ascii=False))
    return {"text": answer.read_text(encoding="utf-8"), "receipt": receipt}


def parse_observations(text: str, ids: list[str]) -> tuple[dict, list[str]]:
    """Strict per-frame validation; anything malformed is simply missing (-> review)."""
    problems = []
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}, ["OBSERVATION_NOT_JSON"]
    items = data.get("frames") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return {}, ["OBSERVATION_SCHEMA"]
    out, seen = {}, set()
    for item in items:
        if not isinstance(item, dict) or item.get("id") not in ids:
            problems.append("OBSERVATION_UNKNOWN_ID")
            continue
        if item["id"] in seen:
            problems.append("OBSERVATION_DUPLICATE_ID")
            out.pop(item["id"], None)  # conflicting duplicates are not trusted either way
            continue
        seen.add(item["id"])
        out[item["id"]] = {k: item.get(k) if item.get(k) in ("yes", "no", "unknown") else None for k in PROBLEM}
        out[item["id"]]["note"] = str(item.get("note") or "")[:160]
    return out, problems


def _observer(name) -> tuple[str, str]:
    """The fixed comparison allowlist, or ``<model>-medium`` for the Luna the local catalog names
    newest right now (re-read here). Any other Luna id, and any non-string, fails before a call."""
    if isinstance(name, str) and name in OBSERVERS:
        return OBSERVERS[name]
    model = name[:-len(OBSERVER_EFFORT) - 1] if isinstance(name, str) and name.endswith("-" + OBSERVER_EFFORT) else None
    if model and LUNA.fullmatch(model) and latest_luna()[0] == model:
        return model, OBSERVER_EFFORT
    raise ValueError(f"observer must be one of {sorted(OBSERVERS)} or the newest catalog Luna at medium")


def observe(images: list[Path], reference: Path | None, ids: list[str], directory: Path, cache_dir: Path | None,
            call=None, *, observer: str) -> dict:
    """``images`` are the exact files sent, in order; their bytes (not paths) key the cache."""
    model, effort = _observer(observer)
    key_material = {"version": VERSION, "prompt": PROMPT_VERSION, "schema": SCHEMA, "observer": observer,
                    "model": model, "effort": effort, "imageSha256": [_sha(i) for i in images],
                    "referenceSha256": _sha(reference) if reference else None, "ids": ids}
    key = hashlib.sha256(json.dumps(key_material, sort_keys=True).encode()).hexdigest()
    cache = (cache_dir or directory) / "observations" / f"{key}.json"
    record = {"cacheKey": key, "keyMaterial": {k: v for k, v in key_material.items() if k != "schema"}}
    if cache.is_file():
        try:
            saved = json.loads(cache.read_text())
            frames, problems = parse_observations(saved["text"], ids)
            return {**record, "cacheHit": True, "frames": frames, "problems": problems, "receipt": saved.get("receipt"), "calls": 0}
        except (ValueError, KeyError, TypeError):
            pass  # A corrupt cache entry is ignored, never trusted.
    prompt = PROMPT.format(ids=", ".join(ids), last=len(images), reference=REFERENCE_TEXT[bool(reference)],
                           basis="reference" if reference else "other cells")
    try:
        reply = (call or partial(codex_observe, model=model, effort=effort))(images, prompt, directory / "observation")
    except subprocess.TimeoutExpired:
        return {**record, "cacheHit": False, "frames": {}, "problems": ["OBSERVATION_TIMEOUT"], "calls": 1}
    except (RuntimeError, OSError, ImportError) as exc:
        return {**record, "cacheHit": False, "frames": {}, "problems": ["OBSERVATION_FAILED"], "error": str(exc)[:2000], "calls": 1}
    frames, problems = parse_observations(reply["text"], ids)
    if frames:  # Only a parseable answer is cached; failures are re-observable later.
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"text": reply["text"], "receipt": reply["receipt"], "key": record["keyMaterial"]},
                                    ensure_ascii=False, indent=2))
    return {**record, "cacheHit": False, "frames": frames, "problems": problems, "receipt": reply["receipt"], "calls": 1}


# ---------- judgement ----------

def policy(obs: dict | None, metric: dict) -> tuple[str | None, list[str]]:
    """FrameRoom code decisions that no model may override."""
    if metric.get("empty"):
        return "reject", ["CODE_EMPTY_FRAME"]
    if not obs:
        return "review", ["OBSERVATION_MISSING"]
    missing = [k for k in PROBLEM if obs.get(k) is None]
    if missing:
        return "review", ["OBSERVATION_FIELD_MISSING:" + ",".join(missing)]
    if metric.get("edgeTouch") and obs["body_cropped"] == "no":
        return "review", ["CONFLICT_EDGE_TOUCH_VS_NOT_CROPPED"]
    defects = [k for k, bad in PROBLEM.items() if obs[k] == bad]
    unknown = [k for k in PROBLEM if obs[k] == "unknown"]
    if unknown:  # unknown never becomes keep or reject, whatever else is seen
        return "review", ["UNKNOWN:" + k for k in unknown] + ["OBSERVED:" + k for k in defects]
    return None, []


def rules(obs: dict, metric: dict) -> tuple[str, list[str]]:
    fixed, reasons = policy(obs, metric)
    if fixed:
        return fixed, reasons
    defects = [k for k, bad in PROBLEM.items() if obs[k] == bad]
    if defects:
        return "reject", ["OBSERVED:" + k for k in defects]
    return "keep", ["ALL_CHECKS_OK"]


# ---------- selection ----------

def boundaries(times: list, indices: list[int], start: int, end: int, loop: bool) -> list:
    """Display boundaries (ms from the first boundary) that always sum to the selected range.

    Each frame shows from its own source time to the next pick. A loop wraps the
    span before a moved first pick onto the last frame (it continues into the next
    cycle); a one-shot lets the first frame cover the range start instead.
    """
    if loop and indices[0] != start:
        marks = [times[i] for i in indices] + [times[end] + times[indices[0]] - times[start]]
    else:
        marks = [times[start], *[times[i] for i in indices[1:]], times[end]]
    return [m - marks[0] for m in marks]


def select(keyed: list[Path], start: int, end: int, count: int, times: list, directory: Path, *,
           loop: bool = True, reference: Path | None = None, cache_dir: Path | None = None,
           observe_call=None, observer: str | None = None, observation_cache_only: bool = False) -> tuple[list[int], dict]:
    """``observer`` None picks the newest catalog Luna; without one nothing is observed (code policy only).
    ``observation_cache_only`` never runs the observer: an uncached observation raises
    ``ObservationCacheMiss`` before any judgement (comparison reruns on existing observations)."""
    if observer is None:
        model, missing = latest_luna()
        effort = OBSERVER_EFFORT if model else None
        observer_record = {"id": f"{model}-{effort}" if model else None, "model": model, "effort": effort,
                           "source": "local-codex-catalog", "available": bool(model), **({"reason": missing} if missing else {})}
    else:
        model, effort = _observer(observer)
        observer_record = {"id": observer, "model": model, "effort": effort, "source": "request"}
    base = uniform(start, end, count)
    groups = windows(start, end, count)
    record = {"version": VERSION, "mode": "vision", "uniformSourceFrameIndices": base, "candidatePool": sum(map(len, groups)),
              "rules": RULES_VERSION, "observedImageStage": "keyed-after-size-hold-and-repair", "status": "uniform-kept",
              "observer": observer_record, "judge": {"requested": "rules", "backend": "rules"}}
    if all(len(g) == 1 for g in groups):
        record.update(reason="출력 장수에 비해 후보 범위가 없어 균등 위치를 유지했습니다.", slots=[])
        return base, record
    directory.mkdir(parents=True, exist_ok=True)
    pool = sorted({i for g in groups for i in g})
    metrics = measure({i: keyed[i] for i in pool})
    sheet = directory / "candidates.sheet.png"
    record["sheet"] = contact_sheet({i: keyed[i] for i in pool}, groups, sheet)
    details = detail_sheets({i: keyed[i] for i in pool}, groups, reference, directory)
    images = [sheet, *(d["path"] for d in details["images"])]
    record["sheet"]["details"] = [{"file": d["path"].name, **{k: d[k] for k in ("cellHeight", "cellWidth", "size", "downscaledToFit")}}
                                  for d in details["images"]]
    record["sheet"]["imageSha256"] = [_sha(i) for i in images]
    ids = [f"F{i:03d}" for i in pool]
    if not model:  # no usable Luna: no call, no other model; empty frames reject, the rest OBSERVATION_MISSING
        if observation_cache_only:
            raise ObservationCacheMiss(f"OBSERVATION_CACHE_MISS:{missing}")
        observed = {"skipped": True, "reason": missing, "cacheHit": False, "frames": {}, "problems": [], "calls": 0}
    else:
        if observation_cache_only:
            def observe_call(*_a, **_k):  # the guard itself: never a paid observer call
                raise RuntimeError("OBSERVATION_CACHE_ONLY")
        observed = observe(images, reference, ids, directory, cache_dir, observe_call, observer=f"{model}-{effort}"
                           if observer is None else observer)
        if observation_cache_only and not observed.get("cacheHit"):
            raise ObservationCacheMiss(f"OBSERVATION_CACHE_MISS:{observed['cacheKey']}")
    record["observation"] = {k: v for k, v in observed.items() if k != "frames"}
    obs = {i: observed["frames"].get(f"F{i:03d}") for i in pool}
    decisions = {}
    started = time.monotonic()
    for i in pool:
        label, reasons = rules(obs[i], metrics[i]) if obs[i] else policy(obs[i], metrics[i])
        decisions[i] = {"sourceFrameIndex": i, "sourceTimeMs": times[i], "metrics": metrics[i], "observation": obs[i],
                        "rules": {"label": label, "reasons": reasons}, "label": label, "reasons": reasons, "source": "rules"}
    record["judgeSeconds"] = round(time.monotonic() - started, 3)
    chosen, slots = [], []
    rank = {"keep": 0, "review": 1, "reject": 2}
    for k, (centre, group) in enumerate(zip(base, groups)):
        best = min(group, key=lambda i: (rank[decisions[i]["label"]], abs(i - centre), i))
        # Move only for evidence about the uniform frame (a reject, or a review the rules also
        # raise); a judge's low confidence alone must not reshuffle a clean slot.
        centre_label = decisions[centre]["label"]
        movable = centre_label == "reject" or (centre_label == "review" and decisions[centre]["rules"]["label"] != "keep")
        pick = best if movable and decisions[best]["label"] == "keep" else centre
        status = "keep" if decisions[pick]["label"] == "keep" else "review"
        reasons = [] if status == "keep" else (["NO_KEEP_CANDIDATE_UNIFORM_KEPT"] + decisions[centre]["reasons"])
        chosen.append(pick)
        slots.append({"slot": k, "uniformSourceFrameIndex": centre, "candidates": group, "chosen": pick,
                      "changed": pick != centre, "status": status, "reasons": reasons})
    record.update(slots=slots, decisions=[decisions[i] for i in pool], sequence=sequence_check(chosen, base, start, end, times, keyed, loop))
    record["counts"] = {label: sum(d["label"] == label for d in decisions.values()) for label in LABELS}
    record["changedSlots"] = sum(s["changed"] for s in slots)
    if record["sequence"]["reasons"] and record["changedSlots"]:
        # A sequence that loses timing coverage keeps the original path, with an explanation.
        for s in slots:
            if s["changed"]:  # status/reasons follow the uniform frame that is actually used again
                centre = s["uniformSourceFrameIndex"]
                s.update(chosen=centre, changed=False, status="keep" if decisions[centre]["label"] == "keep" else "review",
                         reasons=["SEQUENCE_REVERTED_UNIFORM_KEPT", *("SEQUENCE:" + r for r in record["sequence"]["reasons"]),
                                  *decisions[centre]["reasons"]])
        record.update(status="review", appliedSourceFrameIndices=base, changedSlots=0)
        return base, record
    record["status"] = ("applied" if record["changedSlots"] else
                        "review" if any(s["status"] == "review" for s in slots) else "uniform-kept")
    record["appliedSourceFrameIndices"] = chosen
    return chosen, record


def sequence_check(chosen: list[int], base: list[int], start: int, end: int, times: list, keyed: list[Path],
                   loop: bool = True) -> dict:
    """Order, timing coverage and loop seam of the chosen frames versus the uniform path."""
    reasons = []
    if chosen != sorted(set(chosen)) or len(chosen) != len(base):
        reasons.append("ORDER_OR_COUNT_CHANGED")
    step = (times[end] - times[start]) / len(base)
    bounds = boundaries(times, chosen, start, end, loop)
    gaps = [b - a for a, b in zip(bounds, bounds[1:])]
    worst = max(gaps) / step if step else None
    if worst is not None and worst > 1.75:
        reasons.append("TIMING_GAP_TOO_LONG")
    if min(gaps) <= 0:
        reasons.append("TIMING_NOT_INCREASING")

    def diff(a, b):
        return float(np.abs(_alpha(keyed[a]).astype(np.int16) - _alpha(keyed[b]).astype(np.int16)).mean())
    seam = lambda seq: diff(seq[-1], seq[0]) / (np.median([diff(a, b) for a, b in zip(seq, seq[1:])]) or 1.0)
    seam_chosen, seam_base = seam(chosen), seam(base)
    if loop and seam_chosen > max(2.0, seam_base * 1.5):
        reasons.append("LOOP_SEAM_WORSE")
    return {"durationsMs": [round(g) for g in gaps], "totalMs": round(bounds[-1] - bounds[0]),
            "maxGapRatio": round(worst, 3) if worst is not None else None, "seamRatio": round(float(seam_chosen), 3),
            "uniformSeamRatio": round(float(seam_base), 3), "reasons": reasons}
