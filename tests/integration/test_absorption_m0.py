"""M0 흡수 기준 도구: 기능 대장 완전성, 파일 이식 분류, recipe 재현 규칙, baseline 변조 탐지."""
import copy
import importlib.util
import json
import pathlib
import sqlite3
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("absorption_m0", ROOT / "scripts" / "absorption_m0.py")
m0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m0)
ABSORPTION = ROOT / "docs" / "product" / "absorption"


def ledger():
    return json.loads((ABSORPTION / "m0-feature-ledger.json").read_text())


def test_committed_ledger_is_complete_and_nothing_is_closed_without_app_evidence():
    data = ledger()
    assert m0.check_ledger(data) == []
    assert data["upstream"]["commit"] == m0.PINS["v2.45.3"]
    assert len(data["inventory"]["commands"]) == len([e for e in data["entries"] if e["kind"] == "command"])
    assert all(e["status"] != "완료" for e in data["entries"])  # M0 has no app evidence for any v2.45.3 feature yet


@pytest.mark.parametrize("mutate, expected", [
    (lambda d: d["entries"].pop(next(i for i, e in enumerate(d["entries"]) if e["upstream"].get("command") == "video-stop")),
     "command needs exactly one ledger entry: video-stop"),
    (lambda d: [e["upstream"]["docs"].remove("user-workflow.md") for e in d["entries"] if "user-workflow.md" in e["upstream"]["docs"]],
     "indexed doc not mapped: user-workflow.md"),
    (lambda d: [e["upstream"]["aliases"].remove("scripts/video_set.py") for e in d["entries"] if "scripts/video_set.py" in e["upstream"]["aliases"]],
     "script alias not mapped: scripts/video_set.py"),
    (lambda d: [e["upstream"]["modules"].remove("sprite_gen.spec.layout") for e in d["entries"] if "sprite_gen.spec.layout" in e["upstream"]["modules"]],
     "taxonomy module not mapped: layout"),
    (lambda d: d["entries"][0].update(status="완료"), "완료 requires app test evidence"),
    (lambda d: d["entries"][0].update(status="나중에 검토"), "invalid status"),
    (lambda d: d["entries"][0].update(status="차단", blockers=[]), "차단 requires blockers"),
    (lambda d: d["entries"][0]["app"].update(entry=""), "app.entry must name"),
    (lambda d: d["entries"][0]["tests"]["existing"].append("tests/integration/test_missing.py"), "referenced local path missing"),
    (lambda d: d["entries"][0].update(notes="/Users/someone/project"), "absolute local path"),
    (lambda d: d["entries"].append(copy.deepcopy(d["entries"][1])), "duplicate entry id"),
    (lambda d: d["entries"][0]["upstream"]["aliases"].append("scripts/video_set.py"), "alias mapped to more than one entry: scripts/video_set.py"),
    (lambda d: d["entries"][0]["upstream"]["aliases"].append("--fit-pixel-perfect"), "retired flag recorded as supported alias: --fit-pixel-perfect"),
    (lambda d: [e["upstream"]["retired"].clear() for e in d["entries"]], "retired flag not mapped: --no-fit-pixel-perfect"),
])
def test_ledger_check_rejects_gaps(mutate, expected):
    data = copy.deepcopy(ledger())
    mutate(data)
    assert any(expected in error for error in m0.check_ledger(data))


