import {describe, expect, it} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {CandidateLibrary} from '../src/CandidateLibrary';
import {buildCandidateHistory, candidateApprovalLabel} from '../src/candidateHistory';
import type {Asset, Clip, Frame, Job, Snapshot} from '../src/types';

const asset = (id: string, provenance: unknown = {kind: 'imported'}) => ({assetId: id, originalFilename: 'same.png', provenance}) as Asset;
const frame = (id: string, group = 'shared', raw = 'raw') => ({frameVersionId: id, imageAssetId: `image-${id}`, rawAssetId: raw, nativeScaleGroupId: group, hidden: false, review: 'pending'}) as Frame;
const snapshot = (frames: Frame[], extra: Partial<Snapshot> = {}) => ({frames, assets: [asset('raw'), ...frames.map(f => asset(f.imageAssetId, {kind: 'raw-crop', parentAssetId: f.rawAssetId}))], clips: [], generations: [], journal: [], ...extra}) as Snapshot;
const extraction = (id: string, ids: string[], extra = {}) => ({jobId: id, operation: 'extract', status: 'needs_review', inputRevision: 1, result: {frames: ids.map(frameVersionId => ({frameVersionId})), ...extra}}) as unknown as Job;

// Synthetic regression data for the saved example's two extraction groups.
// No local project snapshot, generated image or provider call is required.
function savedExample(): Snapshot {
  const frames = Array.from({length: 12}, (_, i) => ({
    ...frame(`candidate-${i + 1}`, i < 6 ? 'first-group' : 'second-group'),
    sourceRect: {x: (i % 6) * 32, y: 0, width: 32, height: 32},
    review: i < 6 ? 'pending' : 'approved',
  })) as Frame[];
  return snapshot(frames, {
    generations: [{generationVersionId: 'synthetic-generation', rawAssetIds: ['raw'], jobId: 'synthetic-generation-job', providerId: 'codex'}],
    clips: [{clipId: 'walk', name: '걷기', occurrences: frames.slice(6).map((f, i) => ({occurrenceId: `slot-${i + 1}`, frameVersionId: f.frameVersionId}))}] as Clip[],
    journal: [8, 9].map(revision => ({revision, reason: 'extract 결과 등록', createdAt: `2026-10-03T00:00:0${revision}Z`})),
  });
}

