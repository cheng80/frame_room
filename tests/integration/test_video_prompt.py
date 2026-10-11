"""Structured prompt/API contracts. No model calls or visual-quality claims."""
import hashlib
import io
import itertools
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from adapters.spritegen import video_provider as provider
from adapters.spritegen.video_prompt import (
    DIRECTIONS, STATES, build_motion_prompt, build_motion_prompt_parts, parse_structured_params,
)
from services.api import store as s
from services.api.main import app

EXTRA_BODIES = ("reference", "arachnid", "winged_biped", "winged_quadruped")
INVALID_BODIES = (
    "centaur", "the bird=winged", "=arachnid", " =winged_biped", "arachnid; winged_biped",
    "the spider=arachnid; winged_quadruped", "the spider=arachnid; THE SPIDER=biped",
    "the bird=winged_biped; the   bird=winged_quadruped",
    "the rider=biped; THE RIDER=arachnid", "the dragon=winged_quadruped; the spider=unknown",
    "=reference", "reference; biped", "the creature=reference; THE CREATURE=arachnid",
)


@pytest.mark.parametrize("body", EXTRA_BODIES)
@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("facing", ("right", "left"))
@pytest.mark.parametrize("model", provider.MODELS)
@pytest.mark.parametrize("custom", ("", "Advance cautiously in place."))
def test_catalog_anatomy_in_every_motion_view_and_validation(body, state, direction, facing, model, custom):
    catalog = json.loads((Path(__file__).resolve().parents[2] / "packages/contracts/body-plans.json").read_text())
    anatomy = next(entry["motionText"] for entry in catalog if entry["value"] == body)
    params = dict(bodyPlan=body, state=state, direction=direction, facing=facing, model=model,
                  motionPrompt=custom, equipment="bag:left; badge:right")
    before = dict(params)
    for generation in (False, True):
        checked = provider.validate_params(params, generation=generation)
        assert all(checked[key] == value for key, value in params.items())
    text = build_motion_prompt(checked)
    assert params == before
    assert anatomy and anatomy in text
    assert "attachment points" in anatomy
    assert "character's own left" in text and "character's own right" in text
    for phrase in ("both feet planted", "one free hand", "same hand", "gentle arm swing", "legs, arms",
                   "left hand", "right hand"):
        assert phrase not in text
    if custom:
        assert custom in text and "walks naturally" not in text
    if body == "reference":
        assert "anatomy shown in the input image" in text
        assert "Do not impose a human pose or a fixed limb count" in text
        assert "Never add, remove or transform body parts" in text
        for phrase in ("small, low steps", "all four legs", "on two legs", "walks naturally", "runs naturally"):
            assert phrase not in text
    elif body == "arachnid":
        assert "exactly eight legs" in text
        assert "all four legs" not in text
    else:
        assert ("exactly two legs and two wings" if body == "winged_biped" else
                "exactly four legs and two wings") in text
        assert "wings remain wings" in text
        assert "walk and run on the ground without taking flight" in text.lower()
        assert "stay grounded" not in text
    if body != "reference":
        assert "as in the image" in anatomy and "human arms" in anatomy


@pytest.mark.parametrize("generation", (False, True))
@pytest.mark.parametrize("body", INVALID_BODIES)
def test_new_body_grammar_rejects_unknown_unnamed_and_duplicate_figures(body, generation):
    with pytest.raises(s.AppError) as caught:
        provider.validate_params({"bodyPlan": body}, generation=generation)
    assert caught.value.code == "VIDEO_BODY_PLAN"
    assert caught.value.status == 422
    assert caught.value.details["field"] == "bodyPlan"


