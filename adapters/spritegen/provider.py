"""Single-call Codex subscription adapter, run inside the worker process group.

No generation runs during import/readiness. Caller owns jobs, leases, cancellation
and concurrency=1. Raw provider evidence stays in the attempt, never in API logs.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Callable

from PIL import Image

ENGINE_ROOT = Path(__file__).resolve().parents[2] / "engine" / "sprite-gen"
ENGINE_COMMIT = "b058341f7543f3adcbea227bd4e6b7587895b1bc"
ADAPTER_VERSION = "1.3.0"
DEFAULT_MODEL = "gpt-6-sol"


class ProviderError(Exception):
    def __init__(self, code: str, message: str, *, outcome_unknown: bool = False, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.outcome_unknown = outcome_unknown
        self.details = details or {}
        self.retryable = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    # Exclusive writes prevent accidental reuse/overwrite of a previous attempt.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _engine():
    import sprite_gen.gen as gen
    if not Path(gen.__file__).resolve().is_relative_to(ENGINE_ROOT.resolve()):
        raise ProviderError("provider.engine_mismatch", "프로젝트 전용 engine venv로 worker를 실행하세요.")
    return gen


def _models() -> list[str]:
    """Local catalog only; model listing does not make a network request."""
    root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    try:
        catalog = json.loads((root / "models_cache.json").read_text())
        models = [m["slug"] for m in catalog.get("models", [])
                  if isinstance(m.get("slug"), str) and m["slug"].startswith("gpt-")
                  and m.get("visibility") != "hide"]
        return list(dict.fromkeys([DEFAULT_MODEL, *models]))
    except (OSError, ValueError, TypeError):
        return [DEFAULT_MODEL]


def _login_probe() -> dict:
    """Read login status, never auth.json, tokens, or a generation endpoint."""
    checked = _now()
    binary = shutil.which("codex")
    if binary is None:
        return {"loginReady": False, "authMode": "unknown", "lastProbe": checked,
                "reason": "Codex CLI가 설치되어 있지 않습니다."}
    try:
        from sprite_gen.gen.base import provider_subprocess_env
        result = subprocess.run([binary, "login", "status"], capture_output=True, text=True,
                                encoding="utf-8", timeout=15, env=provider_subprocess_env())
    except (OSError, subprocess.SubprocessError):
        return {"loginReady": False, "authMode": "unknown", "lastProbe": checked,
                "reason": "Codex 로그인 상태를 확인하지 못했습니다."}
    # Exit zero alone is insufficient: an API-key login is a different billing route.
    text = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
    ready = result.returncode == 0 and "logged in using chatgpt" in text
    mode = "chatgpt" if ready else ("api-key" if "api key" in text or "api_key" in text else "unknown")
    return {"loginReady": ready, "authMode": mode, "lastProbe": checked,
            "reason": None if ready else "ChatGPT 계정으로 codex login이 필요합니다. API 키 경로는 사용하지 않습니다."}


def providers() -> list[dict]:
    """Capability declarations are distinct from login readiness and real success."""
    try:
        _engine()
        probe = _login_probe()
    except (ImportError, ProviderError):
        probe = {"loginReady": False, "authMode": "unknown", "lastProbe": _now(),
                 "reason": "프로젝트 전용 engine venv가 필요합니다."}
    return [
        {"providerId": "codex", "name": "Codex · ChatGPT 구독", "enabled": True,
         "available": probe["loginReady"], **probe,
         "billingRoute": "chatgpt-subscription", "quota": "unknown", "lastSuccess": None,
         "generationVerified": False, "defaultModel": DEFAULT_MODEL, "models": _models(),
         "capabilities": {
             "referenceRoles": ["identity", "style", "pose", "regeneration-target"], "references": True,
             "prompt": True, "model": True, "modelTarget": "codex-agent",
             "imageModelSelection": False, "quality": False, "resolution": False,
             "aspectRatio": False, "nativeAlphaRequest": True, "transparentOutputGuaranteed": False,
             "layoutGuide": True,
             "remoteCancel": False, "resultLookup": False,
             "scope": ["states", "sheet", "frame"], "frameCount": {"min": 1, "max": 24, "mode": "prompt-only"},
             "imagesPerCall": 1, "concurrency": 1, "automaticRetry": False, "fallback": False,
         }},
        {"providerId": "openai", "name": "OpenAI Images API", "enabled": False, "available": False,
         "loginReady": False, "billingRoute": "api-credit", "quota": "unknown", "lastProbe": None,
         "lastSuccess": None, "capabilities": {}, "reason": "호출별 유료 API 경로는 이 앱에서 활성화하지 않았습니다."},
        {"providerId": "grok", "name": "Grok", "enabled": False, "available": False,
         "loginReady": False, "billingRoute": "unknown", "quota": "unknown", "lastProbe": None,
         "lastSuccess": None, "capabilities": {}, "reason": "현재 앱에서 검증하지 않은 provider이며 fallback으로 사용하지 않습니다."},
    ]


def _validate(params: dict, reference: dict, regeneration_target: dict | None = None) -> tuple[str, int, str]:
    if params.get("providerId") != "codex":
        raise ProviderError("provider.unsupported", "providerId를 codex로 명시해야 합니다.")
    for option in ("quality", "resolution", "aspectRatio", "aspect_ratio"):
        if params.get(option) not in (None, ""):
            raise ProviderError("provider.unsupported_option", f"Codex는 {option} 설정을 지원하지 않습니다.",
                                details={"field": option})
    prompt = params.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ProviderError("provider.invalid_prompt", "생성 프롬프트를 입력하세요.")
    model = params.get("model") or DEFAULT_MODEL
    if not isinstance(model, str) or model not in _models():
        raise ProviderError("provider.unsupported_model", "Codex 모델 목록의 모델을 선택하세요.")
    count = params.get("frameCount", 1)
    if type(count) is not int or not 1 <= count <= 24:
        raise ProviderError("provider.invalid_frame_count", "요청 프레임 수는 1–24 정수여야 합니다.")
    if type(params.get("layoutGuide", False)) is not bool:
        raise ProviderError("provider.invalid_layout_guide", "layoutGuide는 참 또는 거짓이어야 합니다.")
    if params.get("layoutGuide", False) and count != 1:
        raise ProviderError("provider.invalid_layout_guide", "구도 가이드는 요청 프레임 수가 1장일 때 사용할 수 있습니다.")
    scope = params.get("scope", "states")
    if scope not in ("states", "sheet", "frame") or (scope == "frame" and count != 1):
        raise ProviderError("provider.invalid_scope", "단일 프레임 생성은 scope=frame, frameCount=1이 필요합니다.")
    if scope == "frame":
        frame_id = params.get("frameVersionId")
        if not isinstance(frame_id, str) or not frame_id or not isinstance(regeneration_target, dict):
            raise ProviderError("provider.regeneration_target_required", "재생성할 프레임과 원본 crop 참조가 필요합니다.")
        if regeneration_target.get("frameVersionId") != frame_id:
            raise ProviderError("provider.invalid_regeneration_target", "선택한 프레임과 재생성 참조가 일치하지 않습니다.")
        asset_id, digest = regeneration_target.get("imageAssetId"), regeneration_target.get("sha256")
        if (not isinstance(asset_id, str) or not asset_id or not isinstance(digest, str)
                or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower())):
            raise ProviderError("provider.invalid_regeneration_target", "재생성 참조의 imageAssetId와 SHA-256이 필요합니다.")
    elif regeneration_target is not None:
        raise ProviderError("provider.invalid_regeneration_target", "재생성 대상 참조는 scope=frame에서만 사용할 수 있습니다.")
    if reference.get("approval") != "approved" or not reference.get("identityAssetId"):
        raise ProviderError("provider.reference_unapproved", "identity 이미지가 있는 승인된 기준 참조가 필요합니다.")
    for field in ("styleAssetIds", "poseAssetIds"):
        if not isinstance(reference.get(field, []), list):
            raise ProviderError("provider.invalid_reference", f"{field}는 배열이어야 합니다.")
    return model, count, scope


def _prompt(params: dict, reference: dict, refs: list[dict], count: int) -> str:
    lines = [params["prompt"], "", "REFERENCE ROLES (attachment order):"]
    for i, ref in enumerate(refs, 1):
        rule = {"identity": "Preserve this character's identity and fixed traits.",
                "style": "Transfer rendering style only, never character identity, costume or anatomy.",
                "pose": "Use only pose/motion guidance; preserve the identity reference character.",
                "derived-guide": (
                    "Locally drawn layout aid, NOT user artwork, character identity or style. "
                    "Use its placement guides only; do not copy its lines, colors or background."
                ),
                "regeneration-target": (
                    "This is the selected frame to regenerate. Use its pose/action as the replacement target "
                    "and starting point, applying the requested corrections. This supplemental image is NOT "
                    "a new identity reference: the identity image and its fixed traits take priority over "
                    "this target whenever they conflict. Other pose references are supplemental guidance."
                )}[ref["role"]]
        lines.append(f"Image {i}: {ref['role']}. {rule}")
    for key in ("fixedTraits", "allowedChanges", "forbiddenTransfers", "facing"):
        if reference.get(key):
            lines.append(f"{key}: {json.dumps(reference[key], ensure_ascii=False)}")
    background = params.get("background")
    if background == "transparent":
        lines.append(
            "Request a genuinely transparent PNG with a real alpha channel from image_gen: "
            "use its transparent background option and preserve the generated alpha. "
            "The background pixels must be transparent, not a painted checkerboard, "
            "transparency grid, or flattened white/colored background."
        )
    elif background in ("white", "green", "magenta"):
        color = {"white": "#FFFFFF", "green": "#00FF00", "magenta": "#FF00FF"}[background]
        lines.append(
            f"Requested background: solid {background} ({color}). "
            "Use a uniform, flat background without gradients, texture, shadows or checkerboard. "
            "Keep the character silhouette separate from the background color."
        )
    elif background:
        lines.append(f"Requested background: {background}. This is a visual instruction; preserve the raw result.")
    output_instruction = (
        "Create exactly one PNG containing a single replacement for the selected regeneration-target frame."
        if params.get("scope") == "frame" else
        f"Create exactly one sprite sheet PNG containing {count} distinct animation frame(s)."
    )
    lines += ["", output_instruction,
              "Keep the same character scale and complete silhouette in every frame; do not crop feet or equipment.",
              "Separate frames clearly; do not add text, labels, grid lines or a painted checkerboard.",
              "Generate once only; do not make an additional generation attempt, retry, or switch providers."]
    return "\n".join(lines)


def generate(params: dict, reference: dict, asset_path: Callable[[str], Path], out_dir: Path,
             *, regeneration_target: dict | None = None) -> dict:
    """Synchronous, single engine call; worker launches us in its own process group.

    frameCount requests poses in ONE image. Returned image count and actual
    frame count must not be confused. Geometry/extraction is a later app step.
    For scope=frame, the worker resolves regeneration_target from the immutable
    job snapshot: frameVersionId, imageAssetId (original crop), and asset sha256.
    """
    params, reference = copy.deepcopy(params), copy.deepcopy(reference)
    regeneration_target = copy.deepcopy(regeneration_target)
    model, count, scope = _validate(params, reference, regeneration_target)
    engine = _engine()
    refs = []
    source_paths = []
    role_assets = [("identity", [reference["identityAssetId"]]),
                   ("style", reference.get("styleAssetIds", [])), ("pose", reference.get("poseAssetIds", []))]
    if regeneration_target is not None:
        role_assets.append(("regeneration-target", [regeneration_target["imageAssetId"]]))
    for role, ids in role_assets:
        for asset_id in ids:
            if not isinstance(asset_id, str) or not asset_id:
                raise ProviderError("provider.invalid_reference", "참조 asset ID가 올바르지 않습니다.")
            path = Path(asset_path(asset_id))
            try:
                with Image.open(path) as im:
                    im.verify()
                suffix = path.suffix.lower() if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") else ".png"
                digest = _hash(path)
                if role == "regeneration-target" and digest != regeneration_target["sha256"].lower():
                    raise ProviderError("provider.regeneration_target_changed", "재생성 대상 이미지의 hash가 snapshot과 다릅니다.")
                record = {"assetId": asset_id, "role": role, "sha256": digest,
                          "file": f"references/{len(refs) + 1:03d}-{role}{suffix}"}
                if role == "regeneration-target":
                    record["frameVersionId"] = regeneration_target["frameVersionId"]
                refs.append(record)
                source_paths.append(path)
            except (OSError, ValueError) as exc:
                raise ProviderError("provider.invalid_reference", "참조 이미지를 읽을 수 없습니다.") from exc
    probe = _login_probe()
    if not probe["loginReady"]:
        raise ProviderError("provider.not_ready", probe["reason"])
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    attempt = out_dir / "provider-attempt"
    try:
        attempt.mkdir()  # no overwrite, stale image reuse, or accidental second submission
    except FileExistsError as exc:
        raise ProviderError("provider.attempt_exists", "이미 사용한 생성 디렉터리입니다. 기존 요청 결과를 확인하세요.") from exc
    (attempt / "references").mkdir()
    copied = []
    for ref, source in zip(refs, source_paths):
        dest = attempt / ref["file"]
        shutil.copyfile(source, dest)
        if _hash(dest) != ref["sha256"]:
            raise ProviderError("provider.reference_changed", "참조 원본이 변경되었습니다. 새 snapshot으로 요청하세요.")
        copied.append(dest)
    guide = None
    if params.get("layoutGuide", False):
        # Draw before the submission marker: this local operation cannot incur a
        # provider charge. Snapshot the actual attachment, not an engine side effect.
        relative = f"references/{len(refs) + 1:03d}-derived-guide.png"
        guide_path = attempt / relative
        try:
            cell = engine.draw_layout_guide(guide_path, None)
            guide_text = engine.layout_guide_text(cell)
            guide_hash = _hash(guide_path)
        except (SystemExit, Exception) as exc:
            raise ProviderError("provider.layout_guide_failed", "로컬 구도 가이드를 만들지 못했습니다. 생성 요청은 전송하지 않았습니다.") from exc
        guide = {"file": relative, "sha256": guide_hash, "cell": cell, "prompt": guide_text}
        refs.append({"assetId": None, "role": "derived-guide", "file": relative, "sha256": guide_hash,
                     "origin": {"kind": "local-layout-guide", "generator": "sprite_gen.gen.draw_layout_guide",
                                "aspectRatio": None, "cell": cell}})
        copied.append(guide_path)
    engine_prompt = _prompt(params, reference, refs, count)
    if guide is not None:
        engine_prompt += "\n\n" + guide["prompt"]
    # Match generate_image's boundary normalization before hashing/snapshotting.
    # The caller's original text remains untouched in params and snapshot.prompt.
    engine_prompt = engine_prompt.strip()
    snapshot = {"schemaVersion": 1, "adapterVersion": ADAPTER_VERSION, "engineCommit": ENGINE_COMMIT,
                "providerId": "codex", "billingRoute": "chatgpt-subscription", "model": model,
                "params": params, "reference": reference, "references": refs, "prompt": params["prompt"],
                "regenerationTarget": regeneration_target,
                "enginePrompt": engine_prompt, "promptHash": hashlib.sha256(engine_prompt.encode()).hexdigest(),
                "scope": scope, "requestedFrameCount": count, "requestedImageCount": 1,
                "requestedNativeAlpha": params.get("background") == "transparent",
                "layoutGuide": {"enabled": guide is not None, **(guide or {})},
                "concurrency": 1, "automaticRetry": False, "fallback": False,
                "engineOptions": {"transparent": False, "trim_alpha": False, "facing": None,
                                  "facing_fix": "none", "keep_session": True,
                                  "layout_guide": False}, "createdAt": _now()}
    _write_json(attempt / "request-snapshot.json", snapshot)
    # Written BEFORE entering the engine. If this process is killed, worker must
    # retain unknown acceptance, never infer failure from missing result.json.
    _write_json(attempt / "submission.json", {"state": "may-have-submitted", "startedAt": _now(),
                                             "providerId": "codex", "requestHash": _hash(attempt / "request-snapshot.json")})
    try:
        result = engine.generate_image("codex", engine_prompt, attempt / "generated.png", refs=copied,
                                       model=model, quality=None, resolution=None, facing=None,
                                       facing_fix="none", transparent=False, trim_alpha=False,
                                       keep_session=True, workdir=attempt, layout_guide=False)
        raw_receipt = result.to_dict()
        _write_json(attempt / "engine-receipt.json", raw_receipt)
        with Image.open(result.out) as image:
            image.load()
            if image.format != "PNG":
                raise ValueError("provider output is not PNG")
            dimensions = {"width": image.width, "height": image.height}
            # Measure decoded output, never infer alpha from the request or the
            # provider's claim. RGB/checkerboard results remain preserved for review.
            histogram = image.convert("RGBA").getchannel("A").histogram()
            alpha_stats = {"transparent": histogram[0], "partial": sum(histogram[1:255]),
                           "opaque": histogram[255]}
            alpha_channel_present = "A" in image.getbands() or "transparency" in image.info
        receipt = {"providerId": "codex", "billingRoute": "chatgpt-subscription", "model": result.model,
                   "sessionId": result.session_id, "elapsedSeconds": result.elapsed_seconds,
                   "requestedImageCount": 1, "returnedImageCount": 1, "requestedFrameCount": count,
                   "actualFrameCount": None, "sha256": _hash(result.out), "rawSha256": _hash(result.raw),
                   **dimensions, "alphaStats": alpha_stats, "alphaChannelPresent": alpha_channel_present,
                   "engineExtra": copy.deepcopy(result.extra),
                   "engineReceiptFile": "provider-attempt/engine-receipt.json",
                   "requestSnapshotFile": "provider-attempt/request-snapshot.json", "completedAt": _now()}
        _write_json(attempt / "receipt.json", receipt)
        return {"paths": [str(result.out)], "receipt": receipt, "requestSnapshot": snapshot,
                "providerId": "codex", "model": model}
    except (SystemExit, Exception) as exc:
        # After entry, even a timeout/nonzero exit may hide an accepted call.
        # No provider logs/secrets/absolute auth paths are exposed through errors.
        _write_json(attempt / "failure.json", {"code": "provider.outcome_unknown", "outcomeUnknown": True,
                                              "exceptionType": type(exc).__name__, "failedAt": _now()})
        raise ProviderError("provider.outcome_unknown", "생성 요청의 접수·완료 여부를 확인하지 못했습니다. 자동 재시도하지 않습니다.",
                            outcome_unknown=True, details={"evidenceDirectory": "provider-attempt"}) from exc