describe('candidate history with explicit lineage', () => {
  it('separates executions even when source and alignment group are identical', () => {
    const p = snapshot([frame('a'), frame('b')]);
    const {groups} = buildCandidateHistory(p, [extraction('first', ['a']), extraction('second', ['b'])]);
    expect(groups.map(g => [g.kind, g.jobs[0].jobId, g.entries.map(e => e.frame.frameVersionId)])).toEqual([
      ['extraction', 'first', ['a']], ['extraction', 'second', ['b']],
    ]);
  });
  it('keeps partial result matches local to the exact candidate IDs', () => {
    const {groups, runs} = buildCandidateHistory(snapshot([frame('a'), frame('b')]), [extraction('first', ['a', 'missing'])]);
    expect(groups.map(g => [g.kind, g.entries.map(e => e.frame.frameVersionId)])).toEqual([['extraction', ['a']], ['unlinked', ['b']]]);
    expect(runs[0].candidateCount).toBe(1);
  });
  it('does not infer an execution from group membership, timestamps, saved revision or filename', () => {
    const p = snapshot([frame('a'), frame('b')], {journal: [{revision: 2, reason: 'extract 결과 등록', createdAt: '2026-10-03T00:00:00Z'}]});
    const {groups, runs} = buildCandidateHistory(p, [extraction('first', [], {savedRevision: 2})]);
    expect(groups).toHaveLength(1);
    expect(groups[0].kind).toBe('unlinked');
    expect(groups[0].jobs).toEqual([]);
    expect(runs).toHaveLength(1);
    expect(runs[0]).toMatchObject({revision: 2, candidateCount: 0});
  });
  it('keeps unlinked source/group combinations separate without calling them executions', () => {
    const {groups} = buildCandidateHistory(snapshot([frame('a', 'one'), frame('b', 'two'), frame('c', 'two', 'other')]), []);
    expect(groups).toHaveLength(3);
    expect(groups.every(g => g.kind === 'unlinked')).toBe(true);
  });
  it('follows cutout provenance and generation source IDs, preserving missing-record uncertainty', () => {
    const f = frame('a', 'shared', 'cutout');
    const p = snapshot([f], {assets: [asset('raw'), asset('cutout', {kind: 'cutout', parentAssetId: 'raw'}), asset(f.imageAssetId)], generations: [{generationVersionId: 'gen', rawAssetIds: ['raw'], jobId: 'generate-1', providerId: 'codex'}]});
    const entry = buildCandidateHistory(p, []).groups[0].entries[0];
    expect(entry.lineage.map(a => a.assetId)).toEqual(['image-a', 'cutout', 'raw']);
    expect(entry.generations).toEqual([expect.objectContaining({id: 'gen', jobId: 'generate-1', recorded: true})]);
    p.generations = [];
    p.assets[0].provenance = {kind: 'real-provider', generationVersionId: 'absent'};
    const missing = buildCandidateHistory(p, []).groups[0].entries[0];
    expect(missing.generations[0]).toMatchObject({id: 'absent', recorded: false});
    expect(missing.issues.join(' ')).toContain('상세 기록이 없습니다');
  });
  it('reports every repeated slot and every clip, using version IDs rather than frame identity', () => {
    const p = snapshot([frame('a'), frame('b')], {clips: [
      {clipId: 'walk', name: '걷기', occurrences: [{occurrenceId: 'one', frameVersionId: 'a'}, {occurrenceId: 'two', frameVersionId: 'a'}, {occurrenceId: 'three', frameVersionId: 'b'}]},
      {clipId: 'idle', name: '대기', occurrences: [{occurrenceId: 'four', frameVersionId: 'a'}]},
    ] as Clip[]});
    expect(buildCandidateHistory(p, []).groups[0].entries[0].uses).toEqual([
      {clipId: 'walk', clipName: '걷기', occurrenceId: 'one', slot: 1},
      {clipId: 'walk', clipName: '걷기', occurrenceId: 'two', slot: 2},
      {clipId: 'idle', clipName: '대기', occurrenceId: 'four', slot: 1},
    ]);
  });
  it('handles missing ancestors, malformed records and cycles without inventing history', () => {
    const p = snapshot([frame('a')], {assets: [asset('image-a', {parentAssetId: 'loop'}), asset('loop', {parentAssetId: 'image-a'})], generations: [null, 5, []], journal: [null, {reason: 'extract 결과 등록', revision: 3}]});
    const {groups, runs} = buildCandidateHistory(p, []);
    expect(groups[0].entries[0].issues.join(' ')).toContain('순환 참조');
    expect(groups[0].entries[0].issues.join(' ')).toContain('raw');
    expect(groups[0].generations).toEqual([]);
    expect(runs[0]).toMatchObject({revision: 3, candidateCount: 0});
    expect(runs[0].job).toBeUndefined();
  });
  it('flags conflicting explicit extraction links rather than selecting the first one', () => {
    const {groups} = buildCandidateHistory(snapshot([frame('a')]), [extraction('one', ['a']), extraction('two', ['a'])]);
    expect(groups[0].kind).toBe('unlinked');
    expect(groups[0].entries[0].issues.join(' ')).toContain('여러 추출 작업');
  });
  it('filters hidden candidates without renumbering or mutating inputs', () => {
    const p = snapshot([{...frame('a'), hidden: true}, frame('b')]);
    const before = JSON.stringify(p), jobs = [extraction('one', ['a', 'b'])];
    expect(buildCandidateHistory(p, jobs).groups[0].entries.map(e => e.number)).toEqual([2]);
    expect(buildCandidateHistory(p, jobs, true).groups[0].entries.map(e => e.number)).toEqual([1, 2]);
    expect(buildCandidateHistory(p, jobs).runs[0].candidateCount).toBe(2);
    expect(JSON.stringify(p)).toBe(before);
  });
  it('uses a synthetic saved example: two source/group bundles, one generation, six used candidates', () => {
    const p = savedExample();
    const {groups, runs} = buildCandidateHistory(p, []);
    expect(groups.map(g => [g.kind, g.entries.length])).toEqual([['unlinked', 6], ['unlinked', 6]]);
    expect(groups.map(g => g.generations[0].jobId)).toEqual(Array(2).fill('synthetic-generation-job'));
    expect(groups[0].entries.every(e => !e.uses.length)).toBe(true);
    expect(groups[1].entries.map(e => e.uses[0].slot)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(runs.filter(r => r.operation === 'extract').map(r => r.revision)).toEqual([9, 8]);
  });
  it('labels approval independently of automated inspection', () => {
    expect(['pending', 'approved', 'rejected', 'unknown'].map(candidateApprovalLabel)).toEqual(['승인 대기', '수동 승인됨', '거절됨', '승인 대기']);
  });
  it('renders recorded lineage, collapsed usage details, source actions and manual approval wording', () => {
    const p = savedExample();
    const html = renderToStaticMarkup(createElement(CandidateLibrary, {
      snapshot: p, jobs: [], includeHidden: false,
      selectedFrameId: p.frames[0].frameVersionId,
      onSelect: () => {}, onSource: () => {}, onUse: () => {},
    }));
    expect(html).toContain('aw-scroll aw-candidate-list');
    expect(html).toContain('추출 실행 연결 미기록');
    expect(html).toContain('승인 대기');
    expect(html).toContain('수동 승인됨');
    expect(html).not.toContain('검수됨');
    expect(html).toContain('슬롯 6로 이동');
    expect(html).toContain('/v1/jobs/synthetic-generation-job');
    expect(html).toContain('cl-entry-detail"><summary>');
    expect(html).toContain('aria-pressed="true"');
  });
});
