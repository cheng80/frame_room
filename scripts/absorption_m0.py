"""M0 기능 흡수 기준: upstream 기능 inventory, 기능 대장 완전성, 파일 단위 이식 목록, 회귀 기준 manifest.

upstream 트리·프로젝트 자료·엔진은 읽기만 한다. 출력은 명령에 지정한 JSON과 replay 작업 폴더뿐이다.
생성 provider 호출은 없다. `fetch-upstream`만 GitHub에서 고정 commit을 내려받는다.

  engine/sprite-gen/.venv/bin/python scripts/absorption_m0.py fetch-upstream <tmp>
  engine/sprite-gen/.venv/bin/python scripts/absorption_m0.py ledger-check [--upstream <tmp>/v2.45.3]
  engine/sprite-gen/.venv/bin/python scripts/absorption_m0.py port-plan --upstream-root <tmp> --out <json> | --verify <json>
  engine/sprite-gen/.venv/bin/python scripts/absorption_m0.py function-plan --upstream-root <tmp> --out <json> | --verify <json>
  engine/sprite-gen/.venv/bin/python scripts/absorption_m0.py baseline --write <json> | --verify <json>
  engine/sprite-gen/.venv/bin/python scripts/absorption_m0.py replay --manifest <json> --work <tmp>
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import tempfile
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine" / "sprite-gen"
LEDGER = ROOT / "docs" / "product" / "absorption" / "m0-feature-ledger.json"
REPOSITORY = "https://github.com/aldegad/sprite-gen"
PINS = {"v2.12.1": "b058341f7543f3adcbea227bd4e6b7587895b1bc",
        "v2.34.0": "1fc35090fa9c359bc96d1287fbc32f733acaa7e4",
        "v2.45.3": "59b2738a2e76ed7043d9691a230396ed6374a336"}
STATUSES = ("미조사", "구현 예정", "구현 중", "검증 대기", "완료", "차단")
PHASES = ("M0", "M1", "M2", "M3", "M4", "M5", "M6")
INVENTORY_SOURCES = ("sprite_gen/cli.py", "sprite_gen/_modules.py", "docs/README.md", "pyproject.toml")
# 현행 영상 처리 정책. 이 값과 다른 version은 현재 코드로 재실행하지 않는다(조회 전용).
CURRENT_VIDEO_PROCESSING = "video-processing-v4-sprite-gen-2.34"
CURRENT_VIDEO_EXTRACTION = "video-v4-2.34-finished"
CURRENT_QUALITY_VERSION = "2.34.0"
# process_clip이 저장하지 않던 시기의 옵션은 당시와 같은 현행 기본값으로만 해석한다.
IMPLIED_OPTION_DEFAULTS = {"frameSelection": "uniform", "frameJudge": "rules"}
CURRENT_OPTION_KEYS = {"state", "key", "loopMode", "maxFrames", "repairMode", "facing", "direction", "bodyPlan",
                       "between", "startFoot", "frameSelection", "frameJudge", "frameObserver", "observationCacheOnly",
                       "startIndex", "targetFrameCount", "targetDurationMs", "startFrame", "endFrame"}
# v2.45.3 소스를 읽고 확인한 프로젝트 보호 계약과의 충돌. 교체·병합 시 로컬 적응이 필요하다.
CONTRACT_CONFLICTS = {
    "sprite_gen/gen/video.py": "generate_video가 429 거절 POST를 다시 보낸다(retry.ask). 앱 adapter가 이 함수를 직접 호출하므로 그대로 교체하면 POST 1회 계약 위반 -> 로컬 패치로 POST 재전송 비활성, GET/다운로드 재시도만 채택",
    "sprite_gen/gen/retry.py": "POST 재전송 정책 포함. GET·다운로드 backoff만 사용하고 POST 재전송 경로는 앱에서 막는다",
    "sprite_gen/gen/__init__.py": "provider_fallback과 저장된 기본값(workflow.preferences) 해석. 자동 provider 전환·전역 설정 사용 금지 계약 + 접수 불명 재시도 제거 로컬 패치 유지",
    "sprite_gen/gen/codex_provider.py": "ChatGPT 구독 경로 고정·API 키/부모 thread 환경 제거·원문 보존 로컬 패치 유지(API 키 과금 경로 자동 사용 금지)",
    "sprite_gen/workflow/preferences.py": "SPRITE_GEN_CONFIG_DIR 또는 사용자 홈 설정을 읽는다. 앱은 프로젝트 설정만 사용하므로 gen 경로에서 차단 또는 프로젝트 범위로 주입",
    "sprite_gen/frames/cutout.py": "cyan 자동 감지·명시 선택 로컬 패치 유지",
    "sprite_gen/frames/extract.py": "로컬 conform_registered_row(등록 시트 행 공통 축소) 추가 유지 후 3-way 병합",
}
FORBIDDEN_TEXT = re.compile(r"/Users/|/home/[a-z]|[A-Za-z]:\\\\|sk-[A-Za-z0-9]{16}|xai-[A-Za-z0-9]{16}|Bearer [A-Za-z0-9]")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def rel(path: pathlib.Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def guard_output(path: pathlib.Path, *, replace: bool = False, directory: bool = False, forbidden: tuple = ()) -> pathlib.Path:
    """출력이 사용자 자료·소스·기존 결과를 덮지 않게 한다. 저장소 안에서는 docs/product/absorption/ 파일만 허용."""
    raw = pathlib.Path(path).absolute()
    if raw.is_symlink():
        raise SystemExit(f"refused output: symlink {path}")
    resolved = raw.resolve()
    for root in (*forbidden, ROOT / ".data"):
        if resolved.is_relative_to(pathlib.Path(root).resolve()):
            raise SystemExit(f"refused output: inside protected input {root}")
    if resolved.is_relative_to(ROOT) and (directory or resolved.relative_to(ROOT).parts[:3] != ("docs", "product", "absorption")):
        raise SystemExit(f"refused output: repository path outside docs/product/absorption/ ({path})")
    if directory:
        if resolved.exists() and (not resolved.is_dir() or any(resolved.iterdir())):
            raise SystemExit(f"refused output: work directory must be new or empty ({path}); earlier caches are never reused")
    elif resolved.exists() and not replace:
        raise SystemExit(f"refused output: {path} exists; pass --replace to re-baseline deliberately")
    return resolved


def dump(path: pathlib.Path, value) -> None:
    """새 임시 파일(O_EXCL)에 쓰고 rename으로 게시한다. 고정 이름 임시 파일·symlink를 따라가 다른 파일을 덮지 않는다."""
    text = json.dumps(value, ensure_ascii=False, indent=1) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)  # rename은 대상이 symlink여도 링크 자체를 바꾸고 링크 대상은 건드리지 않는다
    except BaseException:
        pathlib.Path(name).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- upstream inventory

def _git_blob(path: pathlib.Path) -> str:
    data = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def verify_tree(repo: pathlib.Path, commit: str, out: pathlib.Path) -> list[str]:
    """Every file of `out` must be exactly the pinned commit's tree (git blob ids), nothing more or less."""
    listing = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "-z", commit], check=True, capture_output=True).stdout.decode()
    expected = {}
    for line in filter(None, listing.split("\0")):
        meta, name = line.split("\t", 1)
        expected[name] = meta.split()[2]
    actual = {p.relative_to(out).as_posix(): _git_blob(p) for p in out.rglob("*") if p.is_symlink() or p.is_file()}
    return [f"{name}: tree differs from {commit[:12]}" for name in sorted(set(expected) | set(actual)) if expected.get(name) != actual.get(name)]


