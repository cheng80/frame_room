"""Local pixel/clock oracles; these figures are synthetic, never AI output."""
import copy
import math

import numpy as np
from PIL import Image, ImageDraw
import pytest

from adapters.spritegen import clip_tools as ct
from services.api.store import AppError


def cells():
    frames = []
    for i in range(8):
        dx = round(math.cos(i * math.tau / 8))
        dy = round(2 * math.sin(i * math.tau / 8))
        frame = Image.new("RGBA", (64, 64), (73, 19, 44, 0))
        draw = ImageDraw.Draw(frame)
        draw.rectangle((22 + dx, 10 + dy, 40 + dx, 51 + dy), fill=(100, 110, 120, 255))
        draw.rectangle((29 + dx, 24 + dy, 36 + dx, 37 + dy), fill=(220, 80, 50, 255))
        draw.rectangle((29 + dx, 24 + dy, 30 + dx, 37 + dy), fill=(160, 60, 20, 160))
        frames.append(frame)
    return frames


def params(**override):
    return {"region": [32, 32, 12, 16], "gain": 1., "freq": 2.4, "damping": .6, "onFold": "refuse", **override}


def snapshot():
    return {"projectId": "p", "revision": 7, "clips": [{"clipId": "c", "clipRevisionId": "r", "loop": True,
        "stateId": "walk", "occurrences": [{"occurrenceId": f"o{i}", "frameVersionId": "f", "durationMs": 125} for i in range(8)]}],
        "frames": [{"frameVersionId": "f"}], "alignmentGroups": [{"frameVersionIds": ["f"], "cell": {"width": 64, "height": 64}}], "assets": []}


def test_follow_changes_only_moving_ellipse_and_preserves_inputs_and_timing():
    before = cells(); frozen = [i.tobytes() for i in before]
    durations = [80, 120, 70, 230, 125, 125, 100, 150]
    result, report = ct.follow_frames(before, durations, params())
    assert report["timingMethod"] == "time-weighted-periodic"
    assert report["durationMs"] == sum(durations) == 1000
    assert report["frameCount"] == 8 and not report["unchanged"]
    assert [i.tobytes() for i in before] == frozen
    yy, xx = np.mgrid[:64, :64]
    for a, b, shift in zip(before, result, report["regionShifts"]):
        outside = ((xx - 32 - shift["x"]) / 12) ** 2 + ((yy - 32 - shift["y"]) / 16) ** 2 >= 1
        assert np.array_equal(np.asarray(a)[outside], np.asarray(b)[outside])


@pytest.mark.parametrize("rigid", [False, True])
def test_zero_gain_or_rigid_motion_is_exact_rgba_identity(rigid):
    before = cells()
    if rigid:
        before = [before[0].copy() for _ in before]
    result, report = ct.follow_frames(before, [125] * 8, params(gain=8 if rigid else 0))
    assert report["unchanged"]
    assert all(a.tobytes() == b.tobytes() for a, b in zip(before, result))


def test_uniform_timing_reuses_engine_response_and_uneven_timing_changes_response():
    from sprite_gen.video.follow import body_motion, follow_offsets
    before = cells(); rows, cols, _ = body_motion(before)
    _, report = ct.follow_frames(before, [125] * 8, params())
    expected = follow_offsets(cols, 8., freq=2.4, zeta=.6, gain=1.)
    np.testing.assert_allclose([o["x"] for o in report["offsets"]], expected, atol=1e-6)
    _, weighted = ct.follow_frames(before, [250, 100, 100, 100, 100, 100, 100, 150], params())
    assert weighted["offsets"] != report["offsets"]


def test_fold_is_refused_or_reported_when_lowered():
    before = cells()
    with pytest.raises(AppError) as err:
        ct.follow_frames(before, [125] * 8, params(gain=8, freq=2., damping=.05, region=[32, 32, 6, 7]))
    assert err.value.code == "CLIP_TOOL_FOLD"
    _, lowered = ct.follow_frames(before, [125] * 8, params(gain=8, freq=2., damping=.6, region=[32, 32, 6, 7], onFold="lower"))
    assert lowered["foldLimited"] and 1 <= lowered["gainApplied"] < 8


def test_region_that_moves_outside_cell_is_rejected():
    with pytest.raises(AppError) as err:
        ct.follow_frames(cells(), [125] * 8, params(region=[32, 6, 12, 6]))
    assert err.value.code == "CLIP_TOOL_REGION"


@pytest.mark.parametrize("field,value", [("gain", True), ("gain", float("nan")), ("freq", float("inf")), ("damping", 0),
    ("region", [32, 32, 0, 12]), ("region", [1, 1, 12, 12]), ("onFold", "ignore"), ("unknown", 1)])
def test_invalid_follow_settings_fail_before_processing(field, value):
    with pytest.raises(AppError):
        ct.validate_params(snapshot(), "preview_follow", {"clipId": "c", "clipRevisionId": "r", **params(), field: value})


def test_source_version_limits_and_one_shot_are_rejected():
    p = snapshot(); request = {"clipId": "c", "clipRevisionId": "r", **params()}
    frozen = copy.deepcopy(p)
    assert ct.validate_params(p, "preview_follow", request)["gain"] == 1
    assert p == frozen
    with pytest.raises(AppError) as err:
        ct.validate_params(p, "preview_follow", {**request, "clipRevisionId": "old"})
    assert err.value.status == 409
    p["clips"][0]["loop"] = False
    with pytest.raises(AppError):
        ct.validate_params(p, "preview_follow", request)
    p["clips"][0]["loop"] = True
    p["clips"][0]["occurrences"] *= 4
    p["alignmentGroups"][0]["cell"] = {"width": 1024, "height": 1024}
    with pytest.raises(AppError) as err:
        ct.validate_params(p, "preview_follow", request)
    assert err.value.code == "CLIP_TOOL_LIMIT"


def marked(x=44, marker=(255, 0, 0, 255)):
    frame = Image.new("RGBA", (64, 64))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((20, 10, 44, 55), fill=(90, 90, 90, 255))
    draw.rectangle((x, 27, x + 4, 31), fill=marker)
    return frame


def check_params(**overrides):
    return {"item": "시계", "side": "left", "part": "wrist", "direction": "front", "facing": "right", "marker": "#ff0000", "state": "walk", **overrides}


def test_marker_can_flag_mirrored_item_but_never_passes_no_marker():
    result = ct.check_frames([marked(), marked(15), marked()], check_params())
    assert result["verdict"] == "suspect" and result["framesShown"] == 3
    assert [row["index"] for row in result["suspectFrames"]] == [1]
    assert result["suspectFrames"][0]["reasons"] == ["장비 표식이 지정한 쪽의 반대편에 보입니다."]
    assert ct.check_frames([marked()], check_params())["verdict"] == "clear"
    absent = ct.check_frames([marked(marker=(90, 90, 90, 255))], check_params())
    assert absent["verdict"] == "inconclusive" and absent["unchecked"]


def test_side_without_full_reference_stays_inconclusive():
    result = ct.check_frames([marked()] * 8, check_params(direction="side", facing="left"))
    assert result["verdict"] == "inconclusive" and result["unchecked"]


def test_marker_gray_and_cross_project_reference_are_rejected():
    p = snapshot(); base = {"clipId": "c", "clipRevisionId": "r", **{k: v for k, v in check_params().items() if k != "state"}}
    for extra in ({"marker": "#888888"}, {"marker": "blue"}, {"referenceAssetId": "elsewhere"}):
        with pytest.raises(AppError):
            ct.validate_params(p, "check_handed", {**base, **extra})
