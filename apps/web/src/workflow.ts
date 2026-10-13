import type {Clip,Job,Snapshot} from './types';
import {exportGates} from './draft';
import {defaultReference} from './referenceLabel';

type RecordValue=Record<string,unknown>;
const record=(value:unknown):RecordValue=>value&&typeof value==='object'&&!Array.isArray(value)?value as RecordValue:{};
const rows=(value:unknown):RecordValue[]=>Array.isArray(value)?value.map(record):[];
const str=(value:unknown)=>typeof value==='string'?value:undefined;
export type WorkAction='save'|'conflict'|'assets'|'reference'|'extract'|'generate'|'align'|'frame-review'|'clip-review'|'clip-settings'|'candidates'|'create-clip'|'inspect'|'export'|'pixel';
export interface WorkTarget {action:WorkAction;clipId?:string;frameVersionId?:string;occurrenceId?:string;assetId?:string}
export interface WorkItem extends WorkTarget {id:string;label:string;detail:string}
export interface InspectionIssue {key:string;code:string;message:string;severity:'error'|'warning'|'approval';clipId?:string;frameVersionId?:string;occurrenceId?:string;location?:string;target:WorkTarget}
const approvalCodes=new Set(['FRAME_UNAPPROVED','ANCHOR_UNAPPROVED','CLIP_UNAPPROVED','REFERENCE_UNAPPROVED','BODY_MEASUREMENT_UNAPPROVED']);

export function approvalLabel(status:string,reason?:string){return status==='approved'?'수동 승인됨':status==='rejected'?'거절됨':reason?'변경 후 재확인 필요':'승인 대기';}

export function issueTarget(code:string,ids:{clipId?:string;frameVersionId?:string;occurrenceId?:string;assetId?:string}):WorkTarget {
 const action:WorkAction=/ALPHA/.test(code)?'pixel':/ANCHOR|ALIGNMENT|BODY|SCALE|OVERFLOW|GEOMETRY/.test(code)?'align':/REFERENCE/.test(code)?'clip-settings':['FRAME_UNAPPROVED','FRAME_REJECTED'].includes(code)?'frame-review':code==='CLIP_UNAPPROVED'?'clip-review':/EXTRACTION/.test(code)?'extract':/ASSET/.test(code)?'assets':'clip-settings';
 return {action,...ids};
}

/** Reports are tied to the saved input revision. Approval is never inferred from QA. */
export function inspectionState(s:Snapshot,jobs:Job[],dirty:boolean,clipId?:string){
 const job=jobs.filter(j=>['inspect','bake','export'].includes(j.operation)).slice().sort((a,b)=>(b.createdAt||'').localeCompare(a.createdAt||'')||b.inputRevision-a.inputRevision).find(j=>{
  if(!clipId)return true;
  const raw=record(j),input=record(raw.input),params=record(input.params),qa=record(j.result?.qa);
  const requested=Array.isArray(params.clipIds)?params.clipIds:[];
  const covered=[...rows(qa.frames).map(f=>f.clipId),...rows(record(j.result?.manifest).clips).map(c=>c.id),...requested,...(j.inspectionClipIds||[])];
  const detailRows=(j.errors||[]).flatMap(e=>rows(record(record(e).details).errors));
  return covered.includes(clipId)||detailRows.some(e=>e.clipId===clipId);
 });
 if(!job)return {state:'missing' as const,label:'자동 검사 미실행',issues:[] as InspectionIssue[],job:undefined,stale:false};
 const qa=record(job.result?.qa),stale=dirty||job.inputRevision!==s.revision;
 const issues:InspectionIssue[]=[],seen=new Set<string>();
 const add=(e:RecordValue,severity:'error'|'warning',context:RecordValue={})=>{
  const clip=str(e.clipId)||str(context.clipId),oid=str(e.occurrenceId)||str(context.occurrenceId);
  const occurrence=s.clips.find(c=>c.clipId===clip)?.occurrences.find(o=>o.occurrenceId===oid);
  const fid=str(e.frameVersionId)||str(context.frameVersionId)||occurrence?.frameVersionId;
  if(clipId&&clip&&clip!==clipId)return;
  const code=str(e.code)||'CHECK_DETAIL',message=str(e.message)||'검사 상세 정보를 확인하세요.';
  const key=JSON.stringify([code,clip,oid,fid,message]);if(seen.has(key))return;seen.add(key);
  const overflow=record(e.overflowPx||context.overflowPx),sideNames:Record<string,string>={left:'왼쪽',right:'오른쪽',top:'위',bottom:'아래'};
  const edges=Object.entries(overflow).filter(([,value])=>typeof value==='number'&&value>0).map(([side,value])=>`${sideNames[side]||side} ${value}px`);
  const location=edges.length?`셀 경계: ${edges.join(' · ')}`:typeof e.pixelCount==='number'?`낮은 알파 ${e.pixelCount.toLocaleString()}픽셀 · 개별 좌표 미제공`:undefined;
  const assetId=str(e.assetId)||s.frames.find(f=>f.frameVersionId===fid)?.rawAssetId;
  issues.push({key,code,message,severity:approvalCodes.has(code)?'approval':severity,clipId:clip,frameVersionId:fid,occurrenceId:oid,location,target:issueTarget(code,{clipId:clip,frameVersionId:fid,occurrenceId:oid,assetId})});
 };
 const frames=rows(qa.frames);
 for(const frame of frames){for(const e of rows(frame.errors))add(e,'error',frame);for(const w of rows(frame.warnings))add(w,'warning',frame);}
 for(const e of rows(qa.errors))add(e,'error');
 // The current engine repeats frame warnings in the summary without IDs.
 const frameWarnings=new Set(frames.flatMap(f=>rows(f.warnings)).map(w=>JSON.stringify(w)));
 for(const w of rows(qa.warnings))if(!frameWarnings.has(JSON.stringify(w)))add(w,'warning');
 for(const e of job.errors||[]){const details=record(record(e).details),nested=rows(details.errors);for(const f of rows(details.frames)){for(const x of rows(f.errors))add(x,'error',f);for(const x of rows(f.warnings))add(x,'warning',f);}if(nested.length)nested.forEach(x=>add(x,'error'));else if(!Object.keys(qa).length)add(record(e),'error');}
 const running=['queued','running','cancel_requested'].includes(job.status);
 const failed=['failed','interrupted','canceled','provider_outcome_unknown'].includes(job.status);
 const state=stale?'stale':running?'running':failed?'failed':!Object.keys(qa).length?'missing':'current';
 const errors=issues.filter(i=>i.severity==='error').length,warnings=issues.filter(i=>i.severity==='warning').length;
 const label=state==='stale'?'이전 버전 검사 · 재실행 필요':state==='running'?'자동 검사 처리 중':state==='failed'?'자동 검사 미완료':state==='missing'?'자동 검사 결과 없음':errors?`자동 검사 오류 ${errors}건`:warnings?`자동 검사 경고 ${warnings}건`:'자동 검사 오류·경고 없음';
 return {state,label,issues,job,stale};
}