@pytest.mark.parametrize("body", EXTRA_BODIES)
def test_named_catalog_body_and_mixed_scene_preserve_grammar_and_equipment(body):
    single = f"  the   creature = {body.upper()}  "
    scene = f"{single}; the rider=biped\nthe horse=quadruped; the snake=legless"
    for spec in (single, scene):
        params = {"bodyPlan": spec, "equipment": "bag:left; ring=right claw",
                  "motionPrompt": "Advance cautiously in place."}
        checked = provider.validate_params(params, generation=True)
        assert checked["bodyPlan"] == spec
        bodies, items = parse_structured_params(checked)
        assert (bodies[0].plan, bodies[0].figure) == (body, "the creature")
        assert [(item.side, item.part) for item in items] == [("left", ""), ("right", "claw")]
        text = build_motion_prompt(checked)
        assert ("the creature: Keep the anatomy shown" if body == "reference" else
                "the creature: It has exactly") in text
        assert "Advance cautiously in place." in text
        if spec == scene:
            assert "the rider on two legs" in text
            assert "the horse on all four legs, never rising onto its hind legs" in text
            assert "the snake without legs, never growing any" in text


def test_all_new_named_plans_can_share_one_scene():
    text = build_motion_prompt({"bodyPlan": "the spider=arachnid; the bird=winged_biped; the dragon=winged_quadruped; the creature=reference"})
    assert "the creature: Keep the anatomy shown" in text
    for figure, limbs in (("spider", "eight legs"), ("bird", "two legs and two wings"),
                          ("dragon", "four legs and two wings")):
        assert f"the {figure}: It has exactly {limbs}" in text


def test_existing_nonbiped_prompt_bytes_are_preserved():
    # Captured before adding catalog plans, including the existing user's view cleanup.
    rows = [build_motion_prompt(dict(bodyPlan=body, state=state, direction=direction, facing=facing,
                                    model=model, motionPrompt=custom, equipment="bag:left"))
            for body, state, direction, facing, model, custom in itertools.product(
                ("quadruped", "legless", "the rider=biped; the horse=quadruped"),
                STATES, DIRECTIONS, ("right", "left"), provider.MODELS, ("", "Sneak cautiously in place."))]
    assert len(rows) == 960
    assert hashlib.sha256(json.dumps(rows).encode()).hexdigest() == "090ca13bc8d547eedc295c2a1533cb6321eee090937b790fa8353a49b8c1c5de"


def test_defaults_and_saved_frame_counts_are_preserved():
    for generation in (False, True):
        result = provider.validate_params({}, generation=generation)
        assert result["maxFrames"] == 8
        assert result["between"] == result["startFoot"] == "auto"
        assert result["bodyPlan"] == result["equipment"] == ""
        assert "startIndex" not in result
        for state in STATES:
            assert provider.validate_params({"state": state}, generation=generation)["maxFrames"] == (8 if state == "walk" else 32)
            for count in (8, 12, 24, 32, 64):
                params = {"state": state, "maxFrames": count}
                assert provider.validate_params(params, generation=generation)["maxFrames"] == count
                assert params == {"state": state, "maxFrames": count}


@pytest.mark.parametrize("between,foot", list(itertools.product(("auto", "on", "off"), ("auto", "left", "right"))))
def test_processing_controls(between, foot):
    result = provider.validate_params({"between": between, "startFoot": foot, "startIndex": 63}, generation=False)
    assert result["between"] == between and result["startFoot"] == foot and result["startIndex"] == 63
    assert provider.validate_params({"startIndex": 0}, generation=False)["startIndex"] == 0


@pytest.mark.parametrize("field,value", [
    ("between", "yes"), ("between", None), ("between", []),
    ("startFoot", "screen-left"), ("startFoot", None),
    ("startIndex", -1), ("startIndex", 64), ("startIndex", 0.5),
    ("startIndex", True), ("startIndex", "1"), ("startIndex", None),
    ("bodyPlan", []), ("bodyPlan", None), ("bodyPlan", "x" * 2001),
    ("equipment", {}), ("equipment", False), ("equipment", "x" * 2001),
])
def test_invalid_field_types_and_ranges_are_app_errors(field, value):
    with pytest.raises(s.AppError):
        provider.validate_params({field: value}, generation=False)


