import {describe,it,expect,vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import type {Studio} from '../src/useStudio';
import type {ExportRecord,Job,Runtime,Snapshot} from '../src/types';
import transitions from '../../../tests/fixtures/review-transitions.json';
vi.mock('../src/SourceSteps',()=>({AssetsStep:()=>null,ReferenceStep:()=>null,GenerationStep:()=>null,ExtractStep:()=>null}));
vi.mock('../src/AnimationWorkspace',()=>({EditStep:()=> <div data-editor="preserved"/>}));
vi.mock('../src/FinishSteps',()=>({ExportStep:()=>null}));
import {ProductionWorkflow,productionProgress,productionTabKeys} from '../src/ProductionWorkflow';
const project=()=>{const p=structuredClone(transitions.snapshot) as unknown as Snapshot;p.assets=[{assetId:'identity'}] as any;p.references.forEach(r=>r.identityAssetId='identity');return p;};
const manifest=(revision:number,clipId='c')=>({exportId:'e',projectRevision:revision,clips:[{id:clipId}]} as Runtime);
function bake(p:Snapshot,changes:Partial<Job>={}):Job{return {jobId:'j',operation:'bake',inputRevision:p.revision,status:'succeeded',inspectionClipIds:['c'],artifacts:[{artifactId:'a',name:'atlas.png',url:'/atlas.png'}],result:{qa:{errors:[],warnings:[],frames:[]},manifest:manifest(p.revision)},...changes};}
function output(p:Snapshot):ExportRecord{return {exportId:'e',status:'succeeded',manifest:manifest(p.revision),files:[{artifactId:'a',name:'atlas.png',url:'/atlas.png'},{artifactId:'r',name:'runtime.json',url:'/runtime.json'}]};}
describe('six production stages use data, not manual approval or tab visits',()=>{
 it('keeps pending metadata intact and requires a current inspection and actual output',()=>{
  const p=project();p.references[0].approval='draft';p.clips[0].review='pending';p.frames[0].review='pending';p.alignments.f.approval='pending';const before=structuredClone(p);
  const waiting=productionProgress(p,p.clips[0],[],[],false);expect(waiting.ready.slice(0,4)).toEqual([true,true,true,true]);expect(waiting.statuses.slice(4)).toEqual(['대기','대기']);
  const complete=productionProgress(p,p.clips[0],[bake(p)],[output(p)],false);expect(complete.ready).toEqual([true,true,true,true,true,true]);expect(complete.statuses[5]).toBe('출력 완료');expect(p).toEqual(before);
 });
 it.each(['succeeded','needs_review'])('marks a standalone %s inspection ready without baking or exporting',status=>{
  const p=project(),before=structuredClone(p),inspection=bake(p,{operation:'inspect',status,artifacts:[],result:{qa:{errors:[],warnings:[],frames:[{clipId:'c',errors:[],warnings:[]}]}}});
  const result=productionProgress(p,p.clips[0],[inspection],[],false);
  expect(result.statuses[4]).toBe('준비됨');expect(result.ready[4]).toBe(true);expect(result.statuses[5]).toBe('대기');expect(p).toEqual(before);
  expect(productionProgress(p,p.clips[1],[inspection],[],false).ready[4]).toBe(false);
  expect(productionProgress(p,p.clips[0],[inspection],[],true).ready[4]).toBe(false);
  expect(productionProgress(p,p.clips[0],[inspection],[],false,true).ready[4]).toBe(false);
  p.revision++;expect(productionProgress(p,p.clips[0],[inspection],[],false).ready[4]).toBe(false);
 });
 it('keeps missing inspection guidance separate from real inspection errors',()=>{
  const p=project();expect(productionProgress(p,p.clips[0],[],[],false).hints[4]).toBe('저장한 뒤 선택 동작 자동 검사를 실행하세요.');
  const inspection=bake(p,{operation:'inspect',artifacts:[],result:{qa:{errors:[{code:'FRAME_OVERFLOW',message:'overflow',clipId:'c'}]}}});
  const result=productionProgress(p,p.clips[0],[inspection],[],false);expect(result.statuses[4]).toBe('수정 필요');expect(result.ready[4]).toBe(false);expect(result.hints[4]).toBe('자동 검사 오류 1건');
 });
 it('keeps past files from marking changed or another clip ready',()=>{
  const p=project(),old=bake(p),exported=output(p);p.revision++;
  expect(productionProgress(p,p.clips[0],[old],[exported],false).ready.slice(4)).toEqual([false,false]);
  expect(productionProgress(p,p.clips[1],[bake(p)],[output(p)],false).ready.slice(4)).toEqual([false,false]);
  expect(productionProgress(p,p.clips[0],[bake(p)],[output(p)],true).ready.slice(3)).toEqual([false,false,false]);
 });
 it('blocks missing alignment, inspection error and failed artifact jobs',()=>{
  const p=project();delete p.alignments.f;expect(productionProgress(p,p.clips[0],[],[],false).statuses[3]).toBe('수정 필요');
  const error=bake(p,{result:{manifest:manifest(p.revision),qa:{errors:[{code:'FRAME_OVERFLOW',message:'overflow',clipId:'c'}]}}});expect(productionProgress(p,p.clips[0],[error],[],false).ready[4]).toBe(false);
  expect(productionProgress(p,p.clips[0],[bake(p,{status:'failed'})],[],false).ready[4]).toBe(false);
 });
 it('keeps an existing preview ready after a separate inspection of the same saved revision',()=>{
  const p=project(),preview=bake(p,{createdAt:'2026-10-12T01:00:00Z'}),inspection=bake(p,{jobId:'inspect',operation:'inspect',createdAt:'2026-10-12T02:00:00Z',artifacts:[],result:{qa:{errors:[],frames:[{clipId:'c',errors:[]}]}}});
  expect(productionProgress(p,p.clips[0],[inspection,preview],[],false).ready[4]).toBe(true);
 });
 it('does not accept an atlas without runtime as a completed export',()=>{
  const p=project(),e=output(p);e.files=e.files!.slice(0,1);expect(productionProgress(p,p.clips[0],[],[e],false).ready[5]).toBe(false);
 });
 it('renders six linked tabs, keeps the editor mounted, and never edits or generates on navigation',()=>{
  const p=project(),s={snapshot:p,commands:[],jobs:[],exports:[],resolveId:(id:string)=>id,edit:vi.fn(),job:vi.fn()} as unknown as Studio;
  const html=renderToStaticMarkup(<ProductionWorkflow s={s} step={4} onStep={vi.fn()} clipId="c" onClip={vi.fn()} onTool={vi.fn()} onSelectionChange={vi.fn()} sourceMode="generate" onSourceMode={vi.fn()}/>);
  expect(html.match(/role="tab"/g)).toHaveLength(6);expect(html.match(/role="tabpanel"/g)).toHaveLength(6);expect(html).toContain('data-editor="preserved"');expect(html).toContain('캐릭터 기준 수정');expect(html).toContain('프레임·시간 수정');expect(s.edit).not.toHaveBeenCalled();expect(s.job).not.toHaveBeenCalled();
 });
 it.each([['ArrowRight',5,0],['ArrowLeft',0,5],['Home',3,0],['End',2,5]])('supports keyboard %s without editing data',(key,current,expected)=>{
  const tabs=Array.from({length:6},()=>({focus:vi.fn(),click:vi.fn()}));const preventDefault=vi.fn();productionTabKeys({key,target:tabs[+current],currentTarget:{querySelectorAll:()=>tabs},preventDefault} as any);expect(tabs[+expected].focus).toHaveBeenCalledOnce();expect(tabs[+expected].click).toHaveBeenCalledOnce();expect(preventDefault).toHaveBeenCalledOnce();
 });
});
