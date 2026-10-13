import {useState,useId,type KeyboardEvent} from 'react';
import type {Studio} from './useStudio';
import type {Clip,ExportRecord,Job,Snapshot} from './types';
import {AssetsStep,ReferenceStep,GenerationStep,ExtractStep} from './SourceSteps';
import {EditStep} from './AnimationWorkspace';
import {ExportStep} from './FinishSteps';
import {exportGates} from './draft';
import {inspectionState,type WorkTarget} from './workflow';
import {defaultReference} from './referenceLabel';
import './production-workflow.css';

export const productionSteps=[
 {label:'자료 준비',description:'이미지를 가져오거나 생성해 원본 자료를 보관하세요.'},
 {label:'캐릭터 기준',description:'기준 이미지와 얼굴·의상·장비의 고정 특징을 정하세요.'},
 {label:'동작 만들기',description:'동작을 생성하거나 기존 이미지·영상에서 후보를 만드세요.'},
 {label:'프레임 편집',description:'후보를 골라 순서·시간·픽셀을 편집하고 크기·발을 맞추세요.'},
 {label:'결과 확인',description:'저장된 결과를 재생하고, 필요한 단계로 돌아가 수정하세요.'},
 {label:'내보내기',description:'게임용 파일을 만들고 다운로드하세요. 이전 결과도 보존됩니다.'},
];
export type StageStatus='대기'|'작업 중'|'준비됨'|'수정 필요'|'출력 완료';
export function productionProgress(p:Snapshot,clip:Clip|undefined,jobs:Job[],exports:ExportRecord[],dirty:boolean,conflict=false){
 const reference=clip?.referenceRevisionId?p.references.find(r=>r.referenceRevisionId===clip.referenceRevisionId):defaultReference(p);
 const assetsReady=!!p.assets.length;
 const referenceReady=!!reference&&p.assets.some(a=>a.assetId===reference.identityAssetId);
 const framesReady=clip?.occurrences.length?clip.occurrences.every(o=>p.frames.some(f=>f.frameVersionId===o.frameVersionId)):!!p.frames.length;
 const gates=exportGates(p,clip?[clip.clipId]:[],dirty||conflict||!!p.storage?.syncPending);
 const editedReady=!!clip?.occurrences.length&&!gates.length;
 const report=inspectionState(p,jobs,dirty||conflict||!!p.storage?.syncPending,clip?.clipId);
 const reviewReady=editedReady&&report.state==='current'&&!report.issues.some(i=>i.severity==='error');
 const output=clip?exports.find(e=>['succeeded','completed'].includes(e.status)&&e.manifest?.clips.some(c=>c.id===clip.clipId)&&e.files?.some(a=>a.name==='atlas.png')&&e.files?.some(a=>a.name==='runtime.json')&&e.manifest.projectRevision===p.revision):undefined;
 const outputReady=!!output&&!dirty&&!conflict&&!p.storage?.syncPending;
 const statuses:StageStatus[]=[assetsReady?'준비됨':'대기',referenceReady?'준비됨':p.references.length?'수정 필요':'대기',framesReady?'준비됨':'대기',editedReady?'준비됨':clip?.occurrences.length?'수정 필요':'대기',reviewReady?'준비됨':report.state==='missing'?'대기':'수정 필요',outputReady?'출력 완료':clip&&exports.some(e=>e.manifest?.clips.some(c=>c.id===clip.clipId))?'수정 필요':'대기'];
 const running=jobs.filter(j=>['queued','running','cancel_requested'].includes(j.status));
 const relevant=(j:Job)=>!clip||j.inspectionClipIds?.includes(clip.clipId)||j.result?.manifest?.clips.some(c=>c.id===clip.clipId);
 if(running.some(j=>j.operation==='generate'))statuses[0]='작업 중';
 if(running.some(j=>['generate','generate_video','process_video','extract','cutout'].includes(j.operation)))statuses[2]='작업 중';
 if(running.some(j=>['inspect','bake'].includes(j.operation)&&relevant(j)))statuses[4]='작업 중';
 if(running.some(j=>j.operation==='export'&&relevant(j)))statuses[5]='작업 중';
 const ready=[assetsReady,referenceReady,framesReady,editedReady,reviewReady,outputReady];
 const hints=['자료를 가져오거나 생성하세요.','기준 이미지와 고정 특징을 저장하세요.','동작을 생성하거나 원본에서 프레임을 나누세요.',gates[0]||'동작에 후보를 추가하세요.',gates[0]||(report.state==='missing'?'저장한 뒤 선택 동작 자동 검사를 실행하세요.':report.label),'게임용 파일 출력으로 결과를 저장하세요.'];
 return {statuses,ready,hints};
}
export function productionTabKeys(event:KeyboardEvent<HTMLElement>){
 const tabs=Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
 const current=tabs.indexOf(event.target as HTMLButtonElement);if(current<0)return;
 const index=event.key==='Home'?0:event.key==='End'?tabs.length-1:event.key==='ArrowRight'?(current+1)%tabs.length:event.key==='ArrowLeft'?(current+tabs.length-1)%tabs.length:-1;
 if(index>=0){event.preventDefault();tabs[index].focus();tabs[index].click();}
}
export function ProductionWorkflow({s,step,onStep,clipId,onClip,onTool,onSelectionChange,sourceMode,onSourceMode,sourceAssetId}:{s:Studio;step:number;onStep:(step:number)=>void;clipId:string;onClip:(id:string)=>void;onTool:(id:string,selection?:{frameVersionId?:string;assetId?:string})=>void;onSelectionChange:(selection:{frameVersionId?:string;assetId?:string})=>void;sourceMode:'generate'|'extract';onSourceMode:(mode:'generate'|'extract')=>void;sourceAssetId?:string}){
 const p=s.snapshot!,id=useId();
 const [navigationTarget,setNavigationTarget]=useState<WorkTarget>();
 const [visited,setVisited]=useState<number[]>([3,step]);
 if(!visited.includes(step))setVisited([...visited,step]);
 const [sourceVisited,setSourceVisited]=useState<string[]>([sourceMode]);
 if(!sourceVisited.includes(sourceMode))setSourceVisited([...sourceVisited,sourceMode]);
 const clip=p.clips.find(c=>c.clipId===s.resolveId(clipId))||p.clips[0];
 const progress=productionProgress(p,clip,s.jobs,s.exports,!!s.commands.length,!!s.conflict);
 function navigate(target:WorkTarget){
  if(target.clipId)onClip(target.clipId);
  if(target.action==='save'){void s.save();return;}
  const stages:Record<string,number>={assets:0,reference:1,generate:2,extract:2,align:3,'frame-review':3,'clip-review':4,'clip-settings':3,candidates:3,'create-clip':3,inspect:4,export:5,pixel:3};
  if(target.action==='align'||target.action==='conflict'){onTool(target.action,target);return;}
  if(target.action==='generate'||target.action==='extract')onSourceMode(target.action);
  if((stages[target.action]??3)===3)setNavigationTarget({...target});
  onStep(stages[target.action]??3);
 }
 return <div className="production-workflow">
  <div className="production-tabs" role="tablist" aria-label="제작 순서" onKeyDown={productionTabKeys}>{productionSteps.map((stage,index)=><button type="button" key={stage.label} id={`${id}-tab-${index}`} role="tab" aria-selected={step===index} aria-controls={`${id}-panel-${index}`} tabIndex={step===index?0:-1} data-status={progress.statuses[index]} onClick={()=>onStep(index)}><span className="production-step-number" aria-hidden="true">{index+1}</span><span><strong>{stage.label}</strong><small>{progress.statuses[index]}</small></span></button>)}</div>
  <div className="production-heading"><div><h2>{step+1}. {productionSteps[step].label}</h2><p>{productionSteps[step].description}</p></div>{step>=3&&<label>작업 동작<select aria-label="작업 동작" value={clip?.clipId||''} onChange={e=>onClip(e.target.value)}><option value="" disabled>동작을 만들어 주세요</option>{p.clips.map(c=><option key={c.clipId} value={c.clipId}>{c.name}</option>)}</select></label>}{step===3&&<button onClick={()=>onTool('align')}>크기·발 정렬</button>}{step===4&&<div className="row"><button onClick={()=>onStep(1)}>캐릭터 기준 수정</button><button onClick={()=>{onSourceMode('generate');onStep(2);}}>동작 다시 만들기</button><button onClick={()=>onStep(3)}>프레임·시간 수정</button><button onClick={()=>onTool('align')}>크기·발 정렬</button></div>}</div>
  <div className="production-panels">{productionSteps.map((stage,index)=><section key={stage.label} id={`${id}-panel-${index}`} role="tabpanel" aria-labelledby={`${id}-tab-${index}`} tabIndex={0} hidden={step!==index} className="production-panel">{visited.includes(index)&&<>
   {index===0&&<AssetsStep s={s} onNext={()=>onStep(1)} onGenerate={()=>onTool('generateAsset')}/>}
   {index===1&&<ReferenceStep s={s} initialReferenceRevisionId={clip?.referenceRevisionId||undefined}/>}
   {index===2&&<div className="production-source"><div className="row production-source-switch" role="group" aria-label="동작을 만드는 방법"><button aria-pressed={sourceMode==='generate'} onClick={()=>onSourceMode('generate')}>이미지·영상 생성</button><button aria-pressed={sourceMode==='extract'} onClick={()=>onSourceMode('extract')}>기존 이미지 나누기</button></div>{sourceVisited.includes('generate')&&<div hidden={sourceMode!=='generate'}><GenerationStep s={s} initialReferenceRevisionId={clip?.referenceRevisionId||undefined} onSelectClip={next=>{onClip(next);onStep(3);}}/></div>}{sourceVisited.includes('extract')&&<div hidden={sourceMode!=='extract'}><ExtractStep s={s} initialAssetId={sourceAssetId}/></div>}</div>}
   {index===3&&<EditStep s={s} clipId={clipId} onClip={onClip} onAction={onTool} onSelectionChange={onSelectionChange} navigationTarget={navigationTarget}/>}
   {index===4&&<ExportStep s={s} mode="review" clipId={clip?.clipId} onNavigate={navigate}/>}
   {index===5&&<ExportStep s={s}/>}
  </>}</section>)}</div>
  <footer className="production-footer"><button disabled={step===0} onClick={()=>onStep(step-1)}>이전</button><span role="status">현재 단계 {step+1} / 6 · {progress.statuses[step]}{!progress.ready[step]?` · ${progress.hints[step]}`:''}</span>{step<5&&<button className="primary" disabled={!progress.ready[step]} onClick={()=>onStep(step+1)}>다음: {productionSteps[step+1].label}</button>}</footer>
 </div>;
}
