import {describe,it,expect} from 'vitest';
import {applyDraft,remapCommand,exportGates} from '../src/draft';
import {occurrenceAt,validateRuntime} from '../src/render';
import type {Snapshot} from '../src/types';
const base={projectId:'p',revision:1,activeReferenceRevisionId:'r',clips:[{clipId:'c',review:'approved',defaultFps:10,occurrences:[]}],alignments:{f:{approval:'approved'}},alignmentGroups:[{alignmentGroupId:'g',frameVersionIds:['f'],sharedScale:1}],frames:[{frameVersionId:'f',review:'pending'}]} as unknown as Snapshot;
describe('independent occurrences and saving',()=>{
 it('preserves [A,A] as separate slots and durations',()=>{const s=applyDraft(base,[{operation:{type:'addOccurrence',clipId:'c',frameVersionId:'f'},localId:'o1'},{operation:{type:'duplicateOccurrence',clipId:'c',occurrenceId:'o1'},localId:'o2'},{operation:{type:'setTiming',clipId:'c',occurrenceId:'o2',durationMs:240,timingMode:'explicit'}}]);expect(s.clips[0].occurrences.map(o=>o.durationMs)).toEqual([100,240]);expect(s.clips[0].occurrences.map(o=>o.occurrenceId)).toEqual(['o1','o2']);expect(base.clips[0].occurrences).toEqual([]);});
 it('remaps draft identifiers before dependent server operations',()=>{expect(remapCommand({operation:{type:'reorderOccurrences',clipId:'draft-c',occurrenceIds:['draft-o']}},{'draft-c':'c','draft-o':'o'}).operation).toEqual({type:'reorderOccurrences',clipId:'c',occurrenceIds:['o']});});
 it('keeps empty timeline empty after removing final occurrence',()=>{const s=applyDraft(base,[{operation:{type:'addOccurrence',clipId:'c',frameVersionId:'f'},localId:'o'},{operation:{type:'removeOccurrence',clipId:'c',occurrenceId:'o'}}]);expect(s.clips[0].occurrences).toHaveLength(0);});
 it('invalidates clip and anchors on group edits',()=>{const fixture=structuredClone(base);fixture.clips[0].occurrences=[{frameVersionId:'f'}] as any;fixture.clips.push({...fixture.clips[0],clipId:'unrelated',occurrences:[{frameVersionId:'other'} as any]});const s=applyDraft(fixture,[{operation:{type:'setAlignmentGroup',alignmentGroupId:'g',changes:{sharedScale:1}}}]);expect(s.clips[0].review).toBe('pending');expect(s.clips[1].review).toBe('approved');expect(s.alignments.f.approval).toBe('pending');});
 it('FPS updates preserve explicit durations',()=>{const s=applyDraft(base,[{operation:{type:'addOccurrence',clipId:'c',frameVersionId:'f'},localId:'o1'},{operation:{type:'addOccurrence',clipId:'c',frameVersionId:'f'},localId:'o2'},{operation:{type:'setTiming',clipId:'c',occurrenceId:'o2',durationMs:123,timingMode:'explicit'}},{operation:{type:'updateClip',clipId:'c',changes:{defaultFps:20}}}]);expect(s.clips[0].occurrences.map(o=>o.durationMs)).toEqual([50,123]);});
});
describe('runtime boundaries',()=>{it('uses variable duration and hold-last without FPS rounding',()=>{expect([0,79,80,199,200,399,400].map(t=>occurrenceAt([80,120,200],t,true))).toEqual([0,0,1,1,2,2,0]);expect(occurrenceAt([80,120,200],900,false)).toBe(2);expect(occurrenceAt([],0,true)).toBe(-1);});it('rejects unsupported manifests',()=>{expect(()=>validateRuntime({schemaVersion:5})).toThrow();});});
it('uses the actual cell center for new occurrence pivots',()=>{const fixture=structuredClone(base);fixture.alignmentGroups[0].cell={width:128,height:96,edge:2};const s=applyDraft(fixture,[{operation:{type:'addOccurrence',clipId:'c',frameVersionId:'f'},localId:'o'}]);expect(s.clips[0].occurrences[0].transform.pivot).toEqual({x:64,y:48});});
it('frame review invalidates only clips using that frame',()=>{const fixture=structuredClone(base);fixture.clips[0].occurrences=[{frameVersionId:'f'}] as any;fixture.clips.push({...fixture.clips[0],clipId:'unrelated',occurrences:[{frameVersionId:'other'} as any]});const s=applyDraft(fixture,[{operation:{type:'setFrameReview',frameVersionId:'f',review:'approved'}}]);expect(s.clips.map(c=>c.review)).toEqual(['pending','approved']);});
it('preserves a rejection reason through draft application and later visibility changes',()=>{const s=applyDraft(base,[{operation:{type:'setFrameReview',frameVersionId:'f',review:'rejected',reason:'오른손 장갑과 무기 경계가 기준과 다름'}},{operation:{type:'setFrameReview',frameVersionId:'f',review:'rejected',hidden:true}}]);expect(s.frames[0].review).toBe('rejected');expect(s.frames[0].reviewReason).toBe('오른손 장갑과 무기 경계가 기준과 다름');expect(base.frames[0].reviewReason).toBeUndefined();});
it('blocks export with the stored reason for a rejected frame',()=>{const fixture=structuredClone(base);fixture.references=[{referenceRevisionId:'r',approval:'approved'}] as any;fixture.clips[0].referenceRevisionId='r';fixture.clips[0].name='대기';fixture.clips[0].occurrences=[{frameVersionId:'f',durationMs:100}] as any;fixture.frames[0].review='rejected';fixture.frames[0].reviewReason='투구 형태 불일치';expect(exportGates(fixture,['c'],false)).toContain('대기: 거절된 후보입니다. 투구 형태 불일치');});