def test_inventory_reads_commands_taxonomy_docs_and_aliases_from_source(tmp_path):
    (tmp_path / "sprite_gen/video").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "sprite_gen/cli.py").write_text(
        "from sprite_gen.video import loop as video_loop\nfrom sprite_gen import gen\n"
        "COMMANDS: dict = {'video-loop': ('d', video_loop.add_arguments, video_loop.run), 'gen': ('d', gen.add, gen.run)}\n")
    (tmp_path / "sprite_gen/_modules.py").write_text(
        "MODULE_DOMAIN = {'loop': 'video'}\nPIPELINES = [{'verbs': ['video-loop']}]\nTOOL_GROUPS = []\nWORKFLOWS = []\n")
    (tmp_path / "sprite_gen/video/loop.py").write_text(
        "p.add_argument(\"--old\", \"--no-old\", dest=\"_retired_x\")\nif __name__ == '__main__':\n    pass\n")
    (tmp_path / "docs/README.md").write_text("[a](loop.md) [b](loop.md#x) [index](README.md)\n")
    (tmp_path / "scripts/video_loop.py").write_text("import sprite_gen.video.loop\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n[project.scripts]\nsprite-gen='sprite_gen.cli:main'\n")
    inventory = m0.extract_inventory(tmp_path)
    assert inventory["commands"] == {"gen": "sprite_gen.gen", "video-loop": "sprite_gen.video.loop"}
    assert inventory["moduleDomain"] == {"loop": "video"} and inventory["catalogVerbs"] == ["video-loop"]
    assert inventory["docIndex"] == ["loop.md"]
    assert inventory["moduleEntrypoints"] == ["sprite_gen.video.loop"]
    assert inventory["scriptWrappers"] == {"scripts/video_loop.py": "sprite_gen.video.loop"}
    assert inventory["retiredFlags"] == ["--no-old", "--old"] and inventory["consoleScripts"] == ["sprite-gen"]


@pytest.mark.parametrize("shas, base, expected", [
    ({"v2.12.1": "a", "v2.34.0": "b", "v2.45.3": "b", "local": "b"}, None, ("v2.45.3", "reuse")),
    ({"v2.12.1": "a", "v2.34.0": "b", "v2.45.3": "c", "local": "b"}, None, ("v2.34.0", "replace")),
    ({"v2.12.1": "a", "v2.34.0": "b", "v2.45.3": "c", "local": "a"}, None, ("v2.12.1", "replace")),
    ({"v2.12.1": "a", "v2.34.0": "b", "v2.45.3": "c", "local": "x"}, "b", ("local-patch", "merge")),
    ({"v2.12.1": "a", "v2.34.0": "b", "v2.45.3": "b", "local": "x"}, "b", ("local-patch", "keep-local")),
    ({"v2.12.1": "a", "v2.34.0": "b", "v2.45.3": "c", "local": "x"}, None, ("local-patch", "unrecorded-local-change")),
    ({"v2.12.1": None, "v2.34.0": None, "v2.45.3": "c", "local": None}, None, ("absent", "add")),
    ({"v2.12.1": "a", "v2.34.0": "a", "v2.45.3": None, "local": "a"}, None, ("v2.34.0", "upstream-removed")),
    ({"v2.12.1": None, "v2.34.0": None, "v2.45.3": None, "local": "x"}, None, ("local-patch", "local-only")),
])
def test_port_plan_file_actions(shas, base, expected):
    assert m0.classify_file(shas, base) == expected


def _assert_declared_port_deltas(plan, lock):
    changes = [change for milestone in ("M1", "M2", "M3")
               for change in next(x for x in lock["localAdaptations"] if x["milestone"] == milestone)["files"]]
    baseline = {x["path"]: x["sha256"]["local"] for x in plan["files"]}
    latest = dict(baseline)
    for change in changes:
        assert change['beforeSha256'] == latest.get(change['path'])
        latest[change['path']] = change['forkSha256']
    for path in {change['path'] for change in changes}:
        assert latest[path] == m0.sha256(m0.ROOT / 'engine/sprite-gen' / path)
        assert next(x for x in lock['patches'] if x['path']==path)['forkSha256'] == latest[path]
    tracked = m0._local_engine()
    # local=None인 M0 행도 추가 파일이 Git에 들어오면 changed가 된다(코드·시험 공통).
    expected = {f"local engine file changed since plan: {path}" for path in latest
                if path in baseline and baseline[path] != latest[path]
                and (baseline[path] is not None or path in tracked)}
    expected |= {f"local engine file not in plan: {path}" for path in latest if path not in baseline and path in tracked}
    expected.add('engine-lock.json changed since plan')
    if plan['appEngineModules'] != m0.app_engine_modules():
        expected.add('app engine imports changed since plan')
    assert set(m0.verify_port_plan(plan)) == expected


