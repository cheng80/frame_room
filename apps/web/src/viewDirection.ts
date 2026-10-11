import rules from '../../../packages/contracts/view-direction-rules.json';

/** shortcut: 알려진 방향 표현만 정리한다. 새 표현은 공통 규칙과 회귀 사례에 추가한다. */
export function stripViewInstructions(text: string): string {
  const negative = new RegExp(rules.negativePattern, 'i');
  const patterns = rules.patterns.map(pattern => new RegExp(pattern, 'gi'));
  const clauses = text.split(/([.!?。\n,;，；])/);
  const kept: string[] = [];
  for (let index = 0; index < clauses.length; index += 2) {
    const clause = (negative.test(clauses[index]) ? clauses[index] :
      patterns.reduce((value, pattern) => value.replace(pattern, ''), clauses[index])).replace(/\s+/g, ' ').trim();
    if (clause) kept.push(clause + (clauses[index + 1] ?? ''));
  }
  return kept.join(' ').trim();
}
