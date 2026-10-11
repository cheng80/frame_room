"""Shared, conservative cleanup of explicit view phrases in effective prompts."""
from __future__ import annotations

import json
from pathlib import Path
import re

DIRECTIONS = ("side", "front", "back", "front_diagonal", "back_diagonal")
_RULES = json.loads((Path(__file__).resolve().parents[2] / "packages/contracts/view-direction-rules.json").read_text())
_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in _RULES["patterns"]]
_NEGATIVE = re.compile(_RULES["negativePattern"], re.IGNORECASE)


def strip_view_instructions(text: str) -> str:
    # shortcut: only listed Korean/English view phrases; extend shared rules/tests for new phrasing.
    clauses = re.split(r"([.!?。\n,;，；])", text)
    kept = []
    for index in range(0, len(clauses), 2):
        clause = clauses[index]
        if not _NEGATIVE.search(clause):
            for pattern in _PATTERNS:
                clause = pattern.sub("", clause)
        clause = " ".join(clause.split())
        if clause:
            delimiter = clauses[index + 1] if index + 1 < len(clauses) else ""
            kept.append(clause + delimiter)
    return " ".join(kept).strip()


def view_instruction(direction: str, facing: str) -> str:
    views = {
        "side": f"Exact side view, with the whole body and head facing {facing}.",
        "front": "Exact front view: the whole body, head, chest and pelvis face the viewer directly. "
                 "Any feet point toward the viewer; do not turn only the head.",
        "back": "Exact back view: the whole body, head and pelvis face directly away from the viewer. "
                "Show the back of the head and body; keep the face hidden.",
        "front_diagonal": f"Exact 45-degree three-quarter front view: the whole body and head face "
                          f"diagonally toward the viewer and to the {facing} together.",
        "back_diagonal": f"Exact 45-degree three-quarter back view: the whole body and head face "
                         f"diagonally away from the viewer and to the {facing} together; keep the face hidden.",
    }
    selected = f"viewDirection={direction}"
    if direction in ("side", "front_diagonal", "back_diagonal"):
        selected += f"; viewFacing={facing}"
    return (f"SELECTED VIEW (authoritative): {selected}. "
            + views[direction] + " Apply this selected view instead of the attachments' viewing angles. "
            "Preserve identity, anatomy, pose/action and equipment on the character's own sides.")