def test_committed_port_plan_tracks_only_declared_m1_m2_m3_deltas():
    plan = json.loads((ABSORPTION / "m0-port-plan.json").read_text())
    lock = json.loads((ROOT / 'engine/engine-lock.json').read_text())
    m1 = next(x for x in lock['localAdaptations'] if x['milestone'] == 'M1')['files']
    assert {x['path'] for x in m1} == {'sprite_gen/gen/video.py', 'sprite_gen/gen/xai.py'}
    _assert_declared_port_deltas(plan, lock)
    assert {t: p["commit"] for t, p in plan["pins"].items()} == m0.PINS
    merges = {r["path"] for r in plan["files"] if r["kind"] == "code" and r["action"] == "merge"}
    # 로컬 보호 패치(cyan 키, 접수 불명 재시도 제거, 구독 경로 고정)는 교체가 아니라 병합 대상이어야 한다.
    assert {"sprite_gen/gen/__init__.py", "sprite_gen/gen/codex_provider.py", "sprite_gen/frames/cutout.py"} <= merges
    assert not [r for r in plan["files"] if r["action"] == "unrecorded-local-change"]
    # 앱이 직접 호출하는 generate_video는 v2.45.3에서 POST를 재전송하므로 단순 교체 대상으로 남기지 않는다.
    video = next(r for r in plan["files"] if r["path"] == "sprite_gen/gen/video.py")
    assert video["appImports"] and "POST" in video["contractConflict"]


@pytest.mark.parametrize("state", ["untracked", "staged", "committed"])
def test_declared_port_deltas_preserve_sha_chain_and_reject_tampering_in_git_states(tmp_path, monkeypatch, state):
    monkeypatch.setattr(m0, "ROOT", tmp_path)
    engine = tmp_path / "engine/sprite-gen"
    git = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    git("init", "-q")
    existing = ["sprite_gen/shared.py", "tests/test_existing.py", "sprite_gen/untouched.py", "tests/test_untouched.py"]
    added = ["sprite_gen/new.py", "tests/test_new.py", "sprite_gen/outside_plan.py", "tests/test_outside_plan.py"]
    for path in existing:
        target = engine / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("baseline\n")
    lock_path = tmp_path / "engine/engine-lock.json"
    lock_path.write_text("{}\n")
    baseline = {path: m0.sha256(engine / path) for path in existing}
    baseline.update({path: None for path in added[:2]})
    plan = {"files": [{"path": path, "sha256": {"local": sha}} for path, sha in baseline.items()],
            "local": {"lockSha256": m0.sha256(lock_path)}, "appEngineModules": []}
    git("add", "engine")
    git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "baseline")
    lock = {"localAdaptations": [], "patches": []}
    latest = dict(baseline)
    for milestone, paths in [("M1", existing[:1]), ("M2", existing[:2] + added), ("M3", existing[:1])]:
        changes = []
        for path in paths:
            (engine / path).write_text(milestone + "\n")
            sha = m0.sha256(engine / path)
            changes.append({"path": path, "beforeSha256": latest.get(path), "forkSha256": sha})
            latest[path] = sha
        lock["localAdaptations"].append({"milestone": milestone, "files": changes})
    lock["patches"] = [{"path": path, "forkSha256": latest[path]} for path in existing[:2] + added]
    lock_path.write_text(json.dumps(lock))
    if state != "untracked":
        git("add", "engine")
    if state == "committed":
        git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "M1-M3")
    assert all((path in m0._local_engine()) == (state != "untracked") for path in added)
    _assert_declared_port_deltas(plan, lock)

    for path in existing + added:
        original = (engine / path).read_bytes()
        (engine / path).write_text("undeclared edit\n")
        with pytest.raises(AssertionError):
            _assert_declared_port_deltas(plan, lock)
        (engine / path).write_bytes(original)
    for field in ("chain", "patch"):
        tampered = copy.deepcopy(lock)
        if field == "chain":
            tampered["localAdaptations"][2]["files"][0]["beforeSha256"] = "0" * 64
        else:
            tampered["patches"][0]["forkSha256"] = "0" * 64
        with pytest.raises(AssertionError):
            _assert_declared_port_deltas(plan, tampered)
    for path in ("sprite_gen/undeclared.py", "tests/test_undeclared.py"):
        (engine / path).write_text("undeclared addition\n")
        git("add", "engine/sprite-gen/" + path)
        with pytest.raises(AssertionError):
            _assert_declared_port_deltas(plan, lock)
        git("rm", "--cached", "-q", "engine/sprite-gen/" + path)
        (engine / path).unlink()
    (engine / added[0]).unlink()
    with pytest.raises(FileNotFoundError):
        _assert_declared_port_deltas(plan, lock)


