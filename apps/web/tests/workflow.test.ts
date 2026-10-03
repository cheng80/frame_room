import {describe,it,expect} from 'vitest';
import type {Snapshot,Job} from '../src/types';
import {approvalLabel,inspectionState,nextWork} from '../src/workflow';

function project():Snapshot{return {projectId:'p',revision:7,assets:[{assetId:'a'}],activeReferenceRevisionId:'r',references:[{referenceRevisionId:'r',approval:'approved'}],frames:[{frameVersionId:'f',review:'approved',nativeScaleGroupId:'g'},{frameVersionId:'unused',review:'pending'}],alignments:{f:{frameVersionId:'f',approval:'approved',groupRevisionId:'gr'}},alignmentGroups:[{alignmentGroupId:'g',groupRevisionId:'gr',frameVersionIds:['f']}],clips:[{clipId:'c',referenceRevisionId:'r',name:'걷기',review:'approved',defaultFps:10,occurrences:[{occurrenceId:'o',frameVersionId:'f',durationMs:100}]}]} as Snapshot;}
function inspection(changes:Partial<Job>={}):Job{return {jobId:'j',operation:'inspect',status:'needs_review',inputRevision:7,createdAt:'2026-10-03T01:00:00Z',inspectionClipIds:['c'],result:{qa:{frames:[{clipId:'c',occurrenceId:'o',frameVersionId:'f',errors:[],warnings:[]}],errors:[],warnings:[]}},...changes};}

describe('inspection is separate from manual approval',()=>{
 it('never calls an uninspected manually approved clip a quality pass',()=>{expect(approvalLabel('approved')).toBe('수동 승인됨');expect(inspectionState(project(),[],false,'c').state).toBe('missing');});
 it('marks reports stale on unsaved edits and on a saved revision change',()=>{expect(inspectionState(project(),[inspection()],true,'c').state).toBe('stale');const s=project();s.revision++;expect(inspectionState(s,[inspection()],false,'c').state).toBe('stale');});
 it('uses the latest applicable run regardless of API ordering',()=>{const older=inspection({jobId:'old',createdAt:'2026-10-02'}),latest=inspection({jobId:'new',createdAt:'2026-10-04'});expect(inspectionState(project(),[latest,older],false,'c').job?.jobId).toBe('new');expect(inspectionState(project(),[older,latest],false,'c').job?.jobId).toBe('new');});
 it('does not use a different clip report as a selected clip pass',()=>{expect(inspectionState(project(),[inspection()],false,'other').state).toBe('missing');});
 it('shows running and failed scoped jobs even before they have reports',()=>{expect(inspectionState(project(),[inspection({status:'running',result:undefined})],false,'c').state).toBe('running');expect(inspectionState(project(),[inspection({status:'failed',result:undefined})],false,'c').state).toBe('failed');});
 it('keeps warnings attached to exact repeated occurrences without double-counting summaries',()=>{
  const w={code:'LOW_ALPHA_SUPPORT',message:'낮은 알파',pixelCount:12},e={code:'FRAME_UNAPPROVED',message:'승인 필요'};
  const j=inspection({result:{qa:{frames:[{clipId:'c',occurrenceId:'o',frameVersionId:'f',warnings:[w],errors:[e]},{clipId:'c',occurrenceId:'o2',frameVersionId:'f',warnings:[w],errors:[]}],warnings:[w,w],errors:[{...e,clipId:'c',occurrenceId:'o'}]}}});
  const report=inspectionState(project(),[j],false,'c');
  // o2 is an old report's slot; it must remain identifiable instead of pointing to o.
  expect(report.issues.filter(i=>i.severity==='warning')).toHaveLength(2);
  expect(report.issues.filter(i=>i.severity==='approval')).toHaveLength(1);
  expect(report.issues[0].target).toMatchObject({clipId:'c',frameVersionId:'f',occurrenceId:'o'});
  expect(report.issues.find(i=>i.severity==='warning')?.location).toContain('개별 좌표 미제공');
 });
 it('routes existing overflow evidence to alignment with the supplied edge',()=>{
  const j=inspection({result:{qa:{frames:[{clipId:'c',occurrenceId:'o',frameVersionId:'f',errors:[{code:'FRAME_OVERFLOW',message:'셀 경계',overflowPx:{right:3,top:0}}]}]}}});
  const issue=inspectionState(project(),[j],false,'c').issues[0];expect(issue.target.action).toBe('align');expect(issue.location).toBe('셀 경계: 오른쪽 3px');
 });
 it('distinguishes changed approvals only when an invalidation record exists',()=>{expect(approvalLabel('pending')).toBe('승인 대기');expect(approvalLabel('pending','타이밍 변경')).toBe('변경 후 재확인 필요');});
});
describe('next work follows the selected clip',()=>{
 it('ignores unused pending candidates and offers output once approvals are satisfied',()=>{const s=project();const tasks=nextWork(s,s.clips[0],false,[inspection()]);expect(tasks.map(t=>t.id)).toEqual(['export']);});
 it('offers specific frame and anchor destinations without duplicate tasks for repeated slots',()=>{const s=project();s.frames[0].review='pending';s.alignments.f.approval='pending';s.clips[0].occurrences.push({...s.clips[0].occurrences[0],occurrenceId:'o2'});const tasks=nextWork(s,s.clips[0],false,[]);expect(tasks.find(t=>t.id==='frames')).toMatchObject({label:'사용 후보 1개 수동 승인',frameVersionId:'f'});expect(tasks.find(t=>t.id==='anchors')).toMatchObject({frameVersionId:'f',action:'align'});expect(tasks.some(t=>t.action==='export')).toBe(false);});
 it('puts save first and withholds output for dirty data',()=>{const s=project(),tasks=nextWork(s,s.clips[0],true,[inspection()]);expect(tasks[0].action).toBe('save');expect(tasks.some(t=>t.action==='export')).toBe(false);});
 it('offers conflict resolution instead of save when conflict exists',()=>{const s=project();expect(nextWork(s,s.clips[0],true,[],true)[0].action).toBe('conflict');});
 it('requires the clip reference even if another active reference is approved',()=>{const s=project();s.clips[0].referenceRevisionId='missing';expect(nextWork(s,s.clips[0],false,[]).find(t=>t.id==='reference')?.action).toBe('clip-settings');});
 it('offers a useful path for empty projects and empty clips',()=>{const s=project();s.assets=[];s.frames=[];s.references=[];s.clips=[];expect(nextWork(s,undefined,false,[]).map(t=>t.id)).toEqual(['assets','reference','create']);const another=project();another.clips[0].occurrences=[];expect(nextWork(another,another.clips[0],false,[]).map(t=>t.id)).toEqual(['candidates']);});
});
