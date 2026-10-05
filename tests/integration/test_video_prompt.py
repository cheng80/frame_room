"""Structured prompt/API contracts. No model calls or visual-quality claims."""
import hashlib
import io
import itertools
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from adapters.spritegen import video_provider as provider
from adapters.spritegen.video_prompt import (
    DIRECTIONS, STATES, build_motion_prompt, build_motion_prompt_parts, parse_structured_params,
)
from services.api import store as s
from services.api.main import app


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


def test_conflicts_are_reported_and_caller_text_is_not_rewritten():
    custom = "Walk facing left. Carry the sword on the left."
    prompt = build_motion_prompt_parts({"motionPrompt": custom, "equipment": "sword:right", "facing": "right"})
    assert custom in prompt.text
    assert {(note["kind"], note["about"]) for note in prompt.notes} >= {("conflict", "facing"), ("conflict", "handed")}
    repeated = "Keep sword on the character's own right hand, as in the input image."
    text = build_motion_prompt({"motionPrompt": repeated, "equipment": "sword:right"})
    assert text.count(repeated) == 1


def test_api_rejects_invalid_structure_before_queue_and_preserves_request_snapshot(tmp_path, monkeypatch):
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
        assert client.get(root + "/jobs").json()["jobs"] == []
        params = dict(bodyPlan=" biped ", equipment="sword:right; shield:left", between="off", startFoot="left", maxFrames=12)
        response = client.post(root + "/jobs", json={**request, "idempotencyKey": s.uid(), "params": params})
        assert response.status_code == 202, response.text
        job = s.get_job(response.json()["jobId"])
        assert job["request"]["params"] == params
        assert provider.validate_params(job["request"]["params"], generation=True)["maxFrames"] == 12
