"""Local motion prompts and structured anatomy/equipment settings.

Uses the project's sprite-gen v2.34 parsers and prompt pieces (Apache-2.0).
The existing FrameRoom prompt stays byte-identical when no structure is given.
No generation, reference redraw, image mirroring or visual verification occurs
here. Equipment sides are the character's own sides, independent of the view.

API strings separate entries with a semicolon or newline. ``bodyPlan`` accepts
``quadruped`` or ``the rider=biped; the horse=quadruped``. ``equipment`` accepts
upstream ``the watch=left wrist`` and the short form ``sword:right; shield:left``.
Short items default to a hand for bipeds and to a side for other body plans;
an explicit body part always remains the caller's choice.
"""
from __future__ import annotations

import re

from services.api import store as s

STATES = ("idle", "walk", "run", "jump", "attack", "dance", "wave", "cheer")
DIRECTIONS = ("side", "front", "back", "front_diagonal", "back_diagonal")


def _modules():
    from .provider import _engine
    _engine()  # Never fall back to the shared, independently updated skill.
    from sprite_gen.video import body_plan
    from sprite_gen.gen import handedness, prompt_parts
    return body_plan, handedness, prompt_parts


def _specs(params: dict, field: str) -> list[str]:
    value = params.get(field, "")
    if not isinstance(value, str) or len(value) > 2000:
        raise s.AppError("VIDEO_SETTING", f"{field}는 2,000자 이하 문자열이어야 합니다.", details={"field": field})
    if not value.strip():
        return []
    specs = [entry.strip() for entry in re.split(r"[;\n]+", value) if entry.strip()]
    if not specs:
        raise s.AppError("VIDEO_SETTING", f"{field} 설정을 입력하세요.", details={"field": field})
    return specs


def parse_structured_params(params: dict):
    """Validate upstream grammar and view placement; keep API strings intact.

    Upstream command parsers raise SystemExit. API callers always get AppError,
    before any job is enqueued or any provider request can be submitted.
    """
    body_specs, equipment_specs = _specs(params, "bodyPlan"), _specs(params, "equipment")
    # Old/default requests don't need to load the newly added grammar modules.
    if not body_specs and not equipment_specs:
        return [], []
    body_plan, handedness, _ = _modules()
    try:
        bodies = body_plan.parse_all(body_specs)
    except SystemExit as exc:
        raise s.AppError("VIDEO_BODY_PLAN", "체형은 biped, quadruped, legless 또는 인물=체형으로 입력하세요.",
                         details={"field": "bodyPlan", "reason": str(exc)}) from exc
    try:
        specs = []
        for spec in equipment_specs:
            # '=' is the upstream grammar; ':' is only a convenient UI alias.
            if "=" not in spec and ":" in spec:
                item, side_part = (part.strip() for part in spec.rsplit(":", 1))
                if len(side_part.split()) == 1 and body_plan.biped(bodies):
                    side_part += " hand"
                spec = f"{item}={side_part}"
            specs.append(spec)
        items = handedness.parse_all(specs)
        for item in items:
            handedness.placement(item.side, params.get("direction", "side"), params.get("facing", "right"))
    except SystemExit as exc:
        raise s.AppError("VIDEO_EQUIPMENT", "장비는 sword:right; shield:left 또는 장비=left wrist 형식으로 입력하세요.",
                         details={"field": "equipment", "reason": str(exc)}) from exc
    return bodies, items


def _choice(params, field, choices, default):
    value = params.get(field, default)
    if value not in choices:
        raise s.AppError("VIDEO_SETTING", f"영상 {field} 설정을 확인하세요.", details={"field": field})
    return value