def test_output_phase_is_only_for_local_processing():
    with pytest.raises(s.AppError, match="생성 완료된 영상"):
        provider.validate_params({"startIndex": 0}, generation=True)


@pytest.mark.parametrize("body", [
    "centaur", "=quadruped", "biped; quadruped", "the rider=biped; THE RIDER=quadruped", ";\n",
])
def test_invalid_body_grammar_is_not_system_exit(body):
    with pytest.raises(s.AppError) as caught:
        provider.validate_params({"bodyPlan": body}, generation=True)
    assert caught.value.details["field"] == "bodyPlan"


@pytest.mark.parametrize("equipment", [
    "sword", "sword:middle", ":right", "sword=", "sword=front wrist", ";\n",
])
def test_invalid_equipment_grammar_is_not_system_exit(equipment):
    with pytest.raises(s.AppError) as caught:
        provider.validate_params({"equipment": equipment}, generation=True)
    assert caught.value.details["field"] == "equipment"


def test_short_and_upstream_grammars_preserve_input_and_own_sides():
    params = {"bodyPlan": " biped ", "equipment": " sword:right; shield:left\nthe black watch=left wrist "}
    checked = provider.validate_params(params, generation=True)
    assert checked["equipment"] == params["equipment"] and checked["bodyPlan"] == params["bodyPlan"]
    bodies, items = parse_structured_params(checked)
    assert [body.plan for body in bodies] == ["biped"]
    assert [(item.item, item.side, item.part) for item in items] == [
        ("sword", "right", "hand"), ("shield", "left", "hand"), ("the black watch", "left", "wrist"),
    ]
    _, items = parse_structured_params({"bodyPlan": "quadruped", "equipment": "bag:left; armor=right shoulder"})
    assert [(item.side, item.part) for item in items] == [("left", ""), ("right", "shoulder")]


@pytest.mark.parametrize("direction,facing,picture,depth", [
    ("front", "right", "right", None), ("front", "left", "right", None),
    ("back", "right", "left", None), ("back", "left", "left", None),
    ("front_diagonal", "right", "right", "far"), ("front_diagonal", "left", "right", "near"),
    ("back_diagonal", "right", "left", "far"), ("back_diagonal", "left", "left", "near"),
    ("side", "right", None, "far"), ("side", "left", None, "near"),
])
def test_equipment_placement_tracks_character_sides(direction, facing, picture, depth):
    text = build_motion_prompt({"equipment": "sword:left", "direction": direction, "facing": facing})
    assert "Keep sword on the character's own left hand" in text
    if picture:
        assert f"hand at the {picture} of the picture" in text
    if depth == "far":
        assert "on the far side of the body" in text
    elif depth == "near":
        assert "nearer the viewer" in text


def test_two_handed_equipment_does_not_say_other_hand_is_bare():
    text = build_motion_prompt({"equipment": "sword:right; shield:left"})
    assert "character's own right hand" in text and "character's own left hand" in text
    assert "stays bare" not in text
    assert "shows each time that arm swings forward" in text


@pytest.mark.parametrize("body", ["quadruped", "legless", "the rider=biped; the horse=quadruped"])
@pytest.mark.parametrize("state", STATES)
def test_nonbiped_defaults_never_require_human_anatomy(body, state):
    text = build_motion_prompt({"bodyPlan": body, "state": state, "direction": "back_diagonal", "model": provider.MODELS[1]})
    for phrase in ("both feet planted", "one free hand", "same hand", "gentle arm swing", "legs, arms"):
        assert phrase not in text
    if body == "legless":
        assert "never grows legs or feet" in text
        assert "small, low steps" not in text
    else:
        assert "all four legs" in text


def test_scene_body_constraints_and_custom_motion_remain_explicit():
    text = build_motion_prompt({"bodyPlan": "the rider=biped; the horse=quadruped", "motionPrompt": "Advance cautiously in place."})
    assert "the rider on two legs" in text
    assert "the horse on all four legs, never rising onto its hind legs" in text
    assert "Advance cautiously in place." in text
    assert "walks naturally" not in text