def fetch_upstream(dest: pathlib.Path) -> None:
    repo = dest / "repo"
    if not repo.is_dir():
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", REPOSITORY + ".git"], check=True)
    for tag, commit in PINS.items():
        subprocess.run(["git", "-C", str(repo), "fetch", "-q", "--depth", "1", "origin", commit], check=True)
        out = dest / tag
        if not out.is_dir():
            out.mkdir(parents=True)
            archive = subprocess.run(["git", "-C", str(repo), "archive", commit], check=True, capture_output=True).stdout
            subprocess.run(["tar", "-x", "-C", str(out)], input=archive, check=True)
        errors = verify_tree(repo, commit, out)  # an existing directory is accepted only when it is exactly the pin
        if errors:
            raise SystemExit(f"FAIL {tag}: {len(errors)} files differ from the pinned commit, e.g. {errors[0]}")
        print(f"OK {tag} {commit} -> {out} (tree verified)")


def _module_of(path: pathlib.Path, root: pathlib.Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def extract_inventory(root: pathlib.Path) -> dict:
    """Public surface of one upstream tree, read from source text only (no import)."""
    tree = ast.parse((root / "sprite_gen/cli.py").read_text())
    imports, commands = {}, {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sprite_gen"):
            for alias in node.names:
                imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "COMMANDS":
            for key, value in zip(node.value.keys, node.value.values):
                run = value.elts[2]
                commands[key.value] = imports[run.value.id] if isinstance(run, ast.Attribute) else run.id
    taxonomy = {}
    for node in ast.parse((root / "sprite_gen/_modules.py").read_text()).body:
        target = node.targets[0] if isinstance(node, ast.Assign) else getattr(node, "target", None)
        if getattr(target, "id", "") in ("MODULE_DOMAIN", "PIPELINES", "TOOL_GROUPS", "WORKFLOWS"):
            taxonomy[target.id] = ast.literal_eval(node.value)
    index = (root / "docs/README.md").read_text()
    docs = sorted({m for m in re.findall(r"\]\(([A-Za-z0-9_.-]+\.md)(?:#[^)]*)?\)", index)} - {"README.md"})
    package = root / "sprite_gen"
    entrypoints = sorted(_module_of(p, root) for p in package.rglob("*.py")
                         if re.search(r"__name__\s*==\s*['\"]__main__['\"]", p.read_text()) and p.name != "cli.py")
    scripts = {}
    for p in sorted((root / "scripts").rglob("*")):
        if p.is_file() and p.suffix in (".py", ".sh"):
            target = re.search(r"sprite_gen(?:\.[a-z_]+)+", p.read_text())
            scripts[p.relative_to(root).as_posix()] = target.group(0) if target else None
    retired = sorted(flag for p in package.rglob("*.py")
                     for group in re.findall(r"add_argument\(((?:\"--[^\"]+\",\s*)+)dest=\"_retired", p.read_text())
                     for flag in re.findall(r"\"(--[^\"]+)\"", group))
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    pipeline_verbs = sorted({v for group in ("PIPELINES", "TOOL_GROUPS", "WORKFLOWS") for item in taxonomy[group] for v in item["verbs"]})
    return {"sources": {name: sha256(root / name) for name in INVENTORY_SOURCES},
            "consoleScripts": sorted(project.get("scripts", {})),
            "commands": dict(sorted(commands.items())),
            "moduleDomain": dict(sorted(taxonomy["MODULE_DOMAIN"].items())),
            "catalogVerbs": pipeline_verbs,
            "docIndex": docs,
            "moduleEntrypoints": entrypoints,
            "scriptWrappers": scripts,
            "retiredFlags": retired}


# ---------------------------------------------------------------- ledger completeness

def check_ledger(ledger: dict, upstream: pathlib.Path | None = None) -> list[str]:
    errors = []
    inv = ledger["inventory"]
    if ledger["upstream"]["commit"] != PINS["v2.45.3"]:
        errors.append("upstream commit pin mismatch")
    if upstream is not None:
        fresh = extract_inventory(upstream)
        for key in fresh:
            if fresh[key] != inv.get(key):
                errors.append(f"frozen inventory differs from upstream tree: {key}")
    entries = ledger["entries"]
    ids = [e["id"] for e in entries]
    errors += [f"duplicate entry id: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    covered = lambda field: {x for e in entries for x in e["upstream"].get(field, [])}
    modules, docs, aliases = covered("modules"), covered("docs"), covered("aliases")
    leaves = {m.rsplit(".", 1)[-1] for m in modules}
    command_entries = [e["upstream"]["command"] for e in entries if e["kind"] == "command"]
    for name in inv["commands"]:
        if command_entries.count(name) != 1:
            errors.append(f"command needs exactly one ledger entry: {name}")
    errors += [f"ledger command not in upstream: {n}" for n in command_entries if n not in inv["commands"]]
    errors += [f"catalog verb is not a command: {v}" for v in inv["catalogVerbs"] if v not in inv["commands"]]
    errors += [f"command module not mapped: {n} -> {m}" for n, m in inv["commands"].items() if m not in modules]
    errors += [f"taxonomy module not mapped: {m}" for m in inv["moduleDomain"] if m not in leaves]
    errors += [f"module entrypoint not mapped: {m}" for m in inv["moduleEntrypoints"] if m not in modules]
    errors += [f"indexed doc not mapped: {d}" for d in inv["docIndex"] if d not in docs]
    errors += [f"script alias not mapped: {s}" for s in inv["scriptWrappers"] if s not in aliases]
    retired = covered("retired")
    errors += [f"retired flag not mapped: {f}" for f in inv["retiredFlags"] if f not in retired]
    errors += [f"retired flag recorded as supported alias: {f}" for f in inv["retiredFlags"] if f in aliases]
    every_alias = [a for e in entries for a in e["upstream"].get("aliases", [])]
    errors += [f"alias mapped to more than one entry: {a}" for a in sorted({a for a in every_alias if every_alias.count(a) > 1})]
    errors += [f"console script not mapped: {c}" for c in inv["consoleScripts"] if c not in aliases]
    for e in entries:
        where = e["id"]
        if e["status"] not in STATUSES:
            errors.append(f"{where}: invalid status {e['status']}")
        if e["phase"] not in PHASES:
            errors.append(f"{where}: invalid phase {e['phase']}")
        for field in ("entry", "api", "worker", "storage", "output", "recovery"):
            if not isinstance(e["app"].get(field), str) or not e["app"][field].strip():
                errors.append(f"{where}: app.{field} must name the current path or 'none'")
        evidence = e["tests"].get("appEvidence", [])
        if e["status"] == "완료" and not evidence:
            errors.append(f"{where}: 완료 requires app test evidence")
        if e["status"] in ("완료", "검증 대기") and e["coverage"] == "none":
            errors.append(f"{where}: {e['status']} without any app path")
        if e["status"] == "차단" and not e.get("blockers"):
            errors.append(f"{where}: 차단 requires blockers")
        for path in e["tests"].get("existing", []) + evidence + e["app"].get("files", []):
            if not (ROOT / path.split("::")[0]).exists():
                errors.append(f"{where}: referenced local path missing: {path}")
    text = json.dumps(ledger, ensure_ascii=False)
    if FORBIDDEN_TEXT.search(text):
        errors.append("ledger contains an absolute local path or credential-like text")
    return errors


def ledger_summary(ledger: dict) -> dict:
    count = lambda key: {k: sum(1 for e in ledger["entries"] if e[key] == k) for k in sorted({e[key] for e in ledger["entries"]})}
    return {"entries": len(ledger["entries"]), "commands": len(ledger["inventory"]["commands"]),
            "byStatus": count("status"), "byPhase": count("phase"), "byKind": count("kind"), "byCoverage": count("coverage")}


# ---------------------------------------------------------------- port plan

def _tree(root: pathlib.Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted(root.rglob("*")) if p.is_file()}


def _local_engine() -> dict[str, str]:
    names = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "engine/sprite-gen"], check=True,
                           capture_output=True).stdout.decode().split("\0")
    return {n.removeprefix("engine/sprite-gen/"): sha256(ROOT / n) for n in names if n and (ROOT / n).is_file()}


def app_engine_modules() -> list[str]:
    found = set()
    for path in [*ROOT.glob("adapters/**/*.py"), *ROOT.glob("services/**/*.py"), *ROOT.glob("alignment/*.py")]:
        text = path.read_text()
        found |= {"sprite_gen." + m for m in re.findall(r"_engine\(\s*['\"]([a-z_.]+)['\"]\s*\)", text)}
        found |= {"sprite_gen" for _ in re.findall(r"provider\._engine\(\)|_engine\(\)\s*$", text, re.M)}
        for module, names in re.findall(r"from (sprite_gen(?:\.[a-z_]+)*) import ([A-Za-z_, ]+)", text):
            for name in (n.strip() for n in names.split(",")):
                candidate = f"{module}.{name}"
                found.add(candidate if _module_file(candidate, ENGINE) else module)
    return sorted(found)


def _module_file(module: str, root: pathlib.Path) -> str | None:
    base = module.replace(".", "/")
    for name in (base + ".py", base + "/__init__.py"):
        if (root / name).is_file():
            return name
    return None


def _imports(path: pathlib.Path, root: pathlib.Path) -> set[str]:
    package = _module_of(path, root) if path.name == "__init__.py" else _module_of(path, root).rsplit(".", 1)[0]
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names if a.name.startswith("sprite_gen")}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[:len(parts) - node.level + 1] + ([base] if base else []))
            if base.startswith("sprite_gen"):
                for alias in node.names:
                    found.add(f"{base}.{alias.name}" if _module_file(f"{base}.{alias.name}", root) else base)
    return {m for m in found if _module_file(m, root)}