def build_motion_prompt_parts(params: dict):
    """Return upstream Prompt with text and conflict notes, without editing user text."""
    state = _choice(params, "state", STATES, "walk")
    direction = _choice(params, "direction", DIRECTIONS, "side")
    facing = _choice(params, "facing", ("right", "left"), "right")
    custom = params.get("motionPrompt", "")
    if not isinstance(custom, str) or len(custom) > 2000:
        raise s.AppError("VIDEO_PROMPT", "동작 설명은 2,000자 이하로 입력하세요.")
    custom = " ".join(custom.split())
    bodies, items = parse_structured_params(params)
    body_plan, handedness, prompt_parts = _modules()
    biped = body_plan.biped(bodies)
    has_legless = any(body.plan == "legless" for body in bodies)
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
    if not biped:
        motions.update(
            idle="The character stays still, standing or resting exactly as in the image, gently breathing and "
                 "settling its loose parts. Whatever supports it never lifts, steps, shuffles or slides; no travelling or turning.",
            attack="The character performs one attack with what it already holds, or with its own body if it holds "
                   "nothing: a windup, one clean strike, a held impact pose, then a recovery to the exact starting stance.",
            dance="The character dances in place with small, evenly repeated movements and gentle body sway, "
                  "returning to the starting stance without turning or travelling.",
            wave="The character makes a friendly wave with a movable part already present in the image, then "
                 "settles back to the exact starting stance. Any carried equipment stays in its original place.",
            cheer="The character celebrates in place with an expressive body pose, holds it for a beat, then "
                  "settles back to the exact starting stance at an even rhythm.",
        )
        if has_legless:
            motions["walk"] = "The character moves naturally in place at a walking pace, using its own body as in the image."
            motions["run"] = "The character moves quickly in place, using its own body as in the image."
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
    parts = ["2D game sprite animation.", custom or motions[state]]
    if anatomy := body_plan.text(bodies):
        parts.append(anatomy)
    parts.append(views[direction])
    if state in ("walk", "run"):
        parts.append("Stay in place as if on a treadmill; do not draw a treadmill or ground line.")
    if state == "walk" and params.get("model") == "grok-imagine-video-1.5-lite" and not custom:
        if biped:
            parts.append("A slow, relaxed, unhurried walk: small, low steps with the feet barely leaving the ground, "
                         "a gentle arm swing close to the body and no bounce — never running, jogging, skipping or hopping.")
        elif has_legless:
            parts.append("A slow, relaxed, unhurried pace: small, even movements — never rushing, running or leaping.")
        else:
            parts.append("A slow, relaxed, unhurried walk: small, low steps with the feet barely leaving the ground and "
                         "no bounce — never trotting, galloping, running, jogging, skipping or hopping.")
    if state == "walk" and params.get("model") == "grok-imagine-video-1.5-lite" and direction == "back_diagonal":
        parts.append("The head stays level and steady over the body the whole time: it does not bob, nod, tilt or sway "
                     "from side to side; " + ("only the legs, arms and the ends of the hair move." if biped else
                     "only what it moves on and its loose ends, such as a tail, a mane or hair, move."))
    parts.append(
        "Every grip stays as shown in the image. Keep equipment in the same hand; never switch, drop or add gear. "
        "A hand the action does not use stays with its equipment. Preserve the design, colors, proportions and clothing."
        if biped else
        "Anything held, worn or carried stays exactly as shown in the image, held the same way and in the same place; "
        "never switch, drop or add gear. A part the action does not use stays as drawn. Preserve the design, colors, "
        "proportions and outfit.")
    parts += [
        ("The full body, hair and all equipment stay inside the frame with margin and constant scale. " if biped else
         "The full body, loose parts and all equipment stay inside the frame with margin and constant scale. ") +
        "Camera completely locked: no zoom, pan, rotation or reframing.",
        "Keep the input's perfectly flat background color for the whole clip: no shadows, particles, lighting changes or effects. "
        "Crisp frames without motion blur, smears or afterimages.",
        "Return to the starting pose at the end." if state in ("idle", "attack") or
        (state in ("walk", "run") and direction in ("front_diagonal", "back_diagonal")) else
        "Consistent, evenly paced motion so the animation can loop.",
    ]
    prompt = prompt_parts.Prompt(" ".join(parts), caller=custom, sep=" ")
    turned = facing if direction in handedness.LATERAL_VIEWS else None
    prompt.note(facing=turned or prompt_parts.NO_TURN)
    if items:
        own_sides = " ".join(f"Keep {item.item} on the character's own {item.where()}, as in the input image."
                             for item in items)
        placement = handedness.text(items, direction, turned, clip=True, gait=biped and state in ("walk", "run"))
        prompt.add("handed", own_sides + " " + placement, handed=items)
    return prompt


def build_motion_prompt(params: dict) -> str:
    return build_motion_prompt_parts(params).text