def test_port_plan_verify_detects_tampered_local_hash():
    plan = json.loads((ABSORPTION / "m0-port-plan.json").read_text())
    row = next(r for r in plan["files"] if r["path"] == "sprite_gen/video/loop.py")
    row["sha256"]["local"] = "0" * 64
    plan["files"] = [r for r in plan["files"] if r["path"] != "sprite_gen/video/frames.py"]
    errors = m0.verify_port_plan(plan)
    assert "local engine file changed since plan: sprite_gen/video/loop.py" in errors
    assert "local engine file not in plan: sprite_gen/video/frames.py" in errors


def test_output_guard_never_overwrites_inputs_or_existing_results(tmp_path, monkeypatch):
    monkeypatch.setattr(m0, "ROOT", tmp_path / "repo")
    (tmp_path / "repo/.data/projects").mkdir(parents=True)
    (tmp_path / "repo/docs/product/absorption").mkdir(parents=True)
    existing = tmp_path / "repo/docs/product/absorption/m0-baseline-manifest.json"
    existing.write_text("{}")
    refuse = lambda *a, **k: pytest.raises(SystemExit, match="refused")
    with refuse():
        m0.guard_output(tmp_path / "repo/.data/projects/x.json")
    with refuse():
        m0.guard_output(tmp_path / "repo/engine/out.json")
    with refuse():
        m0.guard_output(existing)
    assert m0.guard_output(existing, replace=True) == existing.resolve()
    (tmp_path / "link.json").symlink_to(tmp_path / "repo/.data/projects/target.json")
    with refuse():
        m0.guard_output(tmp_path / "link.json", replace=True)
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    with refuse():
        m0.guard_output(upstream / "plan.json", forbidden=(upstream,))
    work = tmp_path / "work"
    work.mkdir()
    (work / "old-cache").write_text("x")
    with refuse():
        m0.guard_output(work, directory=True)
    with refuse():
        m0.guard_output(tmp_path / "repo/docs/product/absorption/work", directory=True)
    assert m0.guard_output(tmp_path / "new-work", directory=True) == (tmp_path / "new-work").resolve()


def test_fetched_tree_must_equal_the_pinned_commit(tmp_path):
    repo = tmp_path / "repo"
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True).stdout.decode().strip()
    repo.mkdir()
    git("init", "-q")
    (repo / "a.py").write_text("print(1)\n")
    (repo / "docs").mkdir()
    (repo / "docs/b.md").write_text("b\n")
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "x")
    commit = git("rev-parse", "HEAD")
    out = tmp_path / "out"
    out.mkdir()
    subprocess.run(["tar", "-x", "-C", str(out)], input=subprocess.run(["git", "-C", str(repo), "archive", commit], capture_output=True, check=True).stdout, check=True)
    assert m0.verify_tree(repo, commit, out) == []
    (out / "a.py").write_text("print(2)\n")
    (out / "extra.txt").write_text("x")
    assert sorted(e.split(":")[0] for e in m0.verify_tree(repo, commit, out)) == ["a.py", "extra.txt"]


def test_replay_never_calls_an_observer_and_flags_engine_change(tmp_path, monkeypatch):
    monkeypatch.setattr(m0, "ROOT", tmp_path)
    monkeypatch.delenv("SPRITE_DATA_DIR", raising=False)
    monkeypatch.setattr(m0, "_local_engine", lambda: {"sprite_gen/video/loop.py": "changed"})
    folder = _synthetic_project(tmp_path)
    clip = {"clipId": "c1", "loop": True, "cells": [], "recipe": {"class": "reproducible-current", "impliedDefaults": {}},
            "job": {"jobId": "j1", "videoId": "v1", "options": {"state": "walk", "frameSelection": "vision"}, "spillReferenceAssetId": None}}
    manifest = {"engine": {"treeDigest": m0.digest({})}, "projects": [{"projectId": "1", "folder": m0.rel(folder), "videos": [], "clips": [clip]}]}
    fail = lambda *a, **k: pytest.fail("process_clip must not run for a vision (observer) recipe")
    report = m0.replay(manifest, tmp_path / "work", process_clip=fail)
    assert report["results"][0]["skipped"] == "observer-required-not-run"
    assert report["engineMatchesBaseline"] is False and report["allReproduced"] is False
    assert "등록하지 않으며" in report["outputs"]
    assert "SPRITE_DATA_DIR" not in m0.os.environ  # 격리 경로가 이후 시험·프로세스로 새지 않음


