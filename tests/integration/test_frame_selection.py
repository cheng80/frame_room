"""Frame selection around uniform slots. Synthetic fixtures, fixture Codex catalogs and fake
observers only (conftest blocks real observer calls): no Luna call, no generation."""
import json
from pathlib import Path
import subprocess

import pytest
from PIL import Image

from adapters.spritegen import frame_selection as fs, video_processing as vp
from tests.integration.test_video_processing import make_clip

OK = {k: ("no" if bad == "yes" else "yes") for k, bad in fs.PROBLEM.items()}


def observer(overrides=None, calls=None, text=None):
    """Fake Luna: every id clean unless overridden by source index."""
    def call(images, prompt, directory, **kw):
        if calls is not None:
            calls.append(prompt)
        ids = [x.strip() for x in prompt.split("The sheet ids are: ")[1].split(".")[0].split(",")]
        frames = [{"id": i, **OK, **(overrides or {}).get(int(i[1:]), {}), "note": ""} for i in ids]
        return {"text": text if text is not None else json.dumps({"frames": frames}), "receipt": {"fake": True}}
    return call


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    return make_clip(tmp_path_factory.mktemp("selection-fixture"), count=33, period=16)


def catalog(tmp_path, monkeypatch, *models):
    """Fixture Codex catalog: (slug, overrides) pairs; a str path writes raw text instead."""
    path = tmp_path / "models_cache.json"
    if len(models) == 1 and isinstance(models[0], str):
        path.write_text(models[0])
    else:
        path.write_text(json.dumps({"models": [{"slug": slug, "visibility": "list", "input_modalities": ["text", "image"],
                                                "supported_reasoning_levels": [{"effort": "medium"}], **extra}
                                               for slug, extra in models]}))
    monkeypatch.setattr(fs, "catalog_path", lambda: path)