def test_default_prompt_freeze_across_states_views_models_and_custom_motion():
    # Captured from FrameRoom's pre-migration build_motion_prompt, 2026-10-06.
    # Keeps view/camera/key locks, equipment grip and measured Lite clauses stable.
    rows = []
    for state, direction, facing, model, custom in itertools.product(
        STATES, DIRECTIONS, ("right", "left"), provider.MODELS, ("", "Sneak cautiously in place."),
    ):
        params = dict(state=state, direction=direction, facing=facing, model=model, motionPrompt=custom)
        text = build_motion_prompt(params)
        assert build_motion_prompt({**params, "bodyPlan": "biped"}) == text
        rows.append(text)
    assert len(rows) == 320
    assert hashlib.sha256(json.dumps(rows).encode()).hexdigest() == "9d61983b3d77a2e30cb84a0761f890a9ae2452149b16063db948480ce1c06188"


def test_view_conflict_is_removed_and_equipment_conflict_is_reported():
    custom = "Walk facing left. Carry the sword on the left."
    params = {"motionPrompt": custom, "equipment": "sword:right", "facing": "right"}
    prompt = build_motion_prompt_parts(params)
    assert params["motionPrompt"] == custom
    assert "facing left" not in prompt.text
    assert "Carry the sword on the left." in prompt.text
    assert {(note["kind"], note["about"]) for note in prompt.notes} >= {("conflict", "handed")}
    assert not any(note["about"] == "facing" for note in prompt.notes)
    repeated = "Keep sword on the character's own right hand, as in the input image."
    text = build_motion_prompt({"motionPrompt": repeated, "equipment": "sword:right"})
    assert text.count(repeated) == 1


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_custom_view_is_replaced_without_losing_motion_effects_or_own_hands(direction):
    custom = ("오른쪽을 보는 정확한 측면의 이동 중간 자세. side-view walking without glow; "
              "오른손 검, 왼손 방패. no turning to side. 측면 각도를 따르지 않는다.")
    params = {"motionPrompt": custom, "direction": direction, "facing": "left"}
    prompt = build_motion_prompt_parts(params)
    assert params["motionPrompt"] == custom
    assert "오른쪽을 보는" not in prompt.text and "정확한 측면의" not in prompt.text
    assert "side-view walking" not in prompt.text
    for kept in ("이동 중간 자세", "walking without glow", "오른손 검", "왼손 방패",
                 "no turning to side", "측면 각도를 따르지 않는다"):
        assert kept in prompt.text
    expected = {"side": "side-view angle, facing left", "front": "facing the viewer directly",
                "back": "facing directly away", "front_diagonal": "three-quarter front angle",
                "back_diagonal": "three-quarter back angle"}
    assert expected[direction] in prompt.text


def test_direction_only_custom_uses_motion_template_after_cleanup():
    assert build_motion_prompt({"motionPrompt": "side-view, facing left", "direction": "front"}) == \
        build_motion_prompt({"direction": "front"})


@pytest.mark.parametrize("body", (" biped ", *EXTRA_BODIES,
                                  "the rider=biped; the spider=arachnid; the bird=winged_biped; the dragon=winged_quadruped"))