def dependency_closure(root: pathlib.Path, starts: list[str]) -> list[str]:
    seen, stack = set(), [m for m in starts if _module_file(m, root)]
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        stack += _imports(root / _module_file(module, root), root) - seen
    return sorted(_module_file(m, root) for m in seen)


def _kind(path: str) -> str:
    return "code" if path.startswith("sprite_gen/") else "test" if path.startswith("tests/") else \
        "doc" if path.startswith("docs/") or path.endswith(".md") else "other"


def classify_file(shas: dict, patch_base: str | None) -> tuple[str, str]:
    """(localOrigin, action) for one path. shas keys: v2.12.1, v2.34.0, v2.45.3, local (None = absent)."""
    local, target = shas["local"], shas["v2.45.3"]
    if local is None:
        return "absent", "add" if target else "not-applicable"
    origin = next((t for t in ("v2.45.3", "v2.34.0", "v2.12.1") if shas[t] == local), "local-patch")
    if target is None:
        return origin, "local-only" if origin == "local-patch" and not (shas["v2.34.0"] or shas["v2.12.1"]) else "upstream-removed"
    if origin == "v2.45.3":
        return origin, "reuse"
    if origin != "local-patch":
        return origin, "replace"
    if patch_base is None:
        return origin, "unrecorded-local-change"
    return origin, "keep-local" if patch_base == target else "merge"


def build_port_plan(upstream_root: pathlib.Path, ledger: dict) -> dict:
    for tag, commit in PINS.items():
        if verify_tree(upstream_root / "repo", commit, upstream_root / tag):
            raise SystemExit(f"upstream {tag} is not the pinned tree; run fetch-upstream first")
    trees = {tag: _tree(upstream_root / tag) for tag in PINS}
    local = _local_engine()
    lock = json.loads((ROOT / "engine/engine-lock.json").read_text())
    bases = {p["path"]: p["upstreamSha256"] for p in lock["patches"]}
    app = app_engine_modules()
    target_root = upstream_root / "v2.45.3"
    app_target = set(dependency_closure(target_root, app))
    app_local = set(dependency_closure(ENGINE, app))
    owners = {}
    for e in ledger["entries"]:
        for module in e["upstream"].get("modules", []):
            name = _module_file(module, target_root) or _module_file(module, ENGINE)
            if name:
                owners.setdefault(name, []).append(e["id"])
    files = []
    for path in sorted(set(local) | set(trees["v2.34.0"]) | set(trees["v2.45.3"])):
        shas = {**{t: trees[t].get(path) for t in PINS}, "local": local.get(path)}
        origin, action = classify_file(shas, bases.get(path))
        row = {"path": path, "kind": _kind(path), "sha256": shas, "localOrigin": origin, "action": action,
               "lockPatch": path in bases, "appImports": path in app_local or path in app_target,
               "appDependencyIn": [n for n, s in (("local", app_local), ("v2.45.3", app_target)) if path in s],
               "features": sorted(set(owners.get(path, [])))}
        if path in CONTRACT_CONFLICTS:
            row["contractConflict"] = CONTRACT_CONFLICTS[path]
        if path.endswith(".py") and shas["v2.45.3"]:
            row["importsAt245"] = sorted(_module_file(m, target_root) for m in _imports(target_root / path, target_root))
        files.append(row)
    deps = {t: tomllib.loads((upstream_root / t / "pyproject.toml").read_text())["project"] for t in PINS}
    deps["local"] = tomllib.loads((ENGINE / "pyproject.toml").read_text())["project"]
    dep = lambda p: sorted(p.get("dependencies", []))
    extras = lambda p: {k: sorted(v) for k, v in sorted(p.get("optional-dependencies", {}).items())}
    count = {}
    for row in files:
        count.setdefault(row["kind"], {}).setdefault(row["action"], 0)
        count[row["kind"]][row["action"]] += 1
    return {"schema": "frame-room-absorption-port-plan-v1",
            "pins": {t: {"commit": c, "fileCount": len(trees[t]), "treeDigest": digest(trees[t])} for t, c in PINS.items()},
            "local": {"engineVersion": lock["engineVersion"], "commit": lock["commit"], "qualityVersion": lock["qualityVersion"],
                      "fileCount": len(local), "treeDigest": digest(local), "lockSha256": sha256(ROOT / "engine/engine-lock.json")},
            "actions": {"reuse": "local == v2.45.3; app 연결·시험만 확인",
                        "replace": "local == v2.34.0/v2.12.1 원본, 로컬 패치 없음; v2.45.3으로 교체 후 호출자 회귀",
                        "keep-local": "로컬 패치 유지, upstream 기준 파일이 그대로라 충돌 없음",
                        "merge": "로컬 패치와 upstream 변경이 모두 있음; 3-way 병합·보호 계약 재확인",
                        "add": "v2.45.3 신규 파일; 기능 단계에서 추가",
                        "upstream-removed": "v2.45.3에서 삭제; 호출자 정리 또는 로컬 보존 결정",
                        "local-only": "upstream에 없는 로컬 파일",
                        "unrecorded-local-change": "lock에 없는 로컬 변경(무결성 위반)"},
            "summary": count,
            "appEngineModules": app,
            "dependencies": {t: {"python": p.get("requires-python"), "dependencies": dep(p), "optional": extras(p)} for t, p in deps.items()},
            "files": files}


def verify_port_plan(plan: dict) -> list[str]:
    local = _local_engine()
    errors = [f"local engine file changed since plan: {r['path']}" for r in plan["files"] if r["sha256"]["local"] != local.get(r["path"])]
    errors += [f"local engine file not in plan: {p}" for p in sorted(set(local) - {r["path"] for r in plan["files"]})]
    if plan["local"]["lockSha256"] != sha256(ROOT / "engine/engine-lock.json"):
        errors.append("engine-lock.json changed since plan")
    if plan["appEngineModules"] != app_engine_modules():
        errors.append("app engine imports changed since plan")
    return errors


