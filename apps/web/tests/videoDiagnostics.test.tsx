import {describe, expect, it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {VideoDiagnostics} from '../src/VideoDiagnostics';
import {videoDiagnostics} from '../src/videoDiagnosticMessages';

describe('saved video diagnostics', () => {
  it.each([undefined, null, {}, [], {selection: null}, {selection: 'old'}, {selection: {period: null, held: [], footStrike: 1, cycleAlignment: 'old'}}])('tolerates an absent or older record: %j', value => {
    expect(videoDiagnostics(value)).toEqual([]);
    expect(renderToStaticMarkup(<VideoDiagnostics processing={value}/>)).toBe('');
  });
  it('shows actual upstream period suspects as advice without claiming an automatic cut', () => {
    const data = {selection: {period: {suspects: [{cycles: 2, why: 'repeat'}], checked: []}}};
    const rows = videoDiagnostics(data);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({id: 'period', level: 'warning'});
    expect(rows[0].message).toContain('들어 있을 수 있습니다');
    expect(rows[0].message).toContain('수동 구간');
    expect(videoDiagnostics({selection: {period: {suspects: []}}})).toEqual([]);
  });
  it('uses actual retained interpolation and nearest replacement counts after output rotation', () => {
    const processing = {selection: {cycleAlignment: {
      made_by_rife: 99, made_at: [1, 4], nearest_at: [2, 5],
      outputMadeAt: [0, 3], outputNearestAt: [1, 4], turnedBy: 1,
      indexSpace: 'before-output-rotation',
      smear: [{at: 2, method: 'nearest', faults: ['smear']}, {at: 5, method: 'nearest', faults: ['outline']}, {at: 4, method: 'rife', faults: []}],
    }}};
    const original = structuredClone(processing), rows = videoDiagnostics(processing);
    expect(rows.find(row => row.id === 'resample')?.message).toBe('새 보간 2장 · 가까운 원본 사용 2장');
    expect(rows.find(row => row.id === 'protected')?.message).toContain('2장을 가까운 원본으로 대체');
    expect(rows.some(row => row.id === 'smear')).toBe(false);
    expect(processing).toEqual(original);
  });
  it('warns if interpolation kept a measured defect and accepts the nested compatibility shape', () => {
    const rows = videoDiagnostics({selection: {alignment: {resample: {made: 1, nearest: 0, smear: [{method: 'rife', faults: ['outline']}]}}}});
    expect(rows.find(row => row.id === 'resample')?.message).toBe('새 보간 1장 · 가까운 원본 사용 0장');
    expect(rows.find(row => row.id === 'smear')).toMatchObject({level: 'warning'});
  });
  it('does not call an intentional nearest sample a rejected interpolation', () => {
    const rows = videoDiagnostics({selection: {cycleAlignment: {made_by_rife: 0, nearest_at: [1, 3]}}});
    expect(rows).toHaveLength(1);
    expect(rows[0].message).toBe('새 보간 0장 · 가까운 원본 사용 2장');
  });
  it('distinguishes original strike candidate indices from output phase indices', () => {
    const rows = videoDiagnostics({selection: {footStrike: {start: 3, start_foot: null, foot_why: 'low-margin', strikes: [3, 15], indexSpace: 'selected-source-cycle'}}});
    expect(rows[0].message).toContain('3, 15번 (선택한 원본 구간에서 0부터)');
    expect(rows[0].message).toContain('결과의 수동 시작 위치');
    const named = videoDiagnostics({selection: {footStrike: {start_foot: 'left', start_foot_source: 'given'}}});
    expect(named[0].message).toBe('시작 발 · 캐릭터의 왼발 · 수동 지정');
  });
  it('does not claim a detected source foot was applied when the original phase was kept', () => {
    const sourceFoot = {start: 3, start_foot: 'right', indexSpace: 'selected-source-cycle'};
    const rows = videoDiagnostics({selection: {footStrike: sourceFoot}});
    expect(rows[0].message).toContain('원본의 발 디딤 판정');
    expect(rows[0].message).toContain('결과 시작은 유지');
    const manual = videoDiagnostics({selection: {footStrike: sourceFoot, outputPhase: {manual: true, turnedBy: 2, footStrike: {start_foot: 'left'}}}});
    expect(manual).toEqual([{id: 'phase', level: 'info', message: '수동 시작 위치 적용 · 결과 2번 (0부터)'}]);
  });
  it('shows held drawings, size correction and retake advice without a generation action', () => {
    const processing = {selection: {
      held: {hold: 2, drawings_per_second: 12}, sizeHold: {applied: true, drift: .025},
      retake: {suggested: true, reasons: [{reason: 'held-drawings'}], automaticGeneration: false},
    }};
    const html = renderToStaticMarkup(<VideoDiagnostics processing={processing}/>);
    expect(html).toContain('초당 약 12.0회');
    expect(html).toContain('몸 크기를 보정');
    expect(html).toContain('새 영상은 자동 생성하지 않습니다');
    expect(html).not.toContain('<button');
  });
  it('does not render unknown values or malformed arrays as trusted evidence', () => {
    const rows = videoDiagnostics({selection: {held: {hold: NaN}, cycleAlignment: {made_at: [null], nearest_at: 'oops', smear: [null, 'error']}, footStrike: {start_foot: null, strikes: [{at: 3}]}, retake: {suggested: false}}});
    expect(rows).toHaveLength(1);
    expect(rows[0].message).not.toContain('후보:');
  });
});