export function nextWork(s:Snapshot,clip:Clip|undefined,dirty:boolean,jobs:Job[],conflict=false):WorkItem[]{
 const items:WorkItem[]=[];
 const add=(id:string,label:string,detail:string,target:WorkTarget)=>items.push({id,label,detail,...target});
 if(conflict)add('conflict','저장 충돌 해결','서버 버전과 보존된 초안을 비교하세요.',{action:'conflict'});
 else if(dirty)add('save','편집 초안 저장','검사와 출력은 저장된 버전을 사용합니다.',{action:'save'});
 if(!s.assets.length)add('assets','자료 가져오기','제작할 캐릭터 자료를 등록하세요.',{action:'assets'});
 const reference=clip?.referenceRevisionId?s.references.find(r=>r.referenceRevisionId===clip.referenceRevisionId):defaultReference(s);
 if(!reference)add('reference','캐릭터 기준 연결','기준 이미지와 고정 특징을 정하고 동작에 연결하세요.',{action:s.references.length&&clip?'clip-settings':'reference',clipId:clip?.clipId});
 if(!s.frames.length&&s.assets.length)add('extract','원본에서 프레임 추출','동작 만들기에서 기존 이미지의 영역을 나누세요.',{action:'extract'});
 if(!clip)add('create','편집할 동작 만들기','프레임 편집에서 동작을 만든 뒤 후보를 넣으세요.',{action:'create-clip'});
 else if(!clip.occurrences.length)add('candidates','재생 순서에 후보 추가','후보를 선택하고 순서에 추가하세요.',{action:'candidates',clipId:clip.clipId});
 if(clip?.occurrences.length){
  const used=[...new Set(clip.occurrences.map(o=>o.frameVersionId))];
  const anchors=used.filter(id=>{const f=s.frames.find(f=>f.frameVersionId===id),a=s.alignments[id],g=s.alignmentGroups.find(g=>g.alignmentGroupId===f?.nativeScaleGroupId&&g.frameVersionIds.includes(id));return !g||!a||a.frameVersionId!==id||a.groupRevisionId!==g.groupRevisionId;});
  if(anchors.length)add('anchors',`사용 후보 ${anchors.length}개 정렬 확인`,'크기·발 정렬에서 현재 후보의 위치를 맞추세요.',{action:'align',clipId:clip.clipId,frameVersionId:anchors[0]});
  const excluded=used.find(id=>s.frames.find(f=>f.frameVersionId===id)?.review==='rejected');
  if(excluded)add('frames','제외한 후보 교체·다시 사용','후보 확인에서 제외 사유를 확인하세요.',{action:'frame-review',clipId:clip.clipId,frameVersionId:excluded});
  const inspection=inspectionState(s,jobs,dirty,clip.clipId);
  if(inspection.state!=='current')add('inspect',inspection.label,'저장 후 결과 확인에서 검사·미리보기를 만드세요.',{action:'inspect',clipId:clip.clipId});
  else if(inspection.issues.some(i=>i.severity!=='approval'))add('issues','자동 검사 문제 확인',inspection.label+' · 해당 프레임으로 돌아가 수정할 수 있습니다.',{action:'inspect',clipId:clip.clipId});
  const gates=exportGates(s,[clip.clipId],false);
  if(gates.length&&!anchors.length&&!excluded&&reference)add('settings','동작 설정 확인',gates.join(' '),{action:'clip-settings',clipId:clip.clipId});
  if(!dirty&&!conflict&&!gates.length&&inspection.state==='current'&&!inspection.issues.some(i=>i.severity==='error'))add('export','게임용 파일 출력','출력 시 서버가 파일·픽셀·경계를 다시 검사합니다.',{action:'export',clipId:clip.clipId});
 }
 return items;
}
