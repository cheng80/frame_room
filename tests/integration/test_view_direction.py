"""Narrow view cleanup shared with the editor; no image generation."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from adapters.spritegen.view_direction import strip_view_instructions


CASES = [
    ("오른쪽을 보는 정확한 측면의 이동 중간 자세", "이동 중간 자세"),
    ("정확한 오른쪽 측면, 왼손 방패와 오른손 검", "왼손 방패와 오른손 검"),
    ("오른쪽을 바라보며 걷는 자세", "걷는 자세"),
    ("정확한 정면. 앞 대각선 45도; 뒤 대각선 45도. 대기 자세", "대기 자세"),
    ("Side-view, facing RIGHT; walk with a sword in the right hand.", "walk with a sword in the right hand."),
    ("three-quarter front view; three-quarter back view. run", "run"),
    ("facing left\nside-view。 마법 효과，오른손 검；이동 중간 자세", "마법 효과， 오른손 검； 이동 중간 자세"),
    ("no turning to side; do not use side-view. never facing left", "no turning to side; do not use side-view. never facing left"),
    ("측면 각도를 따르지 않는다. 왼쪽을 바라보지 말고 정면 유지", "측면 각도를 따르지 않는다. 왼쪽을 바라보지 말고 정면 유지"),
    ("왼손 방패, 오른손 검. sword:right; shield:left. glow and particles", "왼손 방패, 오른손 검. sword:right; shield:left. glow and particles"),
    ("side-view, no turning to side; facing right. 오른손 검", "no turning to side; 오른손 검"),
    ("side-view, facing right!", ""),
    ("참조의 색과 특징은 유지하되 요청한 측면 방향과 효과 제외를 우선한다.",
     "참조의 색과 특징은 유지하되 효과 제외를 우선한다."),
    ("효과 없는 정면", "효과 없는"),
    ("side-view walking without glow", "walking without glow"),
    ("정면 대각선 45도 이동 자세", "이동 자세"),
    ("No facing left. Never turn into a side view. 참조 그림의 측면 각도를 따르지 않는다",
     "No facing left. Never turn into a side view. 참조 그림의 측면 각도를 따르지 않는다"),
]


@pytest.mark.parametrize("source,expected", CASES)
def test_strip_view_instructions(source, expected):
    assert strip_view_instructions(source) == expected


def test_shared_patterns_and_cleanup_match_javascript():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to check the TypeScript-compatible regex contract")
    rules = Path(__file__).resolve().parents[2] / "packages/contracts/view-direction-rules.json"
    script = r"""
const fs = require('node:fs');
const {rules, cases} = JSON.parse(fs.readFileSync(0, 'utf8'));
const patterns = rules.patterns.map(p => new RegExp(p, 'gi'));
const negative = new RegExp(rules.negativePattern, 'i');
const results = cases.map(text => {
  const clauses = text.split(/([.!?。\n,;，；])/), kept = [];
  for (let i = 0; i < clauses.length; i += 2) {
    let clause = clauses[i];
    if (!negative.test(clause)) for (const pattern of patterns) clause = clause.replace(pattern, '');
    clause = clause.trim().replace(/\s+/g, ' ');
    if (clause) kept.push(clause + (clauses[i + 1] || ''));
  }
  return kept.join(' ').trim();
});
process.stdout.write(JSON.stringify(results));
"""
    result = subprocess.run([node, "-e", script], input=json.dumps({
        "rules": json.loads(rules.read_text()), "cases": [source for source, _ in CASES],
    }), text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == [expected for _, expected in CASES]