# ---------------------------------------------------------------- function-level port grounds

ENV_READ = re.compile(r"""(?:environ\.get\(|environ\[|getenv\()\s*['"]?([A-Z][A-Z0-9_]+)""")  # 상수 이름(…_ENV)도 그대로 기록


def _app_files() -> list[pathlib.Path]:
    return sorted({*ROOT.glob("adapters/**/*.py"), *ROOT.glob("services/**/*.py"), *ROOT.glob("alignment/*.py")})


def _short(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def definitions(path: pathlib.Path) -> dict[str, dict]:
    """Module-level functions, classes, methods, values and re-exports, digested without line numbers."""
    out = {}

    def add(name, node, kind):
        args = getattr(node, "args", None)
        out[name] = {"kind": kind, "line": node.lineno, "body": _short(ast.dump(node)),
                     "signature": _short(ast.dump(args)) if isinstance(args, ast.arguments) else None,
                     "names": sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name)})}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node.name, node, "function")
        elif isinstance(node, ast.ClassDef):
            add(node.name, node, "class")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(f"{node.name}.{item.name}", item, "method")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        add(name.id, node, "value")
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                add(alias.asname or alias.name, node, "import")
    return out


def _exports(path: pathlib.Path) -> list[str] | None:
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in node.targets):
            try:
                return sorted(ast.literal_eval(node.value))
            except ValueError:
                return ["<dynamic>"]
    return None