def test_default_and_explicit_uniform_are_unchanged(clip, tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "codex_observe", lambda *a, **kw: pytest.fail("uniform must not observe"))
    old = vp.process_clip(clip, tmp_path / "a", {"loopMode": "full"})
    new = vp.process_clip(clip, tmp_path / "b", {"loopMode": "full", "frameSelection": "uniform"})
    times = old["source"]["timesMs"]
    assert [f["sourceFrameIndex"] for f in old["frames"]] == [i * 33 // 8 for i in range(8)]
    assert [f["durationMs"] for f in old["frames"]] == [f["durationMs"] for f in new["frames"]]
    assert sum(f["durationMs"] for f in old["frames"]) == round(times[33] - times[0])
    assert "frameSelection" not in old["selection"] and "alternateFrames" not in old
    assert old["options"]["frameSelection"] == "uniform" and old["options"]["maxFrames"] == 8


def test_validate_params_keeps_saved_shape_and_rejects_bad_values():
    from services.api.store import AppError
    from adapters.spritegen.video_provider import validate_params
    plain = validate_params({"videoId": "v"}, generation=False)
    assert "frameSelection" not in plain and "frameJudge" not in plain and plain["maxFrames"] == 8
    assert validate_params({"videoId": "v", "frameSelection": "vision", "frameJudge": "rules"}, generation=False)["frameSelection"] == "vision"
    for bad in ({"frameSelection": "luna"}, {"frameJudge": "gpt"}, {"frameSelection": "vision", "matchClipId": "c"}):
        with pytest.raises(AppError):
            validate_params({"videoId": "v", **bad}, generation=False)
    # Legacy auto is rules; omitted stays omitted (stored jobs keep their uniform meaning).
    assert validate_params({"videoId": "v", "frameSelection": "vision", "frameJudge": "auto"}, generation=False)["frameJudge"] == "rules"


def test_fresh_requests_default_to_vision_rules_but_explicit_uniform_and_cycle_match_do_not():
    from adapters.spritegen.video_provider import with_fresh_selection
    assert with_fresh_selection({"videoId": "v"}) == {"frameSelection": "vision", "frameJudge": "rules", "videoId": "v"}
    assert with_fresh_selection({"videoId": "v", "frameJudge": "auto"})["frameJudge"] == "auto"  # validated -> rules
    for kept in ({"videoId": "v", "frameSelection": "uniform"}, {"videoId": "v", "matchClipId": "c"},
                 {"frameSelection": "vision", "frameJudge": "rules"}):
        assert with_fresh_selection(kept) is kept


@pytest.mark.parametrize("judge", ("laya", "jev"))
def test_removed_judges_fail_before_any_observer_call(clip, tmp_path, monkeypatch, judge):
    from services.api.store import AppError
    from adapters.spritegen.video_provider import validate_params, with_fresh_selection
    for params in ({"videoId": "v", "frameSelection": "vision", "frameJudge": judge}, with_fresh_selection({"videoId": "v", "frameJudge": judge})):
        with pytest.raises(AppError) as error:
            validate_params(params, generation=False)
        assert error.value.code == "VIDEO_SETTING" and "제거" in error.value.message
    monkeypatch.setattr(fs, "codex_observe", lambda *a, **kw: pytest.fail("a removed judge never reaches the observer"))
    with pytest.raises(vp.VideoProcessingError) as failed:
        vp.process_clip(clip, tmp_path / "x", {"loopMode": "full", "frameSelection": "vision", "frameJudge": judge})
    assert failed.value.code == "VIDEO_INVALID_PARAMS" and not (tmp_path / "x").exists()
    assert not hasattr(fs, "resolve_judge") and not hasattr(fs, "capability")


def test_windows_are_disjoint_ordered_and_capped():
    for start, end, count in ((0, 33, 8), (5, 30, 8), (0, 73, 8), (0, 24, 12), (0, 64, 32), (0, 9, 8)):
        groups = fs.windows(start, end, count)
        flat = [i for g in groups for i in g]
        assert flat == sorted(set(flat)) and len(flat) <= fs.MAX_CANDIDATES
        assert all(start <= i < end for i in flat)
        assert [c for c, g in zip(fs.uniform(start, end, count), groups) if c not in g] == []
        assert groups[0][0] == start  # never reaches before the selected range
    assert all(len(g) == 1 for g in fs.windows(0, 64, 32))


def test_large_slot_count_keeps_uniform_without_observation(clip, tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "codex_observe", lambda *a, **kw: pytest.fail("no candidate pool, no call"))
    r = vp.process_clip(clip, tmp_path / "w", {"loopMode": "full", "maxFrames": 32, "frameSelection": "vision", "frameJudge": "rules"})
    assert r["selection"]["frameSelection"]["status"] == "uniform-kept"
    assert [f["sourceFrameIndex"] for f in r["frames"]] == fs.uniform(0, 33, 32)


@pytest.mark.parametrize("loop_mode", ("full", "manual"))
def test_moved_first_pick_preserves_total_time_and_keeps_alternate(clip, tmp_path, monkeypatch, loop_mode):
    # Uniform 0 is rejected (extra limb); the neighbour 1 replaces it.
    monkeypatch.setattr(fs, "codex_observe", observer({0: {"extra_or_missing_parts": "yes"}}))
    params = {"loopMode": loop_mode, "frameSelection": "vision", "frameJudge": "rules", "maxFrames": 8,
              **({"startFrame": 0, "endFrame": 33} if loop_mode == "manual" else {})}
    r = vp.process_clip(clip, tmp_path / loop_mode, params)
    times, fsel = r["source"]["timesMs"], r["selection"]["frameSelection"]
    assert [f["sourceFrameIndex"] for f in r["frames"]][:2] == [1, 4]
    assert sum(f["durationMs"] for f in r["frames"]) == round(times[33] - times[0]) == r["selection"]["durationMs"]
    assert all(f["durationMs"] > 0 for f in r["frames"]) and len(r["frames"]) == 8
    if r["selection"]["loop"]:  # manual loops wrap the skipped lead-in onto the last frame
        assert r["frames"][0]["durationMs"] == round(times[4] - times[1])
    else:  # a one-play clip lets the first frame cover the range start
        assert r["frames"][0]["durationMs"] == round(times[4] - times[0])
    assert r["frames"][0]["frameSelection"] == {"slot": 0, "label": "keep", "reasons": ["ALL_CHECKS_OK"], "source": "rules",
                                                "slotStatus": "keep", "slotReasons": [], "changed": True, "uniformSourceFrameIndex": 0}
    alt = r["alternateFrames"]
    assert [a["sourceFrameIndex"] for a in alt] == [0] and "outputFrameIndex" not in alt[0] and "durationMs" not in alt[0]
    assert alt[0]["frameSelection"]["role"] == "uniform-alternative" and alt[0]["frameSelection"]["label"] == "reject"
    assert fsel["status"] == "applied" and fsel["changedSlots"] == 1 and fsel["counts"]["reject"] == 1


def test_boundaries_vfr_and_loop_wrap():
    times = [0, 40, 160, 240, 400, 440, 560]  # variable frame rate timestamps (n+1 boundaries)
    assert fs.boundaries(times, [0, 2, 4], 0, 6, True) == [0, 160, 400, 560]
    assert fs.boundaries(times, [1, 2, 4], 0, 6, True) == [0, 120, 360, 560]  # 40ms lead-in wraps to the last frame
    assert fs.boundaries(times, [1, 2, 4], 0, 6, False) == [0, 160, 400, 560]


@pytest.mark.parametrize("text,problem", (("not json", "OBSERVATION_NOT_JSON"), (json.dumps({"x": 1}), "OBSERVATION_SCHEMA")))
def test_malformed_observation_never_keeps(clip, tmp_path, monkeypatch, text, problem):
    monkeypatch.setattr(fs, "codex_observe", observer(text=text))
    r = vp.process_clip(clip, tmp_path / "w", {"loopMode": "full", "frameSelection": "vision", "frameJudge": "rules"})
    fsel = r["selection"]["frameSelection"]
    assert fsel["observation"]["problems"] == [problem] and fsel["counts"]["keep"] == 0
    assert fsel["status"] == "review" and fsel["changedSlots"] == 0
    assert [f["sourceFrameIndex"] for f in r["frames"]] == fs.uniform(0, 33, 8)
    assert all(s["reasons"][0] == "NO_KEEP_CANDIDATE_UNIFORM_KEPT" for s in fsel["slots"])


def test_parse_observations_rejects_unknown_duplicate_and_missing_fields():
    good = {"id": "F001", **OK, "note": ""}
    frames, problems = fs.parse_observations(json.dumps({"frames": [
        good, {**good, "id": "F009"}, {"id": "F002", **OK, "blur_or_smear": "maybe"},
        {"id": "F003", **OK}, {"id": "F003", **OK, "body_cropped": "yes"}]}), ["F001", "F002", "F003"])
    assert set(frames) == {"F001", "F002"} and frames["F002"]["blur_or_smear"] is None
    assert problems == ["OBSERVATION_UNKNOWN_ID", "OBSERVATION_DUPLICATE_ID"]
    assert fs.rules(frames["F002"], {})[0] == "review"
    assert fs.policy({**OK, "blur_or_smear": "unknown"}, {}) == ("review", ["UNKNOWN:blur_or_smear"])
    assert fs.policy(None, {}) == ("review", ["OBSERVATION_MISSING"])
    assert fs.policy(OK, {"empty": True})[0] == "reject"
    assert fs.policy(OK, {"edgeTouch": True}) == ("review", ["CONFLICT_EDGE_TOUCH_VS_NOT_CROPPED"])


def test_observation_cache_hit_isolation_and_corruption(tmp_path):
    sheet, ref, other = tmp_path / "s.png", tmp_path / "r.png", tmp_path / "o.png"
    Image.new("RGB", (8, 8), (1, 2, 3)).save(sheet)
    Image.new("RGB", (8, 8), (9, 9, 9)).save(ref)
    Image.new("RGB", (8, 8), (7, 7, 7)).save(other)
    calls, luna = [], {"observer": "gpt-6-luna-medium"}
    first = fs.observe([sheet], ref, ["F001"], tmp_path / "a", tmp_path / "cache", observer(calls=calls), **luna)
    second = fs.observe([sheet], ref, ["F001"], tmp_path / "b", tmp_path / "cache", observer(calls=calls), **luna)
    assert (first["cacheHit"], second["cacheHit"], len(calls), second["frames"]) == (False, True, 1, first["frames"])
    fs.observe([sheet], other, ["F001"], tmp_path / "c", tmp_path / "cache", observer(calls=calls), **luna)
    assert len(calls) == 2  # a different reference is a different observation
    (tmp_path / "cache" / "observations" / f"{first['cacheKey']}.json").write_text("{broken")
    third = fs.observe([sheet], ref, ["F001"], tmp_path / "d", tmp_path / "cache", observer(calls=calls), **luna)
    assert third["cacheHit"] is False and len(calls) == 3
    failed = fs.observe([sheet], ref, ["F002"], tmp_path / "e", tmp_path / "cache", lambda *a: (_ for _ in ()).throw(RuntimeError("auth")), **luna)
    assert failed["problems"] == ["OBSERVATION_FAILED"] and not (tmp_path / "cache" / "observations" / f"{failed['cacheKey']}.json").exists()
    assert ("gpt-6-luna", "medium", "gpt-6-luna-medium") == tuple(first["keyMaterial"][k] for k in ("model", "effort", "observer"))


@pytest.mark.codex_command
def test_codex_command_pins_subscription_model_and_strips_parent_identity(tmp_path, monkeypatch):
    seen = {}

    def fake_run(command, **kw):
        seen.update(command=command, env=kw["env"])
        out = command[command.index("-o") + 1]
        open(out, "w").write(json.dumps({"frames": []}))
        return subprocess.CompletedProcess(command, 0, '{"type":"turn.completed","usage":{"input_tokens":5,"output_tokens":1}}\n', "")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("CODEX_THREAD_ID", "parent")
    monkeypatch.setattr(fs.subprocess, "run", fake_run)
    monkeypatch.setenv("TYPESAFE_API_KEY", "old-judge-key")  # the removed judge's key never reaches Codex either
    reply = fs.codex_observe([tmp_path / "s.png"], "p", tmp_path / "obs", model="gpt-6-luna", effort="medium")
    c = seen["command"]
    assert c[c.index("-m") + 1] == "gpt-6-luna" and "--ignore-user-config" in c and "--output-schema" in c
    assert 'model_provider="openai"' in c and 'forced_login_method="chatgpt"' in c
    assert "OPENAI_API_KEY" not in seen["env"] and "CODEX_THREAD_ID" not in seen["env"] and "TYPESAFE_API_KEY" not in seen["env"]
    assert reply["receipt"]["usage"] == {"input_tokens": 5, "output_tokens": 1} and reply["receipt"]["fallbackModel"] is None


def test_cycle_alignment_path_skips_observation(clip, tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "codex_observe", lambda *a, **kw: pytest.fail("targetFrameCount keeps its own sampling"))
    try:
        r = vp.process_clip(clip, tmp_path / "w", {"loopMode": "manual", "startFrame": 0, "endFrame": 32, "targetFrameCount": 8,
                                                     "between": "off", "frameSelection": "vision", "frameJudge": "rules"})
    except vp.VideoProcessingError as exc:  # environment without RIFE still never observes
        assert exc.code.startswith("VIDEO_")
        return
    assert r["selection"]["frameSelection"]["status"] == "skipped" and "alternateFrames" not in r


def test_repaired_lineage_follows_the_chosen_index(clip, tmp_path, monkeypatch):
    real = vp._repair_selection

    def fake_repair(files, selection, options, directory, interpolation=None):
        files, record = real(files, selection, options, directory, interpolation)
        paths = list(files)
        target = directory / 'synthetic-repaired-4.png'
        with Image.open(files[3]) as a, Image.open(files[5]) as b:
            Image.blend(a.convert('RGBA'), b.convert('RGBA'), .5).save(target)
        paths[4] = target
        return paths, {**record, "sourceFrameIndices": [4], "lineage": {"4": {"method": "rife-flow-repair", "sourceFrameIndices": [3, 5], "fraction": .5}}}
    monkeypatch.setattr(vp, "_repair_selection", fake_repair)
    monkeypatch.setattr(fs, "codex_observe", observer({4: {"blur_or_smear": "yes"}}))
    r = vp.process_clip(clip, tmp_path / "w", {"loopMode": "full", "frameSelection": "vision", "frameJudge": "rules"})
    chosen = r["frames"][1]
    assert chosen["sourceFrameIndex"] == 3 and chosen["interpolated"] is False and "interpolation" not in chosen
    assert r["alternateFrames"][0]["sourceFrameIndex"] == 4 and r["alternateFrames"][0]["interpolated"] is True
    alternate = r['alternateFrames'][0]
    assert alternate['interpolation']['sourceFrameIndices'] == [3, 5]
    assert Path(alternate['keyedPath']).read_bytes() != Path(alternate['originalKeyedPath']).read_bytes()


def test_sequence_gap_reverts_to_uniform_with_reason(tmp_path):
    keyed = []
    for i in range(12):
        path = tmp_path / f"{i}.png"
        Image.new("RGBA", (8, 8), (i * 10, 0, 0, 255)).save(path)
        keyed.append(path)
    times = [i * 100 for i in range(13)]
    report = fs.sequence_check([0, 6, 7, 9], [0, 3, 6, 9], 0, 12, times, keyed)
    assert "TIMING_GAP_TOO_LONG" in report["reasons"] and report["totalMs"] == 1200


def test_job_publishes_recommendations_without_touching_user_review(tmp_path, monkeypatch, clip):
    from fastapi.testclient import TestClient
    from services.api import store as s
    from services.api.main import app
    from tests.integration.test_video_jobs import new, load, upload, queue, run
    monkeypatch.setattr(s, "DATA", tmp_path / "data")
    s.init()
    calls = []
    monkeypatch.setattr(fs, "codex_observe", observer({0: {"extra_or_missing_parts": "yes"}}, calls))
    with TestClient(app) as c:
        c.headers["X-Session-Token"] = c.get("/v1/health").json()["sessionToken"]
        p, v = upload(c, new(c), clip.read_bytes())
        before = run(queue(c, p, params={"videoId": v["videoId"], "loopMode": "full", "frameSelection": "uniform"}).json())
        p = load(c, p)
        old_clip, old_frames = p["clips"][0], {f["frameVersionId"]: dict(f) for f in p["frames"]}
        job = run(queue(c, p, params={"videoId": v["videoId"], "loopMode": "full", "frameSelection": "vision",
                                      "frameJudge": "rules"}).json())
        assert before["status"] == job["status"] == "needs_review" and len(calls) == 1
        p = load(c, p)
        assert p["clips"][0] == old_clip and all(old_frames[k] == f for f in p["frames"] if (k := f["frameVersionId"]) in old_frames)
        clip_new = next(cl for cl in p["clips"] if cl["clipId"] == job["result"]["clipId"])
        frames = {f["frameVersionId"]: f for f in p["frames"]}
        slots = [frames[o["frameVersionId"]] for o in clip_new["occurrences"]]
        assert [f["sourceFrameIndex"] for f in slots][:2] == [1, 4] and len(slots) == 8
        assert sum(o["durationMs"] for o in clip_new["occurrences"]) == sum(o["durationMs"] for o in old_clip["occurrences"])
        alternates = [f for f in frames.values() if f.get("selectionDecision", {}).get("role") == "uniform-alternative"]
        assert [f["sourceFrameIndex"] for f in alternates] == [0]
        assert alternates[0]["frameVersionId"] not in {o["frameVersionId"] for o in clip_new["occurrences"]}
        for f in slots + alternates:  # automatic labels never write user review state
            assert f["review"] == "pending" and f["hidden"] is False and "reviewReason" not in f
        assert slots[0]["selectionDecision"]["label"] == "keep" and alternates[0]["selectionDecision"]["label"] == "reject"
        processing = job["result"]["processing"]
        assert processing["outputFrames"] == 8 and processing["selection"]["frameSelection"]["changedSlots"] == 1
        # Re-running the same request (e.g. after a failed publication) reuses the observation cache.
        run(queue(c, p := load(c, p), params={"videoId": v["videoId"], "loopMode": "full", "frameSelection": "vision",
                                                "frameJudge": "rules"}).json())
        assert len(calls) == 1 and (tmp_path / "data" / "cache" / "frame-selection" / "observations").is_dir()


def test_unknown_with_defect_is_review_not_reject():
    obs, metric = {**OK, "blur_or_smear": "yes", "same_character": "unknown", "note": ""}, {"empty": False, "edgeTouch": False}
    assert fs.policy(obs, metric) == ("review", ["UNKNOWN:same_character", "OBSERVED:blur_or_smear"])
    assert fs.rules(obs, metric)[0] == "review"


def _seam_frames(tmp_path):
    """Frame 1 is a large silhouette next to small ones: moving slot 0 onto it breaks the loop seam."""
    keyed = []
    for i in range(16):
        alpha = Image.new("L", (16, 16), 0)
        alpha.paste(255, (4, 4, 4 + {0: 2, 1: 8, 8: 4}.get(i, 3), 12))
        path = tmp_path / f"{i:03d}.png"
        Image.merge("RGBA", (alpha, alpha, alpha, alpha)).save(path)
        keyed.append(path)
    return keyed, [i * 100 for i in range(17)]


def test_sequence_revert_recomputes_slot_status_and_reasons(tmp_path):
    keyed, times = _seam_frames(tmp_path)
    out, record = fs.select(keyed, 0, 16, 4, times, tmp_path / "sel", observe_call=observer({0: {"blur_or_smear": "yes"}}))
    assert record["sequence"]["reasons"] == ["LOOP_SEAM_WORSE"]
    slot = record["slots"][0]
    assert out == record["appliedSourceFrameIndices"] == [0, 4, 8, 12] and record["changedSlots"] == 0
    assert slot["chosen"] == 0 and slot["changed"] is False and slot["status"] == "review" and record["status"] == "review"
    assert slot["reasons"] == ["SEQUENCE_REVERTED_UNIFORM_KEPT", "SEQUENCE:LOOP_SEAM_WORSE", "OBSERVED:blur_or_smear"]
    assert [s["status"] for s in record["slots"][1:]] == ["keep"] * 3


def test_sequence_revert_reaches_published_selection_decision(tmp_path, monkeypatch, clip):
    from fastapi.testclient import TestClient
    from services.api import store as s
    from services.api.main import app
    from tests.integration.test_video_jobs import new, load, upload, queue, run
    real = fs.sequence_check
    monkeypatch.setattr(fs, "sequence_check", lambda *a, **k: {**(r := real(*a, **k)), "reasons": r["reasons"] + ["LOOP_SEAM_WORSE"]})
    monkeypatch.setattr(s, "DATA", tmp_path / "data")
    s.init()
    monkeypatch.setattr(fs, "codex_observe", observer({0: {"extra_or_missing_parts": "yes"}}))
    with TestClient(app) as c:
        c.headers["X-Session-Token"] = c.get("/v1/health").json()["sessionToken"]
        p, v = upload(c, new(c), clip.read_bytes())
        job = run(queue(c, p, params={"videoId": v["videoId"], "loopMode": "full", "frameSelection": "vision",
                                      "frameJudge": "rules"}).json())
        p = load(c, p)
        clip_new = next(cl for cl in p["clips"] if cl["clipId"] == job["result"]["clipId"])
        frames = {f["frameVersionId"]: f for f in p["frames"]}
        first = frames[clip_new["occurrences"][0]["frameVersionId"]]
        decision = first["selectionDecision"]
        assert first["sourceFrameIndex"] == 0 and decision["changed"] is False and decision["slotStatus"] == "review"
        assert decision["label"] == "reject" and "SEQUENCE:LOOP_SEAM_WORSE" in decision["slotReasons"]
        assert not [f for f in frames.values() if f.get("selectionDecision", {}).get("role") == "uniform-alternative"]
        assert first["review"] == "pending" and "reviewReason" not in first


def test_observer_opt_in_is_allowlisted_per_request_with_separate_cache_and_same_images(clip, tmp_path, monkeypatch):
    from services.api.store import AppError
    from adapters.spritegen.video_provider import validate_params
    assert validate_params({"videoId": "v", "frameSelection": "vision", "frameObserver": "gpt-6.1-sol-medium"},
                           generation=False)["frameObserver"] == "gpt-6.1-sol-medium"
    for bad in ({"frameSelection": "vision", "frameObserver": "gpt-6.1-sol"}, {"frameObserver": "gpt-6-luna-medium"}):
        with pytest.raises(AppError):
            validate_params({"videoId": "v", **bad}, generation=False)
    with pytest.raises(vp.VideoProcessingError):
        vp.process_clip(clip, tmp_path / "x", {"loopMode": "full", "frameSelection": "vision", "frameObserver": "gpt-5"})
    seen = []

    def call(images, prompt, directory, model, effort):
        seen.append((model, effort, [fs._sha(i) for i in images]))
        return observer()(images, prompt, directory)
    monkeypatch.setattr(fs, "codex_observe", call)
    cache = tmp_path / "cache"
    runs = {}
    for n, name in enumerate(("gpt-6-luna-medium", "gpt-6.1-sol-medium", "gpt-6.1-sol-medium")):
        params = {"loopMode": "full", "frameSelection": "vision", "observationCacheDir": str(cache), "frameObserver": name}
        runs.setdefault(name, []).append(vp.process_clip(clip, tmp_path / f"run{n}", params)["selection"]["frameSelection"])
    assert [(m, e) for m, e, _ in seen] == [("gpt-6-luna", "medium"), ("gpt-6.1-sol", "medium")]  # third run: cache hit
    assert seen[0][2] == seen[1][2]  # identical image bytes for both observers
    luna, sol = runs["gpt-6-luna-medium"][0], runs["gpt-6.1-sol-medium"]
    assert luna["observer"]["model"] == "gpt-6-luna" and sol[0]["observer"]["model"] == "gpt-6.1-sol"
    assert luna["observation"]["cacheKey"] != sol[0]["observation"]["cacheKey"] == sol[1]["observation"]["cacheKey"]
    assert sol[1]["observation"]["cacheHit"] is True and luna["sheet"]["imageSha256"] == sol[0]["sheet"]["imageSha256"]


def test_observation_images_fit_codex_limits_and_carry_reference(tmp_path):
    keyed = [tmp_path / f"k{i}.png" for i in range(9)]
    for i, path in enumerate(keyed):
        im = Image.new("RGBA", (120, 240), (0, 0, 0, 0))
        im.paste((10 + i, 120, 40, 255), (30, 20, 90, 220))
        im.save(path)
    ref = tmp_path / "ref.png"
    Image.new("RGB", (300, 300), (255, 0, 255)).save(ref)
    rows = [[0, 1, 2], [3, 4, 5], [6, 7, 8]]
    paths = dict(enumerate(keyed))
    overview = fs.contact_sheet(paths, rows, tmp_path / "s.png")
    details = fs.detail_sheets(paths, rows, ref, tmp_path)
    with Image.open(tmp_path / "s.png") as im:
        assert max(im.size) <= fs.IMAGE_MAX_EDGE and overview["cellHeight"] <= 448
    for d in details["images"]:
        with Image.open(d["path"]) as im:
            assert max(im.size) <= fs.IMAGE_MAX_EDGE and min(im.size) <= 768
        assert d["cellHeight"] > overview["cellHeight"]  # the close-up is really larger than the overview cell
    assert details["reference"] is True
    no_ref = fs.detail_sheets(paths, rows, None, tmp_path / "plain")
    assert no_ref["reference"] is False and no_ref["images"][0]["cellHeight"] >= details["images"][0]["cellHeight"]


@pytest.mark.codex_command
def test_codex_observe_uses_requested_allowlisted_model_only(tmp_path, monkeypatch):
    seen = {}

    def fake_run(command, **kw):
        seen["command"] = command
        open(command[command.index("-o") + 1], "w").write(json.dumps({"frames": []}))
        return subprocess.CompletedProcess(command, 0, "", "")
    monkeypatch.setattr(fs.subprocess, "run", fake_run)
    reply = fs.codex_observe([tmp_path / "s.png"], "p", tmp_path / "obs", model="gpt-6.1-sol", effort="medium")
    c = seen["command"]
    assert c[c.index("-m") + 1] == "gpt-6.1-sol" and 'model_reasoning_effort="medium"' in c
    assert reply["receipt"]["requestedModel"] == "gpt-6.1-sol"
    catalog(tmp_path, monkeypatch, ("gpt-6-luna", {}), ("gpt-7-luna", {}))
    fs.codex_observe([tmp_path / "s.png"], "p", tmp_path / "obs3", model="gpt-7-luna", effort="medium")  # the catalog's newest Luna
    assert seen["command"][seen["command"].index("-m") + 1] == "gpt-7-luna"
    seen.clear()
    for model, effort in (("gpt-6.1-sol", "high"), ("gpt-6-luna", "high"), ("gpt-6-sol", "medium"), ("gpt-6-luna-x", "medium"),
                          ("gpt-999-luna", "medium"), ("gpt-6.5-luna", "medium")):  # unlisted / listed but not newest
        with pytest.raises(RuntimeError, match="OBSERVER_NOT_ALLOWED"):
            fs.codex_observe([tmp_path / "s.png"], "p", tmp_path / "obs2", model=model, effort=effort)
    assert seen == {}  # refused before any subprocess


@pytest.mark.parametrize("name", ["gpt-999-luna-medium", "gpt-7-luna-medium", "gpt-6-luna-high", "gpt-6.1-luna-medium"])
def test_unlisted_dynamic_luna_is_refused_before_any_observer_call(clip, tmp_path, monkeypatch, name):
    # Fixture catalog lists only gpt-6-luna: a Luna-shaped id is not a model the catalog supports.
    monkeypatch.setattr(fs, "codex_observe", lambda *a, **kw: pytest.fail("an unsupported observer is never called"))
    with pytest.raises(ValueError):
        fs.observe([], None, [], tmp_path / "o", None, lambda *a, **kw: pytest.fail("never called"), observer=name)
    with pytest.raises(ValueError):
        fs.select([], 0, 9, 3, list(range(10)), tmp_path / "s", observer=name, observe_call=lambda *a, **kw: pytest.fail("never called"))
    with pytest.raises(vp.VideoProcessingError):  # direct process_clip keeps the fixed comparison allowlist
        vp.process_clip(clip, tmp_path / "p", {"loopMode": "full", "frameSelection": "vision", "frameObserver": name})
    assert not (tmp_path / "o").exists() and not (tmp_path / "s").exists()
    # The fixed comparison ids stay valid whatever the catalog says; the newest listed Luna is accepted.
    catalog(tmp_path, monkeypatch, ("gpt-7-luna", {}))
    assert fs._observer("gpt-6-luna-medium") == ("gpt-6-luna", "medium")
    assert fs._observer("gpt-6.1-sol-medium") == ("gpt-6.1-sol", "medium")
    assert fs._observer("gpt-7-luna-medium") == ("gpt-7-luna", "medium")


@pytest.mark.parametrize("slug", ["gpt-" + "9" * 5000 + "-luna", "gpt-99999-luna", "gpt-6.1.2.3.4-luna", "gpt-\u0667-luna", "gpt--luna"])
def test_malformed_or_oversized_catalog_version_fails_closed_without_a_call(clip, tmp_path, monkeypatch, slug):
    from adapters.spritegen.video_provider import frame_selection_capability
    catalog(tmp_path, monkeypatch, (slug, {}))
    assert fs.latest_luna() == (None, "LUNA_NOT_IN_CATALOG")
    assert frame_selection_capability()["observer"]["available"] is False
    with pytest.raises(ValueError):
        fs._observer(slug + "-medium")
    monkeypatch.setattr(fs, "codex_observe", lambda *a, **kw: pytest.fail("no valid Luna means no call"))
    sel = vp.process_clip(clip, tmp_path / "w", {"loopMode": "full", "frameSelection": "vision"})["selection"]["frameSelection"]
    assert sel["observation"]["calls"] == 0 and sel["observation"]["skipped"] is True and sel["changedSlots"] == 0
    assert all(d["label"] == ("reject" if d["metrics"]["empty"] else "review") for d in sel["decisions"])
    catalog(tmp_path, monkeypatch, (slug, {}), ("gpt-6-luna", {}))  # a bad row never hides a valid one
    assert fs.latest_luna() == ("gpt-6-luna", None)


def _rgba(path, size, bbox=None):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    if bbox:
        im.paste((90, 60, 40, 255), bbox)
    im.save(path)
    return path


def _assert_fits(images):
    for path in images:
        with Image.open(path) as im:
            assert max(im.size) <= fs.IMAGE_MAX_EDGE and min(im.size) <= fs.IMAGE_SHORT_EDGE, (path.name, im.size)


@pytest.mark.parametrize("size, bbox, columns, ref", [
    ((480, 480), (10, 200, 470, 240), 3, None),   # wide crop: the overview used to be 6165 x 2048
    ((400, 400), (6, 106, 394, 288), 3, None),    # crop aspect 2:1: overview short side used to be 1368
    ((400, 400), (6, 56, 394, 344), 3, None),     # crop aspect 4/3: detail width used to round to 2049
    ((500, 600), (6, 6, 294, 494), 5, None),      # crop aspect 3/5 x 5 cells: used to be 2050
    ((120, 240), None, 3, None),                  # empty alpha: full canvas crop
    ((120, 240), (30, 20, 90, 220), 3, ((5000, 1), (0, 0, 5000, 1))),   # extreme wide REF: cell height used to be 0
    ((120, 240), (30, 20, 90, 220), 3, ((2, 2000), (0, 0, 2, 2000))),   # extreme tall REF
    ((5000, 2), (0, 0, 5000, 2), 3, None),        # extreme candidate itself: 7512 wide even at cell height 1
])
def test_observation_images_stay_inside_codex_limit_for_odd_shapes(tmp_path, size, bbox, columns, ref):
    rows = [list(range(r * columns, (r + 1) * columns)) for r in range(8)]
    paths = {i: _rgba(tmp_path / f"k{i}.png", size, bbox) for i in range(8 * columns)}
    reference = _rgba(tmp_path / "ref.png", *ref) if ref else None
    overview = fs.contact_sheet(paths, rows, tmp_path / "s.png")
    details = fs.detail_sheets(paths, rows, reference, tmp_path)
    _assert_fits([tmp_path / "s.png", *(d["path"] for d in details["images"])])
    assert overview["cellHeight"] >= 1 and all(d["cellHeight"] >= 1 for d in details["images"])
    for record, path in ((overview, tmp_path / "s.png"), *((d, d["path"]) for d in details["images"])):
        with Image.open(path) as im:  # recorded size is the stored image, shrunk or not
            assert record["size"] == list(im.size)
    assert overview["downscaledToFit"] == (size == (5000, 2))
    for d in details["images"]:
        with Image.open(d["path"]) as im:
            assert im.size[1] <= 768


@pytest.mark.parametrize("bad", [[], {}, ["gpt-6-luna-medium"], {"gpt-6-luna-medium": 1}, 1, None, ""])
def test_non_string_or_unknown_observer_is_a_setting_error_not_a_crash(clip, tmp_path, bad):
    from services.api.store import AppError
    from adapters.spritegen.video_provider import validate_params
    with pytest.raises(AppError) as error:
        validate_params({"videoId": "v", "frameSelection": "vision", "frameObserver": bad}, generation=False)
    assert error.value.code == "VIDEO_SETTING"
    if bad is not None:  # None means "omitted" for process_clip, like every optional field there
        with pytest.raises(vp.VideoProcessingError):
            vp.process_clip(clip, tmp_path / "p", {"loopMode": "full", "frameSelection": "vision", "frameObserver": bad})
    if bad is not None:  # None is the catalog default for select
        with pytest.raises(ValueError):
            fs.select([], 0, 9, 3, list(range(10)), tmp_path / "s", observer=bad)
    with pytest.raises(ValueError):
        fs.observe([], None, [], tmp_path / "o", None, observer=bad)
    plain = validate_params({"videoId": "v", "frameSelection": "vision"}, generation=False)
    assert "frameObserver" not in plain


def test_latest_luna_reads_the_local_catalog_only(tmp_path, monkeypatch):
    medium, image = [{"effort": "medium"}], ["text", "image"]
    catalog(tmp_path, monkeypatch, ("gpt-6-luna", {}), ("gpt-5.6-luna", {}), ("gpt-6.1-sol", {}), ("gpt-6.10-luna", {}),
            ("gpt-6.2-luna", {}), ("gpt-9-luna", {"visibility": "hide"}), ("gpt-8-luna", {"input_modalities": ["text"]}),
            ("gpt-7-luna", {"supported_reasoning_levels": [{"effort": "high"}]}), ("gpt-7.5-luna-mini", {}), ("x/gpt-9-luna", {}))
    assert fs.latest_luna() == ("gpt-6.10-luna", None)  # numeric, not string, version order
    catalog(tmp_path, monkeypatch, ("gpt-6.1-sol", {"supported_reasoning_levels": medium, "input_modalities": image}))
    assert fs.latest_luna() == (None, "LUNA_NOT_IN_CATALOG")  # never another model family
    for raw in ("{broken", "[]", json.dumps({"models": None}), json.dumps({"models": [1, None, {"slug": 5}]})):
        catalog(tmp_path, monkeypatch, raw)
        assert fs.latest_luna()[0] is None
    monkeypatch.setattr(fs, "catalog_path", lambda: tmp_path / "missing.json")
    assert fs.latest_luna() == (None, "LUNA_CATALOG_UNREADABLE")


@pytest.mark.parametrize("field, value", [
    ("input_modalities", "image"), ("input_modalities", {"image": True}), ("input_modalities", None),
    ("supported_reasoning_levels", "medium"), ("supported_reasoning_levels", {"effort": "medium"}),
    ("supported_reasoning_levels", ["medium"]), ("visibility", "hide"), ("visibility", None), ("visibility", "LIST")])
def test_malformed_catalog_rows_never_authorize_a_model(tmp_path, monkeypatch, field, value):
    catalog(tmp_path, monkeypatch, ("gpt-6-luna", {field: value}))
    assert fs.latest_luna() == (None, "LUNA_NOT_IN_CATALOG")
    catalog(tmp_path, monkeypatch, ("gpt-6-luna", {}))  # re-read on every call, no remembered answer
    assert fs.latest_luna() == ("gpt-6-luna", None)


def test_without_a_catalog_luna_nothing_is_observed_and_uniform_frames_stay(clip, tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "catalog_path", lambda: tmp_path / "missing.json")
    monkeypatch.setattr(fs, "codex_observe", lambda *a, **kw: pytest.fail("no Luna in the catalog means no call"))
    params = {"loopMode": "full", "frameSelection": "vision", "frameJudge": "rules", "observationCacheDir": str(tmp_path / "cache")}
    r = vp.process_clip(clip, tmp_path / "w", params)
    sel = r["selection"]["frameSelection"]
    assert sel["observer"] == {"id": None, "model": None, "effort": None, "source": "local-codex-catalog", "available": False,
                               "reason": "LUNA_CATALOG_UNREADABLE"}
    assert sel["observation"] == {"skipped": True, "reason": "LUNA_CATALOG_UNREADABLE", "cacheHit": False, "problems": [], "calls": 0}
    assert [f["sourceFrameIndex"] for f in r["frames"]] == fs.uniform(0, 33, 8) and "alternateFrames" not in r
    assert sel["status"] == "review" and sel["changedSlots"] == 0 and sel["counts"]["keep"] == 0
    assert {d["reasons"][0] for d in sel["decisions"]} <= {"OBSERVATION_MISSING", "CODE_EMPTY_FRAME"}
    assert sum(f["durationMs"] for f in r["frames"]) == round(r["source"]["timesMs"][33] - r["source"]["timesMs"][0])
    assert not (tmp_path / "cache").exists()
    with pytest.raises(vp.VideoProcessingError) as failed:
        vp.process_clip(clip, tmp_path / "x", {**params, "observationCacheOnly": True})
    assert failed.value.code == "VIDEO_FRAME_OBSERVATION_CACHE_MISS"


def test_catalog_luna_reuses_existing_gpt_6_luna_cache_and_isolates_a_newer_luna(clip, tmp_path, monkeypatch):
    seen = []

    def call(images, prompt, directory, model, effort):
        seen.append((model, effort))
        return observer({0: {"extra_or_missing_parts": "yes"}})(images, prompt, directory)
    monkeypatch.setattr(fs, "codex_observe", call)
    cache = {"observationCacheDir": str(tmp_path / "cache"), "loopMode": "full", "frameSelection": "vision"}
    explicit = vp.process_clip(clip, tmp_path / "a", {**cache, "frameObserver": "gpt-6-luna-medium"})["selection"]["frameSelection"]
    default = vp.process_clip(clip, tmp_path / "b", {**cache, "frameJudge": "auto"})
    sel = default["selection"]["frameSelection"]
    assert seen == [("gpt-6-luna", "medium")] and sel["observation"]["cacheHit"] is True  # same key as before the change
    assert sel["observation"]["cacheKey"] == explicit["observation"]["cacheKey"]
    assert sel["observer"] == {"id": "gpt-6-luna-medium", "model": "gpt-6-luna", "effort": "medium", "source": "local-codex-catalog",
                               "available": True}
    assert sel["judge"] == {"requested": "rules", "backend": "rules"} and default["options"]["frameJudge"] == "rules"
    assert {d["source"] for d in sel["decisions"]} == {"rules"} and [f["sourceFrameIndex"] for f in default["frames"]][:2] == [1, 4]
    catalog(tmp_path, monkeypatch, ("gpt-6-luna", {}), ("gpt-6.1-luna", {}))
    newer = vp.process_clip(clip, tmp_path / "c", cache)["selection"]["frameSelection"]
    assert seen[-1] == ("gpt-6.1-luna", "medium") and newer["observation"]["cacheHit"] is False
    assert newer["observation"]["cacheKey"] != sel["observation"]["cacheKey"] and newer["observer"]["id"] == "gpt-6.1-luna-medium"


def test_observation_cache_only_never_calls_the_observer(clip, tmp_path, monkeypatch):
    from services.api.store import AppError
    from adapters.spritegen.video_provider import validate_params
    assert validate_params({"videoId": "v", "frameSelection": "vision", "observationCacheOnly": True}, generation=False)["observationCacheOnly"] is True
    for bad in ({"frameSelection": "vision", "observationCacheOnly": False}, {"frameSelection": "vision", "observationCacheOnly": "true"},
                {"observationCacheOnly": True}):
        with pytest.raises(AppError):
            validate_params({"videoId": "v", **bad}, generation=False)
    params = {"loopMode": "full", "frameSelection": "vision", "observationCacheOnly": True, "observationCacheDir": str(tmp_path / "cache")}
    with pytest.raises(vp.VideoProcessingError) as failed:
        vp.process_clip(clip, tmp_path / "x", params)
    assert failed.value.code == "VIDEO_FRAME_OBSERVATION_CACHE_MISS"
    monkeypatch.setattr(fs, "codex_observe", observer())
    seeded = vp.process_clip(clip, tmp_path / "y", {**params, "observationCacheOnly": None})
    monkeypatch.setattr(fs, "codex_observe", lambda *a, **k: pytest.fail("cache-only must never observe"))
    sel = vp.process_clip(clip, tmp_path / "z", params)["selection"]["frameSelection"]
    assert sel["observation"]["cacheHit"] is True and sel["observation"]["calls"] == 0
    assert sel["observation"]["cacheKey"] == seeded["selection"]["frameSelection"]["observation"]["cacheKey"]


def test_api_fresh_default_is_vision_rules_and_explicit_uniform_or_stored_omission_is_not(tmp_path, monkeypatch, clip):
    from fastapi.testclient import TestClient
    from services.api import store as s
    from services.api.main import app
    from tests.integration.test_video_jobs import new, load, upload, queue, run
    monkeypatch.setattr(s, "DATA", tmp_path / "data")
    s.init()
    calls = []
    monkeypatch.setattr(fs, "codex_observe", observer({0: {"extra_or_missing_parts": "yes"}}, calls))
    with TestClient(app) as c:
        c.headers["X-Session-Token"] = c.get("/v1/health").json()["sessionToken"]
        p, v = upload(c, new(c), clip.read_bytes())
        for judge in ("laya", "jev"):  # removed judges are refused before a job (or a paid call) exists
            refused = queue(c, p, params={"videoId": v["videoId"], "loopMode": "full", "frameJudge": judge})
            assert refused.status_code == 422 and refused.json()["code"] == "VIDEO_SETTING"
        uniform = run(queue(c, p, params={"videoId": v["videoId"], "loopMode": "full", "frameSelection": "uniform"}).json())
        assert calls == [] and "frameSelection" not in uniform["result"]["processing"]["selection"]
        fresh = run(queue(c, p := load(c, p), params={"videoId": v["videoId"], "loopMode": "full"}).json())
        assert len(calls) == 1
        stored = s.get_job(fresh["jobId"])
        assert stored["request"]["params"] == {"videoId": v["videoId"], "loopMode": "full", "frameSelection": "vision", "frameJudge": "rules"}
        sel = fresh["result"]["processing"]["selection"]["frameSelection"]
        assert sel["observer"]["model"] == "gpt-6-luna" and sel["judge"]["backend"] == "rules" and sel["changedSlots"] == 1
    # A request stored before this change (no frameSelection) is re-validated as uniform: no new observer call.
    from adapters.spritegen.video_provider import validate_params
    assert "frameSelection" not in validate_params({"videoId": v["videoId"], "loopMode": "full"}, generation=False)


def test_missing_codex_cli_is_preflighted_and_nothing_is_observed(clip, tmp_path, monkeypatch):
    import shutil
    from adapters.spritegen.video_provider import frame_selection_capability
    which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None if name == "codex" else which(name, *a, **k))
    monkeypatch.setattr(fs, "observe", lambda *a, **kw: pytest.fail("no CLI: the observer is never entered"))
    monkeypatch.setattr(fs, "codex_observe", lambda *a, **kw: pytest.fail("no CLI: never spawned"))
    assert fs.latest_luna() == (None, "CODEX_CLI_MISSING")
    assert frame_selection_capability()["observer"] == {"model": None, "effort": None, "available": False, "reason": "CODEX_CLI_MISSING"}
    r = vp.process_clip(clip, tmp_path / "w", {"loopMode": "full", "frameSelection": "vision", "observationCacheDir": str(tmp_path / "c")})
    sel = r["selection"]["frameSelection"]
    assert sel["observer"]["available"] is False and sel["observer"]["reason"] == "CODEX_CLI_MISSING"
    assert sel["observation"]["calls"] == 0 and sel["observation"]["skipped"] is True
    assert [f["sourceFrameIndex"] for f in r["frames"]] == fs.uniform(0, 33, 8) and sel["changedSlots"] == 0
    assert all(s["status"] == "review" for s in sel["slots"]) and "alternateFrames" not in r
    assert all(d["label"] == ("reject" if d["metrics"]["empty"] else "review") for d in sel["decisions"])
    assert not (tmp_path / "c").exists()


def test_cli_vanishing_after_preflight_is_one_failed_call_review_and_no_other_model(clip, tmp_path, monkeypatch):
    calls = []

    def no_cli(images, prompt, directory, model, effort):
        calls.append(model)
        raise FileNotFoundError("codex")  # what subprocess.run raises when the CLI disappeared after the preflight
    monkeypatch.setattr(fs, "codex_observe", no_cli)
    r = vp.process_clip(clip, tmp_path / "w", {"loopMode": "full", "frameSelection": "vision", "observationCacheDir": str(tmp_path / "c")})
    sel = r["selection"]["frameSelection"]
    assert calls == ["gpt-6-luna"] and sel["observation"]["problems"] == ["OBSERVATION_FAILED"]
    assert [f["sourceFrameIndex"] for f in r["frames"]] == fs.uniform(0, 33, 8) and sel["status"] == "review"
    assert not (tmp_path / "c" / "observations").exists()  # a failure is never cached