def test_recipe_rules_never_rerun_a_different_policy():
    current = {"version": m0.CURRENT_VIDEO_PROCESSING, "options": {"state": "walk", "key": "auto", "repairMode": "off"}}
    ok = m0.classify_recipe(current, quality_version="2.34.0", source_present=True)
    assert ok["class"] == "reproducible-current" and ok["impliedDefaults"] == {"frameSelection": "uniform", "frameJudge": "rules"}
    assert m0.classify_recipe({**current, "version": "video-processing-v3"}, quality_version="2.34.0", source_present=True)["class"] == "legacy-unreproducible"
    assert m0.classify_recipe({**current, "version": "video-processing-v5-sprite-gen-2.45"}, quality_version="2.34.0", source_present=True)["class"] == "legacy-unreproducible"
    assert m0.classify_recipe({**current, "options": {"overlapWrap": "on"}}, quality_version="2.34.0", source_present=True)["class"] == "legacy-unreproducible"
    assert m0.classify_recipe(current, quality_version="2.45.3", source_present=True)["class"] == "legacy-unreproducible"
    assert m0.classify_recipe(current, quality_version="2.34.0", source_present=False)["class"] == "source-missing"
    assert m0.classify_recipe(None, quality_version="2.34.0", source_present=True)["class"] == "no-recorded-recipe"
    assert m0.classify_derived({"sourceProcessing": {"kind": "clip-follow", "source": {"projectId": "gone"}}}, {"here"})["class"] == "source-missing"


def _synthetic_project(root: pathlib.Path) -> pathlib.Path:
    folder = root / ".data/projects/p--1"
    (folder / "assets").mkdir(parents=True)
    cell = folder / "assets/a1--cell.png"
    cell.write_bytes(b"cell-v1")
    (folder / "project.json").write_text('{"projectId":"1"}')
    snapshot = {"projectId": "1", "schemaVersion": 1, "revision": 3, "assets": [{}], "videos": [], "generations": [],
                "frames": [{"frameVersionId": "f1", "imageAssetId": "a1", "rawAssetId": "a1", "extractionVersion": "raw-v1"}],
                "clips": [{"clipId": "c1", "clipRevisionId": "r1", "name": "walk", "loop": True, "endBehavior": "hold-last",
                           "occurrences": [{"frameVersionId": "f1", "durationMs": 125, "transform": {}, "pixelEdits": []}]}]}
    db = sqlite3.connect(folder / "project.sqlite3")
    db.executescript("CREATE TABLE projects(id,snapshot,updated);CREATE TABLE assets(id,metadata,path);"
                     "CREATE TABLE videos(id,metadata,path);CREATE TABLE jobs(id,project_id,operation,status,request_hash,idem,body,created,updated);")
    db.execute("INSERT INTO projects VALUES ('1',?,'')", (json.dumps(snapshot),))
    db.execute("INSERT INTO assets VALUES ('a1',?,?)", (json.dumps({"sha256": m0.sha256(cell)}), "assets/a1--cell.png"))
    db.commit()
    db.close()
    return folder


def test_project_baseline_detects_changed_cells_and_timing(tmp_path, monkeypatch):
    monkeypatch.setattr(m0, "ROOT", tmp_path)
    folder = _synthetic_project(tmp_path)
    stored = m0._project_baseline(folder, "2.34.0", {"1"})
    assert stored["folder"] == ".data/projects/p--1" and stored["clips"][0]["cells"][0]["path"] == ".data/projects/p--1/assets/a1--cell.png"
    assert stored["clips"][0]["recipe"]["class"] == "no-recorded-recipe"
    assert m0.compare_baseline(stored, m0._project_baseline(folder, "2.34.0", {"1"})) == []

    (folder / "assets/a1--cell.png").write_bytes(b"cell-v2")
    changed = m0._project_baseline(folder, "2.34.0", {"1"})
    assert changed["assetIntegrity"]["mismatch"] == ["a1"]
    assert m0.baseline_self_check({"projects": [changed]})

    db = sqlite3.connect(folder / "project.sqlite3")
    snapshot = json.loads(db.execute("SELECT snapshot FROM projects").fetchone()[0])
    snapshot["clips"][0]["occurrences"][0]["durationMs"] = 126
    db.execute("UPDATE projects SET snapshot=?", (json.dumps(snapshot),))
    db.commit()
    db.close()
    assert any("durationMs" in e for e in m0.compare_baseline(stored, m0._project_baseline(folder, "2.34.0", {"1"})))


