import {defaultTransform,type Snapshot,type DraftCommand,type Clip,type Occurrence} from './types';
const reviewReasons:Record<string,string>={
 addOccurrence:'재생 슬롯이 추가되었습니다.',removeOccurrence:'재생 슬롯이 삭제되었습니다.',
 duplicateOccurrence:'재생 슬롯이 복제되었습니다.',reorderOccurrences:'재생 순서가 변경되었습니다.',
 setTiming:'표시 시간이 변경되었습니다.',setTransform:'프레임 변형이 변경되었습니다.',
 setPixelEdits:'픽셀 편집이 변경되었습니다.',replaceFrameVersion:'사용 프레임이 교체되었습니다.',
 setAlignment:'앵커 설정이 변경되었습니다.',setAlignmentGroup:'정렬 그룹 설정이 변경되었습니다.',
 setFrameReview:'사용 프레임의 수동 승인 상태가 변경되었습니다.',setOutline:'테두리 설정이 변경되었습니다.',
 updateClip:'동작 설정이 변경되었습니다.',
};
function invalidateReview(entity:{reviewInvalidatedReason?:string;review?:string;approval?:string},key:'review'|'approval',reason:string,wasApproved=entity[key]==='approved'){
 if(wasApproved)entity.reviewInvalidatedReason=reason;
 entity[key]='pending';
}
// Compare points by value: object property order is not an edit.
function sameValue(a:any,b:any):boolean{
 if(a===b)return true;
 if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;
 const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.hasOwn(b,k)&&sameValue(a[k],b[k]));
}
export function applyDraft(base:Snapshot,commands:DraftCommand[]):Snapshot {
 const s=structuredClone(base);
 for(const {operation:o,localId} of commands){
 const frameGroup=s.alignmentGroups.find(g=>g.frameVersionIds.includes(o.frameVersionId));const pivot={x:(frameGroup?.cell?.width||512)/2,y:(frameGroup?.cell?.height||512)/2};
 const c=s.clips.find(x=>x.clipId===o.clipId);const occ=c?.occurrences.find(x=>x.occurrenceId===o.occurrenceId);const clipWasApproved=c?.review==='approved';
 switch(o.type){
 case 'updateCharacter':s.characterName=o.name;break;
 case 'setGenerationSettings':s.generationSettings={...o.settings};break;
 case 'createClip':s.clips.push({clipId:localId!,clipRevisionId:localId!,stateId:localId!,facing:'right',referenceRevisionId:s.activeReferenceRevisionId,loop:true,endBehavior:'hold-last',defaultFps:10,occurrences:[],review:'pending',...o.clip} as Clip);break;
 case 'updateClip':if(c){Object.assign(c,o.changes);if(o.changes.defaultFps)c.occurrences.forEach(x=>{if(x.timingMode==='fps')x.durationMs=Math.round(1000/c.defaultFps);});}break;
 case 'addOccurrence':if(c){const n:Occurrence={occurrenceId:localId!,frameVersionId:o.frameVersionId,durationMs:Math.round(1000/c.defaultFps),timingMode:'fps',transform:defaultTransform(pivot),pixelEdits:[]};c.occurrences.splice(o.index??c.occurrences.length,0,n);}break;
 case 'duplicateOccurrence':if(c&&occ){c.occurrences.splice(c.occurrences.indexOf(occ)+1,0,{...structuredClone(occ),occurrenceId:localId!});}break;
 case 'removeOccurrence':if(c){c.occurrences=c.occurrences.filter(x=>x.occurrenceId!==o.occurrenceId);}break;
 case 'reorderOccurrences':if(c){const old=c.occurrences;c.occurrences=o.occurrenceIds.map((id:string)=>old.find(x=>x.occurrenceId===id)).filter(Boolean);}break;
 case 'setTiming':if(occ){occ.timingMode=o.timingMode??'explicit';occ.durationMs=occ.timingMode==='fps'?Math.round(1000/c!.defaultFps):o.durationMs;}break;
 case 'setTransform':if(occ)occ.transform={...occ.transform,...o.transform};break;
 case 'setPixelEdits':if(occ)occ.pixelEdits=o.pixelEdits;break;
 case 'replaceFrameVersion':if(occ){occ.frameVersionId=o.frameVersionId;occ.pixelEdits=[];occ.transform=defaultTransform(pivot);}break;
 case 'setFrameReview':{const f=s.frames.find(x=>x.frameVersionId===o.frameVersionId);if(f){f.review=o.review;if(typeof o.reason==='string')f.reviewReason=o.reason.trim();if(o.hidden!==undefined)f.hidden=o.hidden;}break;}
 case 'setAlignmentGroup':{const g=s.alignmentGroups.find(x=>x.alignmentGroupId===o.alignmentGroupId);if(g)Object.assign(g,o.changes);break;}
 case 'setAlignment':{
 const previous=s.alignments[o.frameVersionId];const {reviewInvalidatedReason:_ignored,...incoming}=o.alignment;
 const changed=Object.entries(incoming).some(([k,v])=>!['approval','frameVersionId','groupRevisionId'].includes(k)&&!sameValue((previous as any)?.[k],v));
 const a={...previous,...incoming,frameVersionId:o.frameVersionId,groupRevisionId:frameGroup?.groupRevisionId};
 if(previous?.approval==='approved'&&(changed||incoming.approval==='pending'))invalidateReview(a,'approval',reviewReasons.setAlignment,true);
 else if(incoming.approval==='approved')delete a.reviewInvalidatedReason;
 s.alignments[o.frameVersionId]=a;break;
 }
 case 'setOutline':s.outline={...s.outline,...o.outline};break;
 }
 if(['setAlignment','setAlignmentGroup','setFrameReview','setOutline'].includes(o.type)){
 const affected=o.type==='setAlignmentGroup'?(s.alignmentGroups.find(g=>g.alignmentGroupId===o.alignmentGroupId)?.frameVersionIds||[]):[o.frameVersionId];
 s.clips.forEach(clip=>{if(o.type==='setOutline'||clip.occurrences.some(x=>affected.includes(x.frameVersionId)))invalidateReview(clip,'review',reviewReasons[o.type]);});
 }
 if(c){
 if(o.type==='updateClip'&&Object.keys(o.changes).length===1&&'review' in o.changes){
 if(c.review==='approved')delete c.reviewInvalidatedReason;
 else if(clipWasApproved)invalidateReview(c,'review','동작 승인이 해제되었습니다.',true);
 }else invalidateReview(c,'review',o.type==='updateClip'&&'referenceRevisionId' in o.changes?'연결된 기준이 변경되었습니다.':reviewReasons[o.type]||'동작 설정이 변경되었습니다.',clipWasApproved);
 }
 if(o.type==='setAlignmentGroup'){
 const g=s.alignmentGroups.find(g=>g.alignmentGroupId===o.alignmentGroupId);
 g?.frameVersionIds.forEach(id=>{if(s.alignments[id])invalidateReview(s.alignments[id],'approval',reviewReasons.setAlignmentGroup);});
 if(g?.mode==='shared-scale-foot-anchor'&&g.bodyMeasurement)g.sharedScale=g.bodyMeasurement.targetHeight/(g.bodyMeasurement.bottomY-g.bodyMeasurement.topY);
 }
 }
 return s;
}
export function remapCommand(command:DraftCommand,ids:Record<string,string>):DraftCommand {const walk=(v:any):any=>typeof v==='string'?(ids[v]||v):Array.isArray(v)?v.map(walk):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).map(([k,x])=>[k,walk(x)])):v;return {...command,operation:walk(command.operation)};}
export function exportGates(s:Snapshot,clipIds:string[],dirty:boolean):string[]{
 const issues:string[]=[];
 if(dirty)issues.push('저장되지 않은 초안이 있습니다. 먼저 저장해 주세요.');
 if(!clipIds.length)issues.push('출력할 동작을 선택해 주세요.');
 if(new Set(clipIds).size!==clipIds.length)issues.push('같은 동작이 중복 선택되었습니다.');
 for(const id of clipIds){
  if(!s.clips.some(c=>c.clipId===id))issues.push('출력할 동작을 찾을 수 없습니다. 다시 선택해 주세요.');
 }
 for(const c of s.clips.filter(c=>clipIds.includes(c.clipId))){
  if(!c.occurrences.length)issues.push(`${c.name}: 재생 순서가 비어 있습니다.`);
  if(c.review!=='approved')issues.push(`${c.name}: 동작 수동 승인이 필요합니다.`);
  if(!s.references.some(r=>r.referenceRevisionId===c.referenceRevisionId&&r.approval==='approved'))issues.push(`${c.name}: 승인된 기준을 연결해 주세요.`);
  if(!Number.isFinite(c.defaultFps)||c.defaultFps<1||c.defaultFps>60)issues.push(`${c.name}: FPS는 1–60이어야 합니다.`);
  if(c.endBehavior&&c.endBehavior!=='hold-last')issues.push(`${c.name}: 지원하지 않는 재생 종료 방식입니다.`);
  const occurrenceIds=new Set<string>();
  for(const o of c.occurrences){
   if(!o.occurrenceId||occurrenceIds.has(o.occurrenceId))issues.push(`${c.name}: 재생 슬롯 ID가 없거나 중복됩니다.`);
   occurrenceIds.add(o.occurrenceId);
   if(o.timingMode&&!['fps','explicit'].includes(o.timingMode))issues.push(`${c.name}: 지원하지 않는 시간 설정입니다.`);
   if(o.timingMode==='fps'&&o.durationMs!==Math.round(1000/c.defaultFps))issues.push(`${c.name}: FPS와 표시 시간이 다릅니다.`);
   if(!Number.isInteger(o.durationMs)||o.durationMs<1||o.durationMs>60000)issues.push(`${c.name}: 표시 시간은 1–60000ms여야 합니다.`);
   const f=s.frames.find(f=>f.frameVersionId===o.frameVersionId);
   if(!f){issues.push(`${c.name}: 누락된 후보를 교체해 주세요.`);continue;}
   if(f.review==='rejected')issues.push(`${c.name}: 거절된 후보입니다.${f.reviewReason?` ${f.reviewReason}`:' 재검수 후 승인해 주세요.'}`);
   else if(f.review!=='approved')issues.push(`${c.name}: 후보 수동 승인이 필요합니다.`);
   const a=s.alignments[f.frameVersionId];
   const g=s.alignmentGroups.find(g=>g.alignmentGroupId===f.nativeScaleGroupId&&g.frameVersionIds.includes(f.frameVersionId));
   if(!g||a?.approval!=='approved'||a.groupRevisionId!==g.groupRevisionId||a.frameVersionId!==f.frameVersionId)issues.push(`${c.name}: 현재 정렬 기준의 앵커 승인이 필요합니다.`);
   if(a?.contactMode==='airborne'&&!a.rootAnchor)issues.push(`${c.name}: 공중 자세의 루트 앵커가 필요합니다.`);
  }
 }
 return [...new Set(issues)];
}