def test_api_rejects_invalid_structure_before_queue_and_preserves_request_snapshot(tmp_path, monkeypatch, body):
    monkeypatch.setattr(s, "DATA", tmp_path / "data")
    monkeypatch.setattr(provider, "login_credential", lambda: pytest.fail("Queue validation must not authenticate"))
    s.init()
    with TestClient(app) as client:
        client.headers["X-Session-Token"] = client.get("/v1/health").json()["sessionToken"]
        project = client.post("/v1/projects", json={"name": "구조화 프롬프트 API 시험"}).json()
        root = "/v1/projects/" + project["projectId"]
        data = io.BytesIO()
        Image.new("RGBA", (32, 32), (100, 70, 40, 255)).save(data, format="PNG")
        response = client.post(root + "/assets", files={"files": ("synthetic-api-fixture.png", data.getvalue(), "image/png")})
        assert response.status_code == 201
        asset = response.json()["assets"][0]
        project = client.get(root).json()
        request = dict(operation="generate_video", inputRevision=project["revision"], assetIds=[asset["assetId"]])
        for invalid in ({"bodyPlan": "biped; quadruped"}, {"equipment": "sword:middle"}, {"startIndex": 0}):
            response = client.post(root + "/jobs", json={**request, "idempotencyKey": s.uid(), "params": invalid})
            assert response.status_code == 422, response.text
        for invalid in INVALID_BODIES:
            for operation in ("generate_video", "process_video"):
                response = client.post(root + "/jobs", json={**request, "operation": operation,
                                       "idempotencyKey": s.uid(), "params": {"bodyPlan": invalid}})
                assert response.status_code == 422, response.text
                assert response.json()["code"] == "VIDEO_BODY_PLAN"
            response = client.post(root + "/video-batches", json={"inputRevision": project["revision"],
                                   "idempotencyKey": s.uid(), "items": [
                                       {"assetId": asset["assetId"], "params": {"bodyPlan": "arachnid"}},
                                       {"assetId": asset["assetId"], "params": {"bodyPlan": invalid}},
                                   ]})
            assert response.status_code == 422, response.text
            assert response.json()["code"] == "VIDEO_BODY_PLAN"
        assert client.get(root + "/jobs").json()["jobs"] == []
        params = dict(bodyPlan=body, equipment="sword:right; shield:left", between="off", startFoot="left", maxFrames=12,
                      direction="front", motionPrompt="  side-view walking without glow; 오른손 검  ")
        response = client.post(root + "/jobs", json={**request, "idempotencyKey": s.uid(), "params": params})
        assert response.status_code == 202, response.text
        job = s.get_job(response.json()["jobId"])
        assert job["request"]["params"] == params
        assert provider.validate_params(job["request"]["params"], generation=True)["maxFrames"] == 12
        response = client.post(root + "/video-batches", json={"inputRevision": project["revision"],
                               "idempotencyKey": s.uid(), "items": [{"assetId": asset["assetId"], "params": params}]})
        assert response.status_code == 202, response.text
        queued = s.get_job(response.json()["jobs"][0]["jobId"])
        assert queued["request"]["params"] == params


@pytest.mark.parametrize("body", EXTRA_BODIES)
def test_catalog_body_process_enqueue_preserves_request(tmp_path, monkeypatch, body):
    from tests.integration.test_video_processing import make_clip

    monkeypatch.setattr(s, "DATA", tmp_path / "data")
    monkeypatch.setattr(provider, "login_credential", lambda: pytest.fail("Local processing must not authenticate"))
    s.init()
    clip = make_clip(tmp_path / "synthetic-source", count=8)
    with TestClient(app) as client:
        client.headers["X-Session-Token"] = client.get("/v1/health").json()["sessionToken"]
        project = client.post("/v1/projects", json={"name": "체형별 후처리 접수 시험"}).json()
        root = "/v1/projects/" + project["projectId"]
        response = client.post(root + "/videos", files={"file": ("synthetic-fixture.mp4", clip.read_bytes(), "video/mp4")},
                               data={"expectedRevision": project["revision"]})
        assert response.status_code == 201, response.text
        uploaded = response.json()
        params = {"bodyPlan": body, "videoId": uploaded["video"]["videoId"], "startFoot": "left"}
        response = client.post(root + "/jobs", json={"operation": "process_video", "assetIds": [],
                               "inputRevision": uploaded["snapshot"]["revision"], "params": params, "idempotencyKey": s.uid()})
        assert response.status_code == 202, response.text
        assert s.get_job(response.json()["jobId"])["request"]["params"] == params