def _assert_absorption_documents_safe(folder):
    for path in [*folder.glob("*.json"), *folder.glob("*.md")]:
        portable = path.suffix == ".json" or path.name.lower().startswith(("m0-", "m0_"))
        # 후속 milestone 보고서의 증거 경로는 허용하되 credential은 모든 문서에서 차단한다.
        for match in m0.FORBIDDEN_TEXT.finditer(path.read_text()):
            if portable or match.group().startswith(("sk-", "xai-", "Bearer ")):
                pytest.fail(f"{path.name}: forbidden local path or credential")


def test_committed_m0_files_hold_no_local_paths_or_credentials():
    _assert_absorption_documents_safe(ABSORPTION)
    baseline = json.loads((ABSORPTION / "m0-baseline-manifest.json").read_text())
    assert m0.baseline_self_check(baseline) == []


@pytest.mark.parametrize("name", ["m0-port-plan.json", "M0_REPORT_2026-10-21.md", "m0-notes.md"])
@pytest.mark.parametrize("text", ["/Users/synthetic/project", "/home/synthetic/project", r"C:\\Users\\synthetic"])
def test_absorption_document_guard_rejects_portable_local_paths(tmp_path, name, text):
    (tmp_path / name).write_text(text)
    with pytest.raises(pytest.fail.Exception, match=name):
        _assert_absorption_documents_safe(tmp_path)


@pytest.mark.parametrize("milestone", ["M1", "M2", "M3"])
def test_absorption_document_guard_allows_milestone_evidence_paths(tmp_path, milestone):
    (tmp_path / f"{milestone}_REVIEW.md").write_text("/Users/synthetic/evidence\n/home/synthetic/evidence\n" + r"C:\\Users\\synthetic")
    _assert_absorption_documents_safe(tmp_path)


@pytest.mark.parametrize("name", ["m0-port-plan.json", "M0_REPORT.md", "M1_RUN.md", "M2_REVIEW.md", "M3_IMPLEMENTATION.md"])
@pytest.mark.parametrize("credential", ["sk-" + "A" * 24, "xai-" + "A" * 24, "Bearer synthetic-token"])
def test_absorption_document_guard_rejects_credentials_in_all_milestones(tmp_path, name, credential):
    evidence = "relative/evidence" if name.startswith(("m0-", "M0_")) else "/Users/synthetic/evidence"
    (tmp_path / name).write_text(evidence + "\n" + credential)
    with pytest.raises(pytest.fail.Exception, match=name):
        _assert_absorption_documents_safe(tmp_path)