// Shared cases prevent client previews and saved approval state from diverging.
import transitions from '../../../tests/fixtures/review-transitions.json';
describe('review invalidation contract shared with the API',()=>{
 for(const testCase of transitions.cases)it(testCase.name,()=>{
  const snapshot=structuredClone(transitions.snapshot) as unknown as Snapshot;
  if('initialPending' in testCase&&testCase.initialPending){snapshot.clips.forEach(c=>c.review='pending');snapshot.alignments.f.approval='pending';}
  const before=structuredClone(snapshot);
  const result=applyDraft(snapshot,testCase.operations.map((operation,i)=>({operation,localId:`local-${i}`})));
  const state={clips:result.clips.map(c=>Object.fromEntries(Object.entries(c).filter(([k])=>['clipId','review','reviewInvalidatedReason'].includes(k)))),alignments:Object.fromEntries(Object.entries(result.alignments).map(([fid,a])=>[fid,Object.fromEntries(Object.entries(a).filter(([k])=>['approval','reviewInvalidatedReason'].includes(k)))]))};
  expect(state).toEqual(testCase.expected);expect(snapshot).toEqual(before);
 });
 it('matches server partial transform, outline merge, and FPS duration',()=>{
  const snapshot=structuredClone(transitions.snapshot) as unknown as Snapshot;
  const result=applyDraft(snapshot,[{operation:{type:'setTransform',clipId:'c',occurrenceId:'o',transform:{dx:3}}},{operation:{type:'setTiming',clipId:'c',occurrenceId:'o',durationMs:9,timingMode:'fps'}},{operation:{type:'setOutline',outline:{enabled:true}}}]);
  expect(result.clips[0].occurrences[0].transform).toMatchObject({dx:3,scaleX:1});expect(result.clips[0].occurrences[0].durationMs).toBe(100);expect(result.outline.mode).toBe('preview-only');
 });
});
describe('export approval and selection gates',()=>{
 const ready=()=>structuredClone(transitions.snapshot) as unknown as Snapshot;
 it('accepts approved selection and blocks missing or duplicate clip IDs',()=>{
  expect(exportGates(ready(),['c'],false)).toEqual([]);
  expect(exportGates(ready(),['missing'],false)).toContain('출력할 동작을 찾을 수 없습니다. 다시 선택해 주세요.');
  expect(exportGates(ready(),['c','missing'],false)).toContain('출력할 동작을 찾을 수 없습니다. 다시 선택해 주세요.');
  expect(exportGates(ready(),['c','c'],false)).toContain('같은 동작이 중복 선택되었습니다.');
 });
 it('blocks stale anchors even when approved and requires the proper group',()=>{
  const s=ready();s.alignments.f.groupRevisionId='stale';
  expect(exportGates(s,['c'],false).join(' ')).toContain('현재 정렬 기준의 앵커 승인');
  s.alignments.f.groupRevisionId='gr';s.frames[0].nativeScaleGroupId='missing';
  expect(exportGates(s,['c'],false).join(' ')).toContain('현재 정렬 기준의 앵커 승인');
 });
 it('blocks stale FPS duration and permits explicit duration',()=>{
  const s=ready();s.clips[0].occurrences[0].durationMs=90;
  expect(exportGates(s,['c'],false).join(' ')).toContain('FPS와 표시 시간이 다릅니다.');
  s.clips[0].occurrences[0].timingMode='explicit';expect(exportGates(s,['c'],false)).toEqual([]);
 });
 it('reapproval alone cannot bypass missing frame and anchor approvals',()=>{
  const s=ready();s.frames[0].review='pending';s.alignments.f.approval='pending';
  const issues=exportGates(s,['c'],false).join(' ');expect(issues).toContain('후보 수동 승인');expect(issues).toContain('앵커 승인');
 });
});
