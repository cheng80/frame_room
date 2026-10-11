import {describe, expect, it} from 'vitest';
import {stripViewInstructions} from '../src/viewDirection';

describe('shared view directive cleanup', () => {
  it('keeps hands, action and effects while removing a legacy angle', () => {
    const cleaned = stripViewInstructions('오른손에 황금 스태프를 잡고 오른쪽을 보는 정확한 측면의 이동 중간 자세. 왼손은 빈손. 3D 렌더링과 광채는 제외한다.');
    expect(cleaned).not.toContain('측면');
    expect(cleaned).not.toContain('오른쪽을 보는');
    expect(cleaned).toContain('오른손에 황금 스태프');
    expect(cleaned).toContain('왼손은 빈손');
    expect(cleaned).toContain('이동 중간 자세');
    expect(cleaned).toContain('3D 렌더링과 광채는 제외한다');
  });
  it('preserves prohibitions and anatomical sides', () => {
    const text = 'Never turn into a side view. No facing left. sword in the right hand. 참조 그림의 측면 각도를 따르지 않는다.';
    expect(stripViewInstructions(text)).toBe(text);
  });
  it('cleans repeated switches without losing the source description', () => {
    const raw = 'SD 여성 힐러, 정확한 오른쪽 측면, 오른손에 스태프, 2D 도트 화풍';
    const cleaned = stripViewInstructions(raw);
    expect(cleaned).not.toContain('측면');
    expect(cleaned).not.toContain(', ,');
    expect(stripViewInstructions(cleaned)).toBe(cleaned);
    expect(raw).toContain('측면');
  });
  it.each([
    '참조의 색과 특징은 유지하되 요청한 측면 방향과 효과 제외를 우선한다.',
    '효과 없는 정면', 'side-view walking without glow', '정면 대각선 45도',
  ])('cleans the view independently of effect prohibitions: %s', raw => {
    const cleaned = stripViewInstructions(raw);
    expect(cleaned).not.toMatch(/측면|정면|대각선|side-view/);
    if (raw.includes('제외')) expect(cleaned).toContain('효과 제외');
    if (raw.includes('without')) expect(cleaned).toContain('without glow');
  });
});