def test_dump_never_follows_a_planted_temp_symlink_and_keeps_the_old_file_on_failure(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text("SOURCE")
    out = tmp_path / "out.json"
    # 예전 구현이 쓰던 고정 임시 이름과 출력 경로 자체를 모두 원본을 가리키는 symlink로 심어 둔다.
    (tmp_path / "out.json.tmp").symlink_to(source)
    out.symlink_to(source)
    m0.dump(out, {"a": 1})
    assert source.read_text() == "SOURCE"
    assert not out.is_symlink() and json.loads(out.read_text()) == {"a": 1}
    assert oct(out.stat().st_mode & 0o777) == "0o644"

    def broken_replace(*args):
        raise OSError("disk full")
    monkeypatch.setattr(m0.os, "replace", broken_replace)
    with pytest.raises(OSError):
        m0.dump(out, {"a": 2})
    with pytest.raises(TypeError):
        m0.dump(out, {"a": object()})
    assert json.loads(out.read_text()) == {"a": 1} and source.read_text() == "SOURCE"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.json", "out.json.tmp", "source.json"]  # 새 임시 파일이 남지 않음


def _replay_manifest(folder, *clip_ids):
    clip = lambda cid: {"clipId": cid, "loop": True, "cells": [], "recipe": {"class": "reproducible-current", "impliedDefaults": dict(m0.IMPLIED_OPTION_DEFAULTS)},
                        "job": {"jobId": "j-" + str(cid)[-4:], "videoId": "v1", "options": {"state": "walk"}, "spillReferenceAssetId": None}}
    return {"engine": {"treeDigest": m0.digest({})},
            "projects": [{"projectId": "1", "folder": m0.rel(folder), "videos": [{"videoId": "v1", "path": m0.rel(folder) + "/videos/v1.mp4"}],
                          "clips": [clip(c) for c in clip_ids]}]}


@pytest.mark.parametrize("bad", ["../escape", "ABSOLUTE", "c1/../../escape", "", ".hidden", "c1"])
def test_replay_refuses_unsafe_clip_ids_before_processing_anything(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(m0, "ROOT", tmp_path)
    monkeypatch.setattr(m0, "_local_engine", lambda: {})  # process_clip 호출 여부만 판정 기준으로 남긴다
    monkeypatch.delenv("SPRITE_DATA_DIR", raising=False)
    folder = _synthetic_project(tmp_path)
    escape = tmp_path / "escape"
    escape.mkdir()
    (escape / "keep.txt").write_text("user file")
    bad = str(escape) if bad == "ABSOLUTE" else bad  # "c1" = 중복 clipId
    work = tmp_path / "work"
    fail = lambda *a, **k: pytest.fail("process_clip must not run when any manifest clipId is unsafe")
    with pytest.raises(SystemExit, match="refused replay"):
        m0.replay(_replay_manifest(folder, "c1", bad), work, process_clip=fail)  # 안전한 c1이 먼저 있어도 처리 전 전체 거절
    assert sorted(p.name for p in escape.iterdir()) == ["keep.txt"] and (escape / "keep.txt").read_text() == "user file"
    assert not work.exists() and "SPRITE_DATA_DIR" not in m0.os.environ


def test_replay_refuses_manifest_inputs_outside_the_project_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(m0, "ROOT", tmp_path)
    monkeypatch.setattr(m0, "_local_engine", lambda: {})
    folder = _synthetic_project(tmp_path)
    fail = lambda *a, **k: pytest.fail("process_clip must not run")
    manifest = _replay_manifest(folder, "c1")
    manifest["projects"][0]["videos"][0]["path"] = "../outside.mp4"
    with pytest.raises(SystemExit, match="input path outside"):
        m0.replay(manifest, tmp_path / "work", process_clip=fail)
    manifest = _replay_manifest(folder, "c1")
    manifest["projects"][0]["folder"] = "elsewhere"
    with pytest.raises(SystemExit, match="input path outside"):
        m0.replay(manifest, tmp_path / "work", process_clip=fail)


def test_baseline_differences_say_whether_preserved_data_or_only_analysis_changed():
    stored = {"projects": [{"clips": [{"cells": [{"sha256": "a", "durationMs": 125}], "recipe": {"class": "x"}, "evidence": {"source": "unknown"},
                                       "job": {"evidence": {"present": True}}}]}],
              "referencedEvidence": {"missing": 1}}
    current = copy.deepcopy(stored)
    clip = current["projects"][0]["clips"][0]
    clip["cells"][0]["durationMs"] = 126
    clip["recipe"]["class"] = "y"
    clip["evidence"]["source"] = "verified"
    clip["job"]["evidence"]["present"] = False
    current["referencedEvidence"]["missing"] = 2
    kinds = {e.split(" ")[1].rsplit(":", 1)[0]: e.split(" ")[0] for e in m0.compare_baseline(stored, current)}
    assert kinds == {"baseline.projects[0].clips[0].cells[0].durationMs": "[input]",
                     "baseline.projects[0].clips[0].recipe.class": "[analysis]",
                     "baseline.projects[0].clips[0].evidence.source": "[analysis]",
                     "baseline.projects[0].clips[0].job.evidence.present": "[input]",  # 작업 출력 파일 증거는 보존 자료
                     "baseline.referencedEvidence.missing": "[docs-evidence]"}


def test_function_plan_links_app_callers_to_changed_engine_functions_and_lists_untraced_boundaries(tmp_path, monkeypatch):
    repo, upstream = tmp_path / "repo", tmp_path / "upstream"
    files = {
        "repo/adapters/x.py": "from alignment.pipeline import _engine\nfrom sprite_gen.video.follow import follow_offsets\n\n\n"
                              "def run(frames, name):\n    loop, canvas = _engine(\"video.loop\"), _engine(\"video.canvas\")\n"
                              "    loop.resize_cell(frames)\n    out = canvas.pad(frames)\n    helper(loop)\n    return _engine(name).anything\n",
        "repo/tests/test_x.py": "def test_cell():\n    assert loop.resize_cell(1)\n",
        "repo/engine/sprite-gen/sprite_gen/__init__.py": "",
        "repo/engine/sprite-gen/sprite_gen/video/__init__.py": "",
        "repo/engine/sprite-gen/sprite_gen/video/loop.py": "def resize_cell(a):\n    return _scale(a)\n\n\ndef _scale(a):\n    return a\n",
        "repo/engine/sprite-gen/sprite_gen/video/canvas.py": "def pad(a):\n    return a\n",
        "repo/engine/sprite-gen/sprite_gen/video/follow.py": "def follow_offsets(a):\n    return a\n",
        "upstream/v2.45.3/sprite_gen/__init__.py": "",
        "upstream/v2.45.3/sprite_gen/video/__init__.py": "",
        "upstream/v2.45.3/sprite_gen/video/loop.py": "import os\n\n\ndef resize_cell(a):\n    return _scale(a)\n\n\ndef _scale(a):\n"
                                                     "    return a + int(os.environ.get('SPRITE_GEN_SCALE', '0'))\n\n\ndef seam(a):\n    return a\n",
        "upstream/v2.45.3/sprite_gen/video/canvas.py": "def pad(a, margin=0):\n    return a\n",
        "upstream/v2.45.3/sprite_gen/video/follow.py": "def follow_offsets(a):\n    return a\n",
        "upstream/v2.45.3/tests/test_loop.py": "from sprite_gen.video import loop\nloop.resize_cell\n",
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    monkeypatch.setattr(m0, "ROOT", repo)
    monkeypatch.setattr(m0, "ENGINE", repo / "engine/sprite-gen")
    monkeypatch.setattr(m0, "verify_tree", lambda *a: [])
    monkeypatch.setattr(m0, "_local_engine", lambda: {})
    plan = m0.build_function_plan(upstream)
    rows = {s["symbol"]: s for s in plan["appSymbols"]}
    assert rows["resize_cell"]["status"] == "same" and rows["resize_cell"]["changedHelpers"] == ["_scale"]
    assert rows["resize_cell"]["callers"] == ["adapters/x.py:7"] and rows["resize_cell"]["appTests"] == ["tests/test_x.py"]
    assert rows["resize_cell"]["upstreamTests"] == ["tests/test_loop.py"]
    assert rows["pad"]["status"] == "signature-changed" and rows["follow_offsets"]["callers"] == ["adapters/x.py:2"]
    loop = next(f for f in plan["files"] if f["file"] == "sprite_gen/video/loop.py")
    assert loop["new"] == ["seam"] and loop["changed"] == ["_scale"] and loop["envAdded"] == ["SPRITE_GEN_SCALE"]
    assert [u["at"] for u in plan["unresolved"]] == ["adapters/x.py:8", "adapters/x.py:9", "adapters/x.py:10"]


def test_committed_function_plan_matches_m0_pinned_app_callers(tmp_path,monkeypatch):
    plan = json.loads((ABSORPTION / "m0-function-plan.json").read_text())
    # M0 is a historical investigation; later milestones must not rewrite its evidence.
    names=subprocess.run(['git','ls-tree','-r','--name-only','c48e46e','--','adapters','services','alignment'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.splitlines()
    for name in names:
        if name.endswith('.py'):
            target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(subprocess.run(['git','show','c48e46e:'+name],cwd=ROOT,capture_output=True,check=True).stdout)
    monkeypatch.setattr(m0,'ROOT',tmp_path)
    uses, unresolved = m0.app_engine_uses()
    assert [{k: s[k] for k in ("module", "symbol", "callers")} for s in plan["appSymbols"]] == uses
    assert plan["unresolved"] == unresolved and plan["upstreamCommit"] == m0.PINS["v2.45.3"]
    video = next(s for s in plan["appSymbols"] if s["symbol"] == "generate_video")
    assert video["status"] == "signature-changed" and "POST" in video["protectedPolicy"]
