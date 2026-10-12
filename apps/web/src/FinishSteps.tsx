import {PropertyHelp} from './PropertyHelp';
import {useState,useEffect,useRef,useId} from 'react';
import {api,downloadJson} from './api';
import {isVideoJob,videoJobStep,videoRetryLabel} from './videoWorkflow';
import {VideoDiagnostics} from './VideoDiagnostics';
import type {Studio} from './useStudio';
import {exportGates} from './draft';
import {InspectionPanel} from './WorkflowPanel';
import {type WorkTarget} from './workflow';
import {EditorCanvas,RuntimePlayer} from './Canvas';
import './export-workspace.css';
import {Panel,Input,Select,Num,Check,Empty,short,date} from './ui';
import {uid,type Runtime,type Job,type Artifact,type ExportRecord} from './types';
const jobNames:Record<string,string>={preview_follow:'부위 흔들림 미리보기',apply_follow:'부위 흔들림 새 동작 저장',check_handed:'장비 좌우 검사',generate:'이미지 생성',generate_video:'영상 생성·후보 추출',process_video:'기존 영상 후보 추출',extract:'프레임 추출',cutout:'배경 제거',align:'공통 정렬',inspect:'자동 검사',bake:'확정 미리보기',export:'게임용 출력',backup:'프로젝트 백업',restore:'백업 복원'};
const statuses:Record<string,string>={queued:'대기 중',running:'처리 중',needs_review:'처리 완료 · 직접 확인 필요',succeeded:'완료',completed:'완료',failed:'실패',cancel_requested:'취소 요청됨',canceled:'취소됨',interrupted:'중단됨',provider_outcome_unknown:'외부 접수 결과 불명'};
export function JobCard({job,s,onSelectClip}:{job:Job;s:Studio;onSelectClip?:(clipId:string)=>void}){
 const progress=typeof job.progress==='number'?job.progress:job.progress?.percent;
 const videoJob=isVideoJob(job);
 const retryLabel=videoJob?videoRetryLabel(job):['failed','interrupted','canceled'].includes(job.status)?'실패 단계 재시도':null;
 const video=s.snapshot?.videos?.find(v=>v.videoId===job.result?.videoId);
 const clip=s.snapshot?.clips.find(c=>c.clipId===job.result?.clipId);
 const outputNames:Record<string,string>={'final-preview/animation.gif':'GIF','final-preview/animation.webp':'WebP','final-preview/strip.png':'가로 시트 PNG','final-preview/grid.png':'격자 시트 PNG'};
 const downloads=job.artifacts?.filter(a=>!videoJob||!!outputNames[a.name]);
 const diagnostics=videoJob?job.artifacts?.filter(a=>!outputNames[a.name]):[];
 return <article className="job-card">
  <div className="row"><strong>{jobNames[job.operation]||job.operation}</strong><span className={`badge ${['succeeded','completed'].includes(job.status)?'success':['failed','interrupted','provider_outcome_unknown'].includes(job.status)?'warn':''}`}>{statuses[job.status]||job.status}</span><small>입력 버전 {job.inputRevision}</small></div>
  {videoJob?<p className="caption" aria-live="polite">{videoJobStep(job)}</p>:null}
  {progress!==undefined?<progress max={100} value={progress<=1?progress*100:progress} aria-label="처리 진행률"/>:null}
  {job.errors?.map((e,i)=><p className="error" key={i}>{e.message}</p>)}
  {job.error?<p className="error">{job.error.message}</p>:null}
  {job.status==='provider_outcome_unknown'?<p className="warning">외부 생성이 접수되었을 수 있습니다. 접수 결과가 확인되지 않아 요청을 다시 보내지 않습니다.</p>:null}
  {videoJob?<VideoDiagnostics processing={job.result?.processing}/>:null}
  {videoJob&&retryLabel?<p className="caption">저장된 영상 또는 접수한 요청을 이어서 처리합니다. 새 영상 생성 요청은 보내지 않습니다.</p>:null}
  <div className="row">
   {['queued','running'].includes(job.status)?<button disabled={s.busy} onClick={()=>s.run(async()=>{await api(`/jobs/${job.jobId}/cancel`,'POST',{expectedStatus:job.status});if(s.base)await s.refreshDetails(s.base.projectId);})}>작업 취소 요청</button>:null}
   {retryLabel?<button disabled={s.busy||!!s.commands.length||!!s.conflict} onClick={()=>s.run(async()=>{await api(`/jobs/${job.jobId}/retry`,'POST',{failedStep:job.failedStep||job.step||'',reuseCheckpoint:true,idempotencyKey:uid()});if(s.base)await s.refreshDetails(s.base.projectId);})}>{retryLabel}</button>:null}
   {video?<a className="button" href={video.url} download={video.originalFilename}>원본 MP4 다운로드</a>:null}
   {clip&&onSelectClip?<button onClick={()=>onSelectClip(clip.clipId)}>결과 동작 편집</button>:null}
   {downloads?.map(a=><a className="button" key={a.artifactId} href={a.url} download={a.name}>{outputNames[a.name]||a.name} 다운로드</a>)}
  </div>
  <details><summary>진단 정보</summary><p className="mono">작업 {job.jobId} · 단계 {job.step||'대기'}</p>{diagnostics?.map(a=><p key={a.artifactId}><a href={a.url} download={a.name}>{a.name}</a></p>)}{job.result?.qa?<pre>{JSON.stringify(job.result.qa,null,2)}</pre>:null}{job.result?.processing?<pre>{JSON.stringify(job.result.processing,null,2)}</pre>:null}</details>
 </article>;
}
export function JobsStep({s,onSelectClip}:{s:Studio;onSelectClip?:(clipId:string)=>void}){return <Panel title="작업 센터" eyebrow="BACKGROUND JOBS"><p className="muted">탭을 닫아도 작업은 처리됩니다. 원본과 성공한 다른 결과는 보존됩니다.</p>{s.jobs.slice().reverse().map(j=><JobCard key={j.jobId} job={j} s={s} onSelectClip={onSelectClip}/>)}{!s.jobs.length&&<Empty title="진행한 작업이 없습니다"><p>생성하거나 이미지를 추출하면 진행 상태를 여기서 확인할 수 있습니다.</p></Empty>}</Panel>}
export function ReviewStep({s}:{s:Studio;clipId?:string;onNavigate?:(target:WorkTarget)=>void}){const p=s.snapshot!;const outline=p.outline;const setOutline=(change:Record<string,unknown>)=>s.edit({type:'setOutline',outline:{...outline,...change}});const hex='#'+outline.colorRGBA.slice(0,3).map(x=>x.toString(16).padStart(2,'0')).join('');
 return <Panel title="팀 테두리" actions={<PropertyHelp title="팀 테두리" description="캐릭터 외곽에 팀을 구분하는 색 테두리를 추가합니다. 셀 경계·안전 여백 가이드와는 다른 효과입니다. 사용을 켠 뒤 미리보기 전용 또는 출력 파일 포함을 선택하세요."/>}><Check label="테두리 사용" checked={outline.enabled} onChange={enabled=>setOutline({enabled})}/><Input label="팀 이름" value={outline.teamLabel} onChange={e=>setOutline({teamLabel:e.target.value})}/><Input label="테두리 색" type="color" value={hex} onChange={e=>setOutline({colorRGBA:[parseInt(e.target.value.slice(1,3),16),parseInt(e.target.value.slice(3,5),16),parseInt(e.target.value.slice(5,7),16),outline.colorRGBA[3]]})}/><span className="mono">{hex.toUpperCase()}</span><Num label="두께 (셀 픽셀)" value={outline.thicknessPx} onChange={thicknessPx=>setOutline({thicknessPx})} min={1} max={16}/><Num label="복제당 불투명도" value={outline.opacityPerCopy} step={.05} min={0} max={1} onChange={opacityPerCopy=>setOutline({opacityPerCopy})}/><Select label="방향" value={outline.directions} onChange={e=>setOutline({directions:+e.target.value})}><option value={4}>4방향</option><option value={8}>8방향</option></Select><Select label="포함 범위" value={outline.mode} onChange={e=>setOutline({mode:e.target.value})}><option value="preview-only">편집 미리보기 전용</option><option value="bake">출력 파일에 포함</option></Select><div className="callout"><strong>테두리 없이도 확인하세요</strong><p>테두리를 끄더라도 알파 잔여물과 잘림 경고는 사라지지 않습니다. 파일 포함 시 셀 경계를 다시 검사합니다.</p></div></Panel>
}
function ExportFailure({record,s}:{record:ExportRecord;s:Studio}) {
 const knownJob=s.jobs.find(j=>j.jobId===record.jobId);
 const [fetched,setFetched]=useState<Job|null>(null),[lookupError,setLookupError]=useState(''),[reload,setReload]=useState(0);
 const terminalFailure=['failed','interrupted','provider_outcome_unknown'].includes(record.status);
 const knownErrors=record.errors?.length?record.errors:knownJob?.errors?.length?knownJob.errors:knownJob?.error?[knownJob.error]:[];
 const hasKnownErrors=knownErrors.some(e=>!!e.message);
 useEffect(()=>{if(!terminalFailure||!record.jobId||hasKnownErrors&&reload===0)return;let active=true;setLookupError('');api<Job>(`/jobs/${record.jobId}`).then(job=>{if(active)setFetched(job);}).catch(e=>{if(active)setLookupError(e.message);});return()=>{active=false;};},[record.jobId,record.status,terminalFailure,hasKnownErrors,reload]);
 if(!terminalFailure)return null;
 const errors=hasKnownErrors?knownErrors:fetched?.errors?.length?fetched.errors:fetched?.error?[fetched.error]:[];
 return <div className="error export-failure" role="alert"><div><strong>출력하지 못했습니다</strong>{errors.length?errors.map((e,i)=><p key={i}>{e.message||'출력 검증을 통과하지 못했습니다.'}</p>):<p>{lookupError||'실패한 작업의 상세 원인을 확인하고 있습니다.'}</p>}<p>문제를 수정하고 저장·검수한 뒤 새 출력을 요청하세요. 이전 성공 결과는 유지됩니다.</p>{record.jobId&&<><button onClick={()=>setReload(n=>n+1)}>실패 원인 다시 조회</button><details><summary>실패 진단 정보</summary><p className="mono">작업 {record.jobId} · 단계 {knownJob?.step||fetched?.step||'확인 중'}</p>{errors.map((e,i)=><small className="mono" key={i}>{e.code||'출력 오류'} </small>)}</details></>}</div></div>;
}
export function ExportStep({s,mode='export',clipId,onNavigate}:{s:Studio;mode?:'review'|'export';clipId?:string;onNavigate?:(target:WorkTarget)=>void}){
 const p=s.snapshot!;
 const [selected,setSelected]=useState<string[]>(p.clips.map(c=>c.clipId));
 // undefined follows the latest successful export; null keeps an explicit close.
 const [preview,setPreview]=useState<{runtime:Runtime;url:string;projectId:string}|null|undefined>(undefined);
 const [view,setView]=useState<'preview'|'settings'>('preview');
 const [sidebarView,setSidebarView]=useState<'settings'|'history'>('settings');
 const [occurrenceId,setOccurrenceId]=useState('');
 const request=useRef(0),viewId=useId();
 const separator=p.storage?.path.includes('\\')?'\\':'/';
 const outputFolder=p.storage?.path?`${p.storage.path.replace(/[\\/]+$/,'')}${separator}outputs`:'';
 const exportHistory=s.exports.map(e=>{
  const job=s.jobs.find(j=>j.jobId===e.jobId);
  return {...e,createdAt:job?.createdAt,completedAt:['succeeded','completed'].includes(e.status)?job?.updatedAt:undefined,attemptId:job?.attemptId};
 }).sort((a,b)=>(Date.parse(b.completedAt||b.createdAt||'')||0)-(Date.parse(a.completedAt||a.createdAt||'')||0));
 const selectedClipIds=(mode==='review'?(clipId?[clipId]:[]):selected).filter(id=>p.clips.some(c=>c.clipId===id));
 const gates=exportGates(p,selectedClipIds,!!s.commands.length||!!s.conflict||!!p.storage?.syncPending);
 const clipRevisionIds=p.clips.filter(c=>selectedClipIds.includes(c.clipId)).map(c=>c.clipRevisionId);
 const bake=s.jobs.filter(j=>j.operation==='bake'&&['succeeded','completed','needs_review'].includes(j.status)&&j.result?.manifest&&j.artifacts?.some(f=>f.name==='atlas.png')&&(mode!=='review'||j.result.manifest.clips.some(c=>c.id===clipId))).slice().sort((a,b)=>(b.createdAt||'').localeCompare(a.createdAt||'')||b.inputRevision-a.inputRevision)[0];
 const latest=exportHistory.find(e=>['succeeded','completed'].includes(e.status)&&e.manifest&&(mode!=='review'||e.manifest.clips.some(c=>c.id===clipId))&&e.files?.some(f=>f.name==='atlas.png'));
 const latestAtlas=latest?.files?.find(f=>f.name==='atlas.png');
 const bakeAtlas=bake?.artifacts?.find(f=>f.name==='atlas.png');
 const useBake=bake?.result?.manifest&&bakeAtlas&&(!latest?.manifest||bake.inputRevision>latest.manifest.projectRevision||bake.inputRevision===latest.manifest.projectRevision&&(Date.parse(bake.updatedAt||bake.createdAt||'')||0)>(Date.parse(latest.completedAt||latest.createdAt||'')||0));
 const automatic=useBake?{runtime:bake.result!.manifest!,url:bakeAtlas!.url,projectId:p.projectId}:latest?.manifest&&latestAtlas?{runtime:latest.manifest,url:latestAtlas.url,projectId:p.projectId}:null;
 const current=preview===null?null:preview===undefined?automatic:preview.projectId===p.projectId&&(mode!=='review'||preview.runtime.clips.some(c=>c.id===clipId))?preview:automatic;
 const clip=p.clips.find(c=>c.clipId===clipId);
 const livePreview=mode==='review'&&(!current||preview===undefined&&(current.runtime.projectRevision!==p.revision||!!s.commands.length));
 useEffect(()=>{
  setSelected(p.clips.map(c=>c.clipId));setPreview(undefined);setView('preview');setSidebarView('settings');
  return()=>{request.current++;};
 },[p.projectId]);
 function closePreview(){request.current++;setPreview(null);}
 function show(manifest:Runtime|undefined,files:Artifact[]){
  const atlas=files.find(f=>f.name==='atlas.png'),runtime=files.find(f=>f.name==='runtime.json');
  if(!atlas){s.setError('아틀라스 산출물이 없습니다. 작업 센터에서 실패 원인을 확인하세요.');return;}
  const ticket=++request.current;
  if(manifest){setPreview({runtime:manifest,url:atlas.url,projectId:p.projectId});setView('preview');}
  else if(runtime)s.run(async()=>{
   const r=await fetch(runtime.url);if(!r.ok)throw new Error('출력 manifest를 읽지 못했습니다.');
   const loaded:Runtime=await r.json();
   if(ticket===request.current){setPreview({runtime:loaded,url:atlas.url,projectId:p.projectId});setView('preview');}
  });
  else s.setError('출력 재생 정보가 없습니다. runtime.json 산출물을 확인해 주세요.');
 }
 return <div className="export-workspace" data-view={view} data-mode={mode}>
  <div className="export-view-switch" role="group" aria-label="출력 작업 보기">
   <button aria-pressed={view==='preview'} aria-controls={`${viewId}-preview`} onClick={()=>setView('preview')}>{mode==='review'?'결과 미리보기':'출력 결과'}</button>
   <button aria-pressed={view==='settings'} aria-controls={`${viewId}-settings`} onClick={()=>setView('settings')}>{mode==='review'?'검사·설정':'설정·다운로드'}</button>
  </div>
  <section id={`${viewId}-preview`} className="export-preview panel" aria-label="출력 결과 미리보기">
   <div className="export-preview-heading">
    <div><h2>{mode==='review'?'결과 확인':'출력 결과'}</h2><p className="caption">{livePreview?'현재 동작의 작업 미리보기입니다. 확정 미리보기 만들기로 최종 픽셀·경계를 검사하세요.':current?`출력 ${short(current.runtime.exportId)} · 저장 버전 ${current.runtime.projectRevision}`:'최근 성공한 출력이 여기에 표시됩니다.'}</p></div>
    <div className="row">
     {automatic&&<button onClick={()=>{request.current++;setPreview(mode==='review'?automatic:undefined);setView('preview');}}>최근 성공 결과</button>}
     {current&&!livePreview&&<button onClick={closePreview}>{mode==='review'?'작업 미리보기':'닫기'}</button>}
    </div>
   </div>
   {current&&!livePreview&&(current.runtime.projectRevision!==p.revision||!!s.commands.length)&&<p className="export-preview-version badge warn">현재 편집과 다른 버전 · 저장된 이전 결과를 표시합니다.</p>}
   {livePreview?(clip?.occurrences.length?<EditorCanvas key={clip.clipId} snapshot={p} clip={clip} selected={occurrenceId} onSelect={setOccurrenceId}/>:<div className="export-preview-empty"><Empty title="확인할 동작 프레임이 없습니다"><p>프레임 편집에서 후보를 동작의 재생 순서에 추가하세요.</p>{onNavigate&&<button onClick={()=>onNavigate({action:'pixel',clipId})}>프레임 편집으로 이동</button>}</Empty></div>):current?<RuntimePlayer key={mode==='review'?clipId:undefined} runtime={mode==='review'?{...current.runtime,clips:current.runtime.clips.filter(c=>c.id===clipId)}:current.runtime} atlasUrl={current.url} initialZoom="fit"/>:<div className="export-preview-empty"><Empty title="표시할 출력 결과를 선택해 주세요"><p>미리보기나 게임용 파일을 만든 뒤 이곳에서 재생할 수 있습니다. 이전 출력도 다시 열 수 있습니다.</p><button onClick={()=>setView('settings')}>출력 설정 열기</button></Empty></div>}
  </section>
  <aside id={`${viewId}-settings`} className="export-sidebar" aria-label="출력 설정과 다운로드">
   {mode==='export'&&<div className="export-sidebar-tabs" role="tablist" aria-label="출력 설정과 이력" onKeyDown={e=>{
    const next=e.key==='Home'?'settings':e.key==='End'?'history':['ArrowLeft','ArrowRight'].includes(e.key)?sidebarView==='settings'?'history':'settings':undefined;
    if(next){e.preventDefault();setSidebarView(next);e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next==='settings'?0:1]?.focus();}
   }}>
    <button type="button" id={`${viewId}-settings-tab`} role="tab" aria-selected={sidebarView==='settings'} aria-controls={`${viewId}-options`} tabIndex={sidebarView==='settings'?0:-1} onClick={()=>setSidebarView('settings')}>출력 설정</button>
    <button type="button" id={`${viewId}-history-tab`} role="tab" aria-selected={sidebarView==='history'} aria-controls={`${viewId}-history`} tabIndex={sidebarView==='history'?0:-1} onClick={()=>setSidebarView('history')}>출력 이력 <span className="badge">{s.exports.length}</span></button>
   </div>}
   <section id={`${viewId}-options`} className="export-settings panel" role={mode==='export'?'tabpanel':undefined} aria-labelledby={mode==='export'?`${viewId}-settings-tab`:undefined} aria-label="출력 설정" tabIndex={0} hidden={mode==='export'&&sidebarView!=='settings'}>
    <div className="panel-heading"><h2>{mode==='review'?'미리보기·수정':'출력 설정'}</h2></div>
    <p className="muted">{mode==='review'?'편집 중인 동작은 바로 재생됩니다. 확정 미리보기는 저장된 버전으로 만듭니다.':'저장된 버전으로 미리보기와 게임용 파일을 만듭니다.'}</p>
    {mode==='export'&&<div className="export-destination" role="group" aria-label="출력 저장 위치">
     <Input label="자동 저장 폴더" readOnly value={outputFolder||'프로젝트 폴더 경로를 확인해 주세요.'} title={outputFolder}/>
     <button disabled={s.busy||!s.service?.desktop?.fileManager||!outputFolder||p.storage?.available===false} onClick={()=>s.revealProject(p)}>프로젝트 폴더 열기</button>
     <p className="caption">프로젝트의 outputs 폴더에 출력별 하위 폴더가 생성됩니다. 아래 다운로드는 브라우저의 다운로드 설정에 따라 별도로 저장됩니다.</p>
    </div>}
    {mode==='export'&&<details className="export-clip-options"><summary>출력할 동작 · {selectedClipIds.length} / {p.clips.length}개 선택</summary><div className="export-clip-selection" role="group" aria-label="출력할 동작">{p.clips.map(c=><Check key={c.clipId} label={`${c.name} · ${c.occurrences.length} 슬롯`} checked={selected.includes(c.clipId)} onChange={v=>setSelected(v?[...selected,c.clipId]:selected.filter(id=>id!==c.clipId))}/>)}</div></details>}
    <div className="export-actions row">
     <button disabled={s.busy||!!gates.length||s.service?.worker!=='ready'} onClick={()=>{setPreview(undefined);setView('preview');void s.job('bake',[],{clipIds:selectedClipIds,clipRevisionIds});}}>확정 미리보기 만들기</button>
     {mode==='export'&&<button className="primary" disabled={s.busy||!!gates.length||s.service?.worker!=='ready'} onClick={async()=>{const ticket=++request.current;const result=await s.mutation(`/projects/${p.projectId}/exports`,{savedRevision:p.revision,clipRevisionIds,formats:['atlas','pngs','runtime','aseprite'],outlineMode:p.outline.mode,idempotencyKey:uid()});if(result&&ticket===request.current){setPreview(undefined);setSidebarView('history');setView('settings');}}}>게임용 파일 출력</button>}
    </div>
    {gates.length?<ul className="gate-list">{gates.map(g=><li key={g}>{g}</li>)}</ul>:<p className="success-text">저장·동작 설정 준비됨. 출력 시 서버가 픽셀·경계·파일을 검사합니다.</p>}
    {mode==='review'&&<InspectionPanel s={s} clip={p.clips.find(c=>c.clipId===clipId)} onNavigate={onNavigate}/>}
    {bake&&<button onClick={()=>show(bake.result?.manifest,bake.artifacts||[])}>최근 미리보기 보기 · 버전 {bake.inputRevision}</button>}
    <details className="export-format-help"><summary>출력 파일 안내</summary>
     <ul className="deliverables"><li><strong>atlas.png + runtime.json</strong><span>프레임 영역, 순서, 가변 시간, 앵커, 반복</span></li><li><strong>pngs.zip</strong><span>순서별 PNG · 같은 아틀라스에서 추출</span></li><li><strong>animations.zip</strong><span>동작별 스트립·그리드 PNG, GIF, 무손실 WebP · 같은 최종 프레임 사용</span></li><li><strong>animation-manifest.json</strong><span>동작별 파일·시간·검증 결과 · 지원하지 않는 형식은 제외 이유 표시</span></li><li><strong>aseprite.json</strong><span>Aseprite 호환 정보 · runtime 동반</span></li><li><strong>bundle.zip</strong><span>게임용 산출물 전체 묶음 · 애니메이션 ZIP 포함</span></li></ul>
     <p className="caption">GIF는 최대 255색·이진 투명도·10ms 단위를 사용합니다. 10ms 미만 프레임이 있는 동작은 GIF에서 제외합니다. 색상·반투명도·정확한 시간이 필요하면 PNG/runtime 또는 무손실 WebP를 사용하세요.</p>
    </details>
    <p className="caption">테두리: {p.outline.enabled?(p.outline.mode==='bake'?'파일에 포함':'미리보기만 표시'):'사용 안 함'} · 저장 버전 {p.revision}</p>
   </section>
   {mode==='export'&&<section id={`${viewId}-history`} className="export-history panel" role="tabpanel" aria-labelledby={`${viewId}-history-tab`} aria-label="이전 출력과 다운로드" tabIndex={0} hidden={sidebarView!=='history'}>
    <div className="panel-heading"><h2>출력 이력 · 최신순</h2><span className="badge">{s.exports.length}건</span></div>
    <p className="caption">저장 버전은 편집 데이터의 버전입니다. 같은 버전을 여러 번 출력할 수 있습니다. 시간은 현재 브라우저의 시간대로 표시합니다.</p>
    <div className="export-history-list" tabIndex={0} aria-label="출력 이력 목록">
     {exportHistory.map((e,index)=>{const Record=index===0?'article':'details',Heading=index===0?'div':'summary',recordTime=e.completedAt||e.createdAt;return <Record className={`list-card ${current?.runtime.exportId===e.exportId?'export-current':''}`} key={e.exportId}>
      <Heading className="export-record-heading"><span className="row"><strong>출력 {short(e.exportId)}</strong><span className="badge">{statuses[e.status]||e.status}</span>{e.exportId===latest?.exportId&&(e.completedAt||e.createdAt)&&<span className="badge success">최신 출력</span>}<span>저장 버전 {e.projectRevision??e.manifest?.projectRevision}</span>{(e.projectRevision??e.manifest?.projectRevision)!==p.revision&&<span className="badge warn">현재 편집과 다른 버전</span>}</span>{index>0&&<span className="export-record-time">{recordTime?<>{e.completedAt?'완료':'요청'} <time dateTime={recordTime} title={recordTime}>{date(recordTime)}</time></>:'출력 시각 기록 없음'}</span>}</Heading>
      <p className="export-timestamps">{e.completedAt&&<span>완료 <time dateTime={e.completedAt} title={`출력 완료 기록 · ${e.completedAt}`}>{date(e.completedAt)}</time></span>}{e.createdAt&&<span>요청 <time dateTime={e.createdAt} title={e.createdAt}>{date(e.createdAt)}</time></span>}{!e.completedAt&&!e.createdAt&&<span>출력 시각 기록 없음</span>}</p>
      {outputFolder&&e.jobId&&<details className="export-record-location"><summary>출력 저장 위치</summary><p className="mono">{[outputFolder,e.jobId,e.attemptId].filter(Boolean).join(separator)}</p></details>}
      <ExportFailure record={e} s={s}/>
      {!!e.files?.length&&<div className="row"><button aria-pressed={current?.runtime.exportId===e.exportId} onClick={()=>show(e.manifest,e.files||[])}>최종 결과 보기</button>{e.files.map(f=><a key={f.artifactId} className="button" href={f.url} download={f.name}>{f.name==='bundle.zip'?'전체 파일 ZIP 다운로드':`${f.name} ↓`}</a>)}</div>}
     </Record>;})}
     {!s.exports.length&&<Empty title="아직 내보낸 결과가 없습니다"/>}
    </div>
   </section>}
  </aside>
 </div>;
}
export function HistoryStep({s}:{s:Studio}){const p=s.snapshot!,[restoreRevision,setRestore]=useState<number|null>(null),[duplicateName,setName]=useState(`${p.name} 사본`);return <div className="two-columns"><Panel title="저장 이력" eyebrow="VERSION HISTORY"><p className="muted">과거 상태로 돌아가도 원본과 이전 출력은 삭제되지 않습니다. 새 저장 버전이 만들어집니다.</p>{s.revisions.slice().reverse().map(r=><article className="revision" key={r.revision}><div><strong>버전 {r.revision}</strong><p>{r.reason}</p><small>{date(r.createdAt)}</small></div><button disabled={r.revision===p.revision||s.busy||!!s.commands.length} onClick={()=>setRestore(r.revision)}>이 버전 복원</button></article>)}{restoreRevision!==null&&<div className="warning" role="alert"><p>버전 {restoreRevision} 상태를 새 버전으로 복원합니다.</p><div className="row"><button onClick={()=>setRestore(null)}>취소</button><button onClick={async()=>{await s.mutation(`/projects/${p.projectId}/restore-revision`,{expectedRevision:p.revision,targetRevision:restoreRevision});setRestore(null);}}>복원 실행</button></div></div>}</Panel><div><Panel title="프로젝트 백업"><p>원본·정렬·순서·시간·생성 이력을 한 파일로 보관합니다.</p><button className="primary" disabled={s.busy||!!s.commands.length} onClick={()=>s.mutation(`/projects/${p.projectId}/backup`,{savedRevision:p.revision})}>백업 파일 만들기</button>{s.jobs.filter(j=>j.operation==='backup').slice(-1).map(j=><JobCard key={j.jobId} job={j} s={s}/>)}</Panel><Panel title="프로젝트 복제"><Input label="사본 이름" value={duplicateName} onChange={e=>setName(e.target.value)}/><button disabled={s.busy||!!s.commands.length||!duplicateName.trim()} onClick={()=>s.mutation(`/projects/${p.projectId}/duplicate`,{expectedRevision:p.revision,name:duplicateName})}>새 프로젝트로 복제</button></Panel><Panel title="초안 보관"><p className="muted">다른 창의 변경과 비교하거나 문제를 해결할 때 로컬 초안을 파일로 보관할 수 있습니다.</p><button onClick={()=>downloadJson(`${p.name}-draft.json`,{base:s.base,commands:s.commands})}>현재 초안 다운로드</button></Panel><Panel title="생성 이력">{p.generations.length?<pre>{JSON.stringify(p.generations,null,2)}</pre>:<p className="muted">실제 생성 이력이 없습니다. 가져온 이미지는 자료 목록에서 확인하세요.</p>}</Panel></div></div>}