def app_engine_uses() -> tuple[list[dict], list[dict]]:
    """Static uses of engine symbols by app files: `_engine("m").x`, `v = _engine("m"); v.x`, `from sprite_gen.m import x`.
    Uses that cannot be resolved without running the code are returned separately, never guessed."""
    uses, unresolved = set(), set()
    for path in _app_files():
        file = rel(path)
        tree = ast.parse(path.read_text())

        def engine_module(call):
            if not (isinstance(call, ast.Call) and getattr(call.func, "id", getattr(call.func, "attr", "")) == "_engine"):
                return None
            if not call.args:
                return "sprite_gen.gen"  # provider._engine()은 load_engine("gen")
            arg = call.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return "sprite_gen." + arg.value
            unresolved.add((file, call.lineno, "_engine() with a non-literal module name"))
            return None

        def aliases_in(scope, inherited):
            found = dict(inherited)
            for node in ast.walk(scope):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sprite_gen"):
                    for alias in node.names:
                        candidate = f"{node.module}.{alias.name}"
                        if _module_file(candidate, ENGINE):
                            found[alias.asname or alias.name] = candidate
                        else:
                            uses.add((node.module, alias.name, file, node.lineno))
                elif isinstance(node, ast.Assign):
                    targets = node.targets[0].elts if isinstance(node.targets[0], ast.Tuple) else [node.targets[0]]
                    values = node.value.elts if isinstance(node.value, ast.Tuple) else [node.value]
                    for target, value in zip(targets, values):
                        module = engine_module(value)
                        if module and isinstance(target, ast.Name):
                            found[target.id] = module
                        elif isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
                            owner = found.get(getattr(value.func.value, "id", None)) or engine_module(value.func.value)
                            if owner:
                                unresolved.add((file, node.lineno, f"return value of {owner}.{value.func.attr}() is kept; later field/method uses on it (result shape) are not traced"))
                elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in ("import_module", "__import__"):
                    unresolved.add((file, node.lineno, "runtime import; only literal _engine('m') callers of this loader are resolved"))
            return found

        module_aliases = aliases_in(ast.Module(body=[n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))], type_ignores=[]), {})
        scopes = [(tree, module_aliases)] + [(n, aliases_in(n, module_aliases)) for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for scope, aliases in scopes:
            for node in ast.walk(scope):
                if isinstance(node, ast.Attribute):
                    module = aliases.get(getattr(node.value, "id", None)) or engine_module(node.value)
                    if module:
                        uses.add((module, node.attr, file, node.lineno))
                elif isinstance(node, ast.Call):
                    for arg in node.args:
                        if isinstance(arg, ast.Name) and arg.id in aliases:
                            callee = getattr(node.func, "id", getattr(node.func, "attr", "?"))
                            unresolved.add((file, node.lineno, f"engine module {aliases[arg.id]} passed to {callee}(); attribute uses inside the callee are not traced"))
    grouped = {}
    for module, name, file, line in sorted(uses):
        grouped.setdefault((module, name), set()).add(f"{file}:{line}")
    return ([{"module": m, "symbol": n, "callers": sorted(c, key=lambda x: (x.split(":")[0], int(x.split(":")[1])))} for (m, n), c in sorted(grouped.items())],
            [{"at": f"{f}:{l}", "reason": r} for f, l, r in sorted(unresolved)])


def _mentions(roots: list[pathlib.Path], base: pathlib.Path, words: tuple[str, str]) -> list[str]:
    pattern = [re.compile(rf"\b{re.escape(w)}\b") for w in words]
    return sorted(p.relative_to(base).as_posix() for root in roots for p in root.rglob("test_*.py")
                  if p.name != "test_absorption_m0.py" and all(r.search(p.read_text()) for r in pattern))  # M0 도구 시험은 앱 근거가 아님


def build_function_plan(upstream_root: pathlib.Path) -> dict:
    target = upstream_root / "v2.45.3"
    if verify_tree(upstream_root / "repo", PINS["v2.45.3"], target):
        raise SystemExit("upstream v2.45.3 is not the pinned tree; run fetch-upstream first")
    uses, unresolved = app_engine_uses()
    closure = {"local": set(dependency_closure(ENGINE, app_engine_modules())), "v2.45.3": set(dependency_closure(target, app_engine_modules()))}
    files = sorted(closure["local"] | closure["v2.45.3"])
    defs = {name: ({} if not (ENGINE / name).is_file() else definitions(ENGINE / name),
                   {} if not (target / name).is_file() else definitions(target / name)) for name in files}

    def status(local, upstream):
        if local and not upstream:
            return "removed-upstream"
        if upstream and not local:
            return "new"
        if local["body"] == upstream["body"]:
            return "same"
        return "signature-changed" if local["signature"] != upstream["signature"] else "body-changed"

    symbols = []
    for use in uses:
        name = _module_file(use["module"], ENGINE) or _module_file(use["module"], target)
        local, upstream = defs.get(name, ({}, {}))
        row = {**use, "file": name}
        symbol = use["symbol"]
        if _module_file(f"{use['module']}.{symbol}", ENGINE) or _module_file(f"{use['module']}.{symbol}", target):
            row["status"] = "submodule"
        elif symbol not in local and symbol not in upstream:
            row["status"] = "unresolved-name"  # 정적 정의가 없음(동적 생성·별칭). 추정하지 않는다
        else:
            row["status"] = status(local.get(symbol), upstream.get(symbol))
            used = set((upstream.get(symbol) or local.get(symbol))["names"])
            kinds = {n: (upstream.get(n) or local.get(n))["kind"] for n in used if n != symbol and n in (set(local) | set(upstream))}
            row["changedHelpers"] = sorted(n for n, k in kinds.items() if k != "import" and status(local.get(n), upstream.get(n)) != "same")
        leaf = use["module"].rsplit(".", 1)[-1]
        row["appTests"] = _mentions([ROOT / "tests"], ROOT, (symbol, leaf))
        row["upstreamTests"] = _mentions([target / "tests"], target, (symbol, leaf))
        if name in CONTRACT_CONFLICTS:
            row["protectedPolicy"] = CONTRACT_CONFLICTS[name]
        symbols.append(row)
    per_file = []
    for name in files:
        local, upstream = defs[name]
        code = lambda d: {k for k, v in d.items() if v["kind"] in ("function", "class", "method")}
        env = lambda root: set(ENV_READ.findall((root / name).read_text())) if (root / name).is_file() else set()
        exports = (_exports(ENGINE / name) if (ENGINE / name).is_file() else None, _exports(target / name) if (target / name).is_file() else None)
        row = {"file": name, "new": sorted(code(upstream) - code(local)), "removed": sorted(code(local) - code(upstream)),
               "changed": sorted(k for k in code(local) & code(upstream) if local[k]["body"] != upstream[k]["body"]),
               "appClosure": [k for k, v in closure.items() if name in v], "envRead": sorted(env(target) or env(ENGINE)),
               "envAdded": sorted(env(target) - env(ENGINE)), "envRemoved": sorted(env(ENGINE) - env(target)),
               "appSymbols": sorted({s["symbol"] for s in symbols if s["file"] == name})}
        if exports[0] != exports[1]:
            row["exports"] = {"local": exports[0], "v2.45.3": exports[1]}
        if name in CONTRACT_CONFLICTS:
            row["protectedPolicy"] = CONTRACT_CONFLICTS[name]
        per_file.append(row)
    count = lambda key: {k: sum(s["status"] == k for s in symbols) for k in sorted({s["status"] for s in symbols})}
    return {"schema": "frame-room-absorption-function-plan-v1",
            "upstreamCommit": PINS["v2.45.3"], "localTreeDigest": digest(_local_engine()),
            "method": "AST static extraction. App callers: _engine('m').x, v = _engine('m'); v.x, from sprite_gen.m import x. "
                      "Body digest = ast.dump without line numbers. changedHelpers = same-module names the symbol references whose definition differs. "
                      "Tests = test files naming both the symbol and its module leaf (textual, not coverage).",
            "summary": {"appSymbols": len(symbols), "byStatus": count("status"), "files": len(per_file),
                        "newFunctions": sum(len(f["new"]) for f in per_file), "changedFunctions": sum(len(f["changed"]) for f in per_file),
                        "unresolvedBoundaries": len(unresolved)},
            "appSymbols": symbols, "files": per_file, "unresolved": unresolved,
            "notResolved": ["engine-internal call graph across modules (only same-module helpers are linked; cross-module effects are covered by the file closure)",
                            "attribute uses on engine modules passed into other functions (listed in unresolved)",
                            "runtime configuration from provider settings files and CLI defaults (env reads are listed per file; file-based settings are covered by protectedPolicy notes)"]}


# ---------------------------------------------------------------- regression baseline

def _ro(path: pathlib.Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def classify_recipe(processing: dict | None, *, quality_version: str, source_present: bool) -> dict:
    """Whether the current code may re-run a stored video recipe. Never upgrades silently."""
    if not processing:
        return {"class": "no-recorded-recipe", "reason": "처리 version/options 기록 없음; 결과 조회 전용"}
    version, options = processing.get("version"), processing.get("options") or {}
    if version != CURRENT_VIDEO_PROCESSING:
        return {"class": "legacy-unreproducible", "reason": f"현행 코드는 {version} 실행을 지원하지 않음; 결과 조회 전용"}
    unknown = sorted(set(options) - CURRENT_OPTION_KEYS)
    if unknown:
        return {"class": "legacy-unreproducible", "reason": "현행 코드가 모르는 옵션: " + ",".join(unknown)}
    if quality_version != CURRENT_QUALITY_VERSION:
        return {"class": "legacy-unreproducible", "reason": f"엔진 qualityVersion {quality_version} != {CURRENT_QUALITY_VERSION}"}
    if not source_present:
        return {"class": "source-missing", "reason": "원본 MP4 없음 또는 해시 불일치"}
    implied = {k: v for k, v in IMPLIED_OPTION_DEFAULTS.items() if k not in options}
    return {"class": "reproducible-current", "impliedDefaults": implied,
            "reason": "현행 정책과 같은 version·옵션; replay로 선택 구간·샘플·키 프레임 일치 확인 필요"}


def classify_derived(clip: dict, project_ids: set[str]) -> dict:
    kind = (clip.get("sourceProcessing") or {}).get("kind")
    source = (clip.get("sourceProcessing") or {}).get("source", clip.get("sourceProcessing") or {})
    source_project = source.get("projectId") or source.get("sourceProjectId")
    if source_project and source_project not in project_ids:
        return {"class": "source-missing", "reason": f"{kind}: 원본 프로젝트가 로컬에 없음"}
    return {"class": "derived-no-replay", "reason": f"{kind}: 파생 결과는 저장된 셀이 기준; M0 replay 대상 아님"}


def _project_baseline(folder: pathlib.Path, quality_version: str, project_ids: set[str]) -> dict:
    from adapters.spritegen.video_probe import read_timing
    db = _ro(folder / "project.sqlite3")
    snapshot = json.loads(db.execute("SELECT snapshot FROM projects").fetchone()[0])
    assets = {r["id"]: (json.loads(r["metadata"]), folder / r["path"]) for r in db.execute("SELECT id,metadata,path FROM assets")}
    integrity = {"checked": 0, "ok": 0, "mismatch": [], "missing": []}
    for aid, (meta, path) in sorted(assets.items()):
        integrity["checked"] += 1
        if not path.is_file():
            integrity["missing"].append(aid)
        elif sha256(path) != meta["sha256"]:
            integrity["mismatch"].append(aid)
        else:
            integrity["ok"] += 1
    integrity["digest"] = digest(sorted((aid, meta["sha256"]) for aid, (meta, _) in assets.items()))
    videos = []
    for row in db.execute("SELECT id,metadata,path FROM videos ORDER BY id"):
        meta, path = json.loads(row["metadata"]), folder / row["path"]
        item = {"videoId": row["id"], "path": rel(path), "present": path.is_file(), "recorded": {
            k: meta.get(k) for k in ("sha256", "frameCount", "fps", "durationMs", "width", "height")}}
        if path.is_file():
            timing = read_timing(path)
            item.update(sha256=sha256(path), bytes=path.stat().st_size,
                        probe={k: timing[k] for k in ("frameCount", "fps", "durationMs", "width", "height")})
            # 저장 기록의 durationMs는 정수 ms로 반올림돼 있다.
            item["matchesRecord"] = item["sha256"] == meta.get("sha256") and all(
                meta.get(k) is None or abs(float(meta[k]) - float(item["probe"][k])) <= (0.5 if k == "durationMs" else 1e-6)
                for k in item["probe"])
        videos.append(item)
    outputs = [{"path": rel(p), "sha256": sha256(p), "bytes": p.stat().st_size} for p in sorted((folder / "outputs").rglob("*.mp4"))]
    jobs = {}
    for row in db.execute("SELECT operation,body FROM jobs WHERE operation IN ('generate_video','process_video') ORDER BY id"):
        job_id = json.loads(row["body"])["jobId"]
        body = json.loads(row["body"])
        result = body.get("result") or {}
        processing = result.get("processing") or {}
        jobs[result.get("clipId")] = {
            "jobId": body["jobId"], "operation": row["operation"], "videoId": result.get("videoId"),
            "version": processing.get("version"), "options": processing.get("options"),
            "requestParams": {k: v for k, v in (body.get("request") or {}).get("params", {}).items() if k not in ("prompt", "motionPrompt")},
            "selection": {k: processing.get("selection", {}).get(k) for k in ("mode", "kind", "startFrame", "endFrame", "loop", "sourceFrameCount", "sampledFrameCount", "durationMs")},
            "normalization": (processing.get("normalization") or {}).get("method"),
            "finish": {k: (processing.get("finish") or {}).get(k) for k in ("version", "mode")},
            "spillReferenceAssetId": processing.get("spillReferenceAssetId"),
            "outputFrames": processing.get("outputFrames"), "durationMs": processing.get("durationMs"),
            "evidence": _job_evidence(folder / "outputs" / job_id)}
    frames = {f["frameVersionId"]: f for f in snapshot["frames"]}
    keyed_of = {}
    for aid, (meta, _) in assets.items():
        provenance = meta.get("provenance") or {}
        if provenance.get("processing") == "chroma-key" and provenance.get("parentAssetId"):
            keyed_of[provenance["parentAssetId"]] = meta["sha256"]
    video_ok = {v["videoId"]: v.get("matchesRecord", False) for v in videos}
    clips = []
    for clip in snapshot["clips"]:
        cells = []
        for occurrence in clip["occurrences"]:
            frame = frames[occurrence["frameVersionId"]]
            meta, path = assets[frame["imageAssetId"]]
            cells.append({"frameVersionId": frame["frameVersionId"], "imageAssetId": frame["imageAssetId"],
                          "path": rel(path), "sha256": meta["sha256"], "durationMs": occurrence["durationMs"],
                          "sourceFrameIndex": frame.get("sourceFrameIndex"), "extractionVersion": frame.get("extractionVersion"),
                          "selectedRawSha256": assets[frame["rawAssetId"]][0]["sha256"] if frame.get("rawAssetId") in assets else None,
                          "selectedKeyedSha256": keyed_of.get(frame.get("rawAssetId")),
                          "sourceKind": (frame.get("sourceProcessing") or {}).get("kind"),
                          "pixelEdits": len(occurrence.get("pixelEdits") or []), "transform": digest(occurrence.get("transform"))})
        job = jobs.get(clip["clipId"])
        versions = sorted({c["extractionVersion"] for c in cells if c["extractionVersion"]})
        if job:
            recipe = classify_recipe(job, quality_version=quality_version, source_present=video_ok.get(job["videoId"], False))
        elif clip.get("sourceProcessing"):
            recipe = classify_derived(clip, project_ids)
        else:
            recipe = classify_recipe(None, quality_version=quality_version, source_present=False)
        recipe["extractionVersions"] = versions
        full = (job or {}).get("evidence", {}).get("fullExtraction", {})
        evidence = {"source": "verified-full-extraction" if full.get("verified") and video_ok.get(job["videoId"]) else "unknown",
                    "origin": "unsupported-legacy", "baseline": "m0-current-cells"}
        clips.append({"clipId": clip["clipId"], "clipRevisionId": clip["clipRevisionId"], "name": clip["name"],
                      "stateId": clip.get("stateId"), "direction": clip.get("direction"), "loop": clip["loop"],
                      "endBehavior": clip["endBehavior"], "frameCount": len(cells), "totalMs": sum(c["durationMs"] for c in cells),
                      "sourceVideoId": clip.get("sourceVideoId"), "cells": cells, "recipe": recipe, "evidence": evidence, "job": job})
    project_json = folder / "project.json"
    return {"projectId": snapshot["projectId"], "folder": rel(folder), "schemaVersion": snapshot["schemaVersion"],
            "revision": snapshot["revision"], "snapshotSha256": digest(snapshot), "projectJsonSha256": sha256(project_json),
            "counts": {k: len(snapshot[k]) for k in ("clips", "frames", "assets", "videos", "generations")},
            "assetIntegrity": integrity, "videos": videos, "outputVideos": outputs, "clips": clips}


def _job_evidence(out: pathlib.Path) -> dict:
    """Job output files beside the registered cells: full raw/keyed extraction, reports, prepared canvas."""
    attempts = sorted(p for p in out.glob("*") if p.is_dir())
    if not attempts:
        return {"present": False}
    attempt = attempts[-1]
    complete = sorted(attempt.glob("processing/extractions/*/complete.json"))
    full = {"present": False}
    if complete:
        manifest = json.loads(complete[-1].read_text()).get("manifest", [])
        base = attempt / "processing"
        verified = bool(manifest) and all((base / m["file"]).is_file() and sha256(base / m["file"]) == m["sha256"] for m in manifest)
        full = {"present": True, "verified": verified, "files": len(manifest),
                "rawFrames": sum("/raw/" in m["file"] for m in manifest), "keyedFrames": sum("/keyed/" in m["file"] for m in manifest),
                "manifestDigest": digest(manifest), "completeSha256": sha256(complete[-1])}
    named = lambda pattern: {rel(p): sha256(p) for p in sorted(attempt.glob(pattern))}
    return {"present": True, "attempts": len(attempts), "fullExtraction": full,
            "extractionReports": named("processing/extractions/*/attempt-*/frames.report.json"),
            "selectionReports": named("processing/selections/*/processing.report.json"),
            "preparedCanvas": named("generation/input-canvas.png*"),
            "processingCheckpoint": named("processing/video-processing.json")}


def referenced_evidence() -> list[dict]:
    cited = {}
    docs = [d for d in ROOT.glob("docs/**/*.md") if not d.is_relative_to(ROOT / "docs/product/absorption")]  # M0 산출물은 과거 증거가 아님
    for doc in sorted([*docs, ROOT / "README.md", ROOT / "engine/PATCHES.md", ROOT / "engine/engine-lock.json"]):
        for match in re.findall(r"(?<![\w/.])((?:research|artifacts|diagnostics|output|\.data)/[^\s)`'\"<>|,*{]+)", doc.read_text()):
            path = match.rstrip(".:")
            cited.setdefault(path, set()).add(rel(doc))
    return [{"path": p, "exists": (ROOT / p).exists(), "citedBy": sorted(d)} for p, d in sorted(cited.items())]


def build_baseline(data: pathlib.Path) -> dict:
    lock = json.loads((ROOT / "engine/engine-lock.json").read_text())
    folders = sorted(p.parent for p in (data / "projects").glob("*/project.json"))
    ids = {json.loads(p.joinpath("project.json").read_text())["projectId"] for p in folders}
    projects = [_project_baseline(f, lock["qualityVersion"], ids) for f in folders]
    registry = _ro(data / "app.sqlite3")
    registered = []
    for row in registry.execute("SELECT project_id,path,ready FROM project_folders ORDER BY project_id"):
        path = pathlib.Path(row["path"])
        inside = path.resolve().is_relative_to(ROOT)
        registered.append({"projectId": row["project_id"], "folder": rel(path) if inside else "outside-repo", "ready": row["ready"]})
    tools = lock["localTools"]["rife"]
    rife_root = ROOT / tools["installRoot"]
    rife = {name: {"expected": expected, "present": (rife_root / name).is_file(),
                   "matches": (rife_root / name).is_file() and sha256(rife_root / name) == expected}
            for name, expected in sorted(tools["files"].items())}
    output = [{"path": rel(p), "sha256": sha256(p), "bytes": p.stat().st_size} for p in sorted((ROOT / "output").rglob("*")) if p.is_file() and p.name != ".DS_Store"]
    evidence = referenced_evidence()
    return {"schema": "frame-room-regression-baseline-v1",
            "readOnly": "immutable SQLite reads, file hashing and ffprobe only; no copy or edit of user data",
            "engine": {"commit": lock["commit"], "qualityVersion": lock["qualityVersion"], "lockSha256": sha256(ROOT / "engine/engine-lock.json"),
                       "treeDigest": digest(_local_engine()),
                       "patchDigest": digest(sorted((p["path"], p["forkSha256"]) for p in lock["patches"]))},
            "policy": {"videoProcessing": CURRENT_VIDEO_PROCESSING, "videoExtraction": CURRENT_VIDEO_EXTRACTION,
                       "impliedOptionDefaults": IMPLIED_OPTION_DEFAULTS},
            "rife": {"release": tools["release"], "model": tools["model"], "files": rife},
            "registeredProjects": registered, "projects": projects,
            "outputArtifacts": {"count": len(output), "digest": digest(output), "files": output},
            "referencedEvidence": {"cited": len(evidence), "missing": sum(not e["exists"] for e in evidence), "paths": evidence}}


# baseline 차이의 원인 구분. 분석 규칙·문서 인용이 바뀐 것과 보존 자료(원본·DB·셀·시간)가 바뀐 것을 섞지 않는다.
ANALYSIS_FIELDS = {"recipe", "evidence", "policy", "readOnly", "schema"}


def diff_kind(keys: list[str]) -> str:
    if "referencedEvidence" in keys:
        return "docs-evidence"  # 저장소 문서가 인용한 경로 목록. 보존 자료가 아니다
    if "job" not in keys and ANALYSIS_FIELDS & set(keys):
        return "analysis"  # M0 도구의 분류·판정 결과(job 아래 evidence는 실제 작업 출력 파일 해시라 input)
    return "input"


def compare_baseline(stored: dict, current: dict) -> list[str]:
    """Every difference fails verify; each is tagged input / analysis / docs-evidence so a tool change never hides a data change."""
    errors = []

    def walk(a, b, where, keys):
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                walk(a.get(key), b.get(key), f"{where}.{key}", keys + [key])
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{where}[{i}]", keys)
        elif a != b:
            errors.append(f"[{diff_kind(keys)}] {where}: {json.dumps(a, ensure_ascii=False)[:120]} -> {json.dumps(b, ensure_ascii=False)[:120]}")
    walk(stored, current, "baseline", [])
    return errors


def baseline_self_check(manifest: dict) -> list[str]:
    errors = []
    for project in manifest["projects"]:
        integrity = project["assetIntegrity"]
        if integrity["mismatch"] or integrity["missing"]:
            errors.append(f"{project['projectId']}: asset integrity {len(integrity['mismatch'])} mismatch / {len(integrity['missing'])} missing")
        errors += [f"{project['projectId']}: video {v['videoId']} differs from its record" for v in project["videos"] if not v.get("matchesRecord")]
        for clip in project["clips"]:
            if clip["frameCount"] != len(clip["cells"]) or clip["totalMs"] != sum(c["durationMs"] for c in clip["cells"]):
                errors.append(f"{clip['clipId']}: frame/time totals inconsistent")
    if FORBIDDEN_TEXT.search(json.dumps(manifest, ensure_ascii=False)):
        errors.append("manifest contains an absolute local path or credential-like text")
    return errors


# ---------------------------------------------------------------- replay of reproducible recipes

def _finish_like_worker(result: dict, params: dict, work: pathlib.Path) -> list[pathlib.Path]:
    # services/worker/video_task.py의 정규화·마무리 단계와 같은 호출(저장·등록 없이 파일만 만든다).
    from adapters.spritegen.video_finish import finish_frames
    from adapters.spritegen.video_normalization import normalize_frames
    extraction = result.get("extraction", {})
    keyed_dir = extraction.get("processedKeyedDir") or extraction.get("keyedDir")
    bounds = sorted(pathlib.Path(keyed_dir).glob("frame-*.png"))[result["selection"]["startFrame"]:result["selection"]["endFrame"]] if keyed_dir else None
    items = result["frames"] + result.get("alternateFrames", [])
    save = lambda path, value: pathlib.Path(path).write_text(json.dumps(value))
    normalized, _ = normalize_frames(items, result["standingHeight"], params["bodyHeight"], work / "normalized",
                                     bounds_paths=result.get("boundsPaths") or bounds, source_anchor=result["anchor"],
                                     resize_mode="legacy" if params["finishMode"] == "gif" else "color-alpha", save_metadata=save)
    finished, _ = finish_frames(normalized, work / "finished", mode=params["finishMode"], cell_width=params["cellWidth"],
                                cell_height=params["cellHeight"], save_metadata=save)
    return [pathlib.Path(p) for p in finished]


OBSERVER_OPTIONS = ("frameObserver", "observationCacheOnly")


SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def replay_dirs(manifest: dict, work: pathlib.Path) -> dict[str, pathlib.Path]:
    """manifest의 clipId로 만들 출력 폴더를 처리 전에 모두 검증한다. 하나라도 어긋나면 아무것도 실행하지 않는다."""
    base = work.resolve()
    dirs = {}
    for project in manifest["projects"]:
        # 입력도 manifest 값이다. 보존 프로젝트 폴더 밖을 읽지 않는다(읽기 전용이어도 경계 밖 접근 금지).
        folder = (ROOT / project["folder"]).resolve()
        inputs = [folder, *((ROOT / v["path"]).resolve() for v in project["videos"])]
        if not folder.is_relative_to((ROOT / ".data" / "projects").resolve()) or not all(p.is_relative_to(folder) for p in inputs):
            raise SystemExit(f"refused replay: project {project.get('projectId')!r} input path outside its .data/projects folder")
        for clip in project["clips"]:
            clip_id = clip.get("clipId")
            if not isinstance(clip_id, str) or not SAFE_ID.fullmatch(clip_id):
                raise SystemExit(f"refused replay: unsafe clipId {clip_id!r} (absolute, '..', separator or empty)")
            target = (base / clip_id).resolve()
            if target.parent != base or clip_id in dirs or clip_id == "isolated-store" or target.exists():
                raise SystemExit(f"refused replay: clipId {clip_id!r} does not map to a new folder directly under work")
            dirs[clip_id] = target
    return dirs


def replay(manifest: dict, work: pathlib.Path, process_clip=None) -> dict:
    """Re-run reproducible-current recipes into `work` (verification-only files, never registered anywhere)."""
    dirs = replay_dirs(manifest, work)
    # 앱 저장소 모듈이 실제 .data를 가리키지 않게 격리한다(프로젝트 자료는 아래에서 읽기 전용으로만 연다).
    previous = os.environ.get("SPRITE_DATA_DIR")
    os.environ["SPRITE_DATA_DIR"] = str(work / "isolated-store")
    try:
        return _replay(manifest, work, dirs, process_clip)
    finally:  # 호출한 프로세스(시험 포함)에 격리 경로를 남기지 않는다
        if previous is None:
            os.environ.pop("SPRITE_DATA_DIR", None)
        else:
            os.environ["SPRITE_DATA_DIR"] = previous


def _replay(manifest: dict, work: pathlib.Path, dirs: dict[str, pathlib.Path], process_clip) -> dict:
    if process_clip is None:
        from adapters.spritegen.video_processing import process_clip
    engine_matches = digest(_local_engine()) == manifest["engine"].get("treeDigest")
    results = []
    for project in manifest["projects"]:
        folder = ROOT / project["folder"]
        db = _ro(folder / "project.sqlite3")
        assets = {r["id"]: (json.loads(r["metadata"]), folder / r["path"]) for r in db.execute("SELECT id,metadata,path FROM assets")}
        by_parent = {}
        for aid, (meta, _) in assets.items():
            parent = (meta.get("provenance") or {}).get("parentAssetId")
            if parent and (meta.get("provenance") or {}).get("processing") == "chroma-key":
                by_parent[parent] = meta["sha256"]
        frames = {f["frameVersionId"]: f for f in json.loads(db.execute("SELECT snapshot FROM projects").fetchone()[0])["frames"]}
        for clip in project["clips"]:
            job = clip["job"]
            if clip["recipe"]["class"] != "reproducible-current":
                continue
            params = {**job["options"], **clip["recipe"]["impliedDefaults"]}
            if params.get("frameSelection") != "uniform" or any(k in params for k in OBSERVER_OPTIONS):
                # vision 선별은 관찰 모델 호출 또는 관찰 캐시가 필요하다. M0 replay는 외부 호출 없이 건너뛴다.
                results.append({"projectId": project["projectId"], "clipId": clip["clipId"], "jobId": job["jobId"],
                                "skipped": "observer-required-not-run", "reproduced": False})
                continue
            video = next(v for v in project["videos"] if v["videoId"] == job["videoId"])
            if job["spillReferenceAssetId"]:
                params["referencePath"] = str(assets[job["spillReferenceAssetId"]][1])
            out = process_clip(ROOT / video["path"], dirs[clip["clipId"]], params)
            sampled = [(f["sourceFrameIndex"], f["durationMs"]) for f in out["frames"] if (f.get("frameSelection") or {}).get("role") != "uniform-alternative"]
            stored = [(c["sourceFrameIndex"], c["durationMs"]) for c in clip["cells"]]
            stored_keyed = [by_parent.get(frames[c["frameVersionId"]]["rawAssetId"]) for c in clip["cells"]]
            keyed = [sha256(pathlib.Path(f.get("originalKeyedPath", f["keyedPath"]))) for f in out["frames"][:len(stored)]]
            finished = _finish_like_worker(out, job["requestParams"], dirs[clip["clipId"]])
            checks = {"selection": [out["selection"]["startFrame"], out["selection"]["endFrame"]] == [job["selection"]["startFrame"], job["selection"]["endFrame"]],
                      "samplesAndDurations": sampled == stored, "keyedPixels": keyed == stored_keyed,
                      "finalCells": [sha256(p) for p in finished[:len(stored)]] == [c["sha256"] for c in clip["cells"]],
                      "loop": out["selection"]["loop"] == clip["loop"]}
            results.append({"projectId": project["projectId"], "clipId": clip["clipId"], "jobId": job["jobId"],
                            "version": out["version"], "checks": checks, "reproduced": all(checks.values()),
                            "replayed": {"selection": [out["selection"]["startFrame"], out["selection"]["endFrame"]], "samples": sampled}})
    return {"schema": "frame-room-recipe-replay-v1",
            "outputs": "검증용 임시 파일. 프로젝트·라이브러리에 등록하지 않으며 사용자 전달 동작이 아니다",
            "engineMatchesBaseline": engine_matches,
            "results": results,
            # 엔진이 baseline 이후 바뀌면 같은 VERSION 문자열이어도 재현이 아니라 정책 비교다.
            "allReproduced": engine_matches and bool(results) and all(r["reproduced"] for r in results)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch-upstream").add_argument("dest", type=pathlib.Path)
    sub.add_parser("inventory").add_argument("upstream", type=pathlib.Path)
    p = sub.add_parser("ledger-check")
    p.add_argument("--ledger", type=pathlib.Path, default=LEDGER)
    p.add_argument("--upstream", type=pathlib.Path)
    p = sub.add_parser("port-plan")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", type=pathlib.Path)
    group.add_argument("--verify", type=pathlib.Path)
    p.add_argument("--upstream-root", type=pathlib.Path)
    p.add_argument("--replace", action="store_true", help="overwrite an existing --out deliberately")
    p = sub.add_parser("function-plan")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", type=pathlib.Path)
    group.add_argument("--verify", type=pathlib.Path)
    p.add_argument("--upstream-root", type=pathlib.Path, required=True)
    p.add_argument("--replace", action="store_true", help="overwrite an existing --out deliberately")
    p = sub.add_parser("baseline")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", type=pathlib.Path)
    p.add_argument("--replace", action="store_true", help="overwrite an existing --write deliberately (re-baseline)")
    group.add_argument("--verify", type=pathlib.Path)
    p.add_argument("--data-dir", type=pathlib.Path, default=ROOT / ".data")
    p = sub.add_parser("replay")
    p.add_argument("--manifest", type=pathlib.Path, required=True)
    p.add_argument("--work", type=pathlib.Path, required=True)
    p.add_argument("--out", type=pathlib.Path)
    p.add_argument("--replace", action="store_true", help="overwrite an existing --out report")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    if args.command == "fetch-upstream":
        fetch_upstream(args.dest)
    elif args.command == "inventory":
        print(json.dumps(extract_inventory(args.upstream), ensure_ascii=False, indent=1))
    elif args.command == "ledger-check":
        ledger = json.loads(args.ledger.read_text())
        errors = check_ledger(ledger, args.upstream)
        print(json.dumps(ledger_summary(ledger), ensure_ascii=False))
        for error in errors:
            print("ERROR", error)
        print("OK ledger complete" + (" (upstream tree re-extracted)" if args.upstream else " (frozen inventory)") if not errors else f"FAIL {len(errors)}")
        return 1 if errors else 0
    elif args.command == "port-plan":
        if args.out:
            if not args.upstream_root:
                parser.error("--out needs --upstream-root")
            out = guard_output(args.out, replace=args.replace, forbidden=(args.upstream_root,))
            plan = build_port_plan(args.upstream_root, json.loads(LEDGER.read_text()))
            dump(out, plan)
            print(json.dumps(plan["summary"]))
            return 0
        errors = verify_port_plan(json.loads(args.verify.read_text()))
        for error in errors:
            print("ERROR", error)
        print("OK port plan matches local engine" if not errors else f"FAIL {len(errors)}")
        return 1 if errors else 0
    elif args.command == "function-plan":
        out = guard_output(args.out, replace=args.replace, forbidden=(args.upstream_root,)) if args.out else None
        plan = build_function_plan(args.upstream_root)
        if out:
            dump(out, plan)
            print(json.dumps(plan["summary"]))
            return 0
        errors = compare_baseline(json.loads(args.verify.read_text()), plan)
        for error in errors:
            print("ERROR", error.split("] ", 1)[1])
        print("OK function plan matches local engine, app callers and upstream" if not errors else f"FAIL {len(errors)}")
        return 1 if errors else 0
    elif args.command == "baseline":
        target = guard_output(args.write, replace=args.replace, forbidden=(args.data_dir,)) if args.write else None
        current = build_baseline(args.data_dir)
        errors = baseline_self_check(current)
        if args.write:
            dump(target, current)
        else:
            differences = compare_baseline(json.loads(args.verify.read_text()), current)
            errors += differences
            if differences:
                kinds = [d[1:d.index("]")] for d in differences]
                print(json.dumps({"differences": {k: kinds.count(k) for k in sorted(set(kinds))}}))
        for error in errors:
            print("ERROR", error)
        clips = [c for p in current["projects"] for c in p["clips"]]
        print(json.dumps({"projects": len(current["projects"]), "videos": sum(len(p["videos"]) for p in current["projects"]),
                          "clips": len(clips), "cells": sum(c["frameCount"] for c in clips),
                          "recipes": {k: sum(c["recipe"]["class"] == k for c in clips) for k in sorted({c["recipe"]["class"] for c in clips})},
                          "missingEvidence": current["referencedEvidence"]["missing"]}, ensure_ascii=False))
        print(("OK baseline written" if args.write else "OK baseline unchanged") if not errors else f"FAIL {len(errors)}")
        return 1 if errors else 0
    elif args.command == "replay":
        manifest = json.loads(args.manifest.read_text())
        work = guard_output(args.work, directory=True, forbidden=tuple(ROOT / p["folder"] for p in manifest["projects"]))
        out = guard_output(args.out, replace=args.replace, forbidden=(work,)) if args.out else None
        report = replay(manifest, work)
        if out:
            dump(out, report)
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if report["allReproduced"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
