import {useState,useEffect,useRef,useId} from 'react';
import {api,downloadJson} from './api';
import {isVideoJob,videoJobStep,videoRetryLabel} from './videoWorkflow';
import {VideoDiagnostics} from './VideoDiagnostics';
import type {Studio} from './useStudio';
import {exportGates} from './draft';
import {InspectionPanel} from './WorkflowPanel';
import {approvalLabel,type WorkTarget} from './workflow';
import {RuntimePlayer} from './Canvas';
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
export function ReviewStep({s,clipId,onNavigate}:{s:Studio;clipId?:string;onNavigate?:(target:WorkTarget)=>void}){const p=s.snapshot!,[checks,setChecks]=useState<Record<string,boolean>>({});const outline=p.outline;const setOutline=(change:Record<string,unknown>)=>s.edit({type:'setOutline',outline:{...outline,...change}});const hex='#'+outline.colorRGBA.slice(0,3).map(x=>x.toString(16).padStart(2,'0')).join('');
 return <div className="two-columns"><Panel title="동작 수동 승인" eyebrow="07 / REVIEW"><p className="muted">후보·앵커·테두리 변경을 먼저 저장하세요. 아래 체크리스트는 직접 확인하는 항목이며 자동 검사 결과와 별개입니다.</p>{p.clips.filter(c=>!clipId||c.clipId===clipId).map(c=><article className="list-card" key={c.clipId}><div className="row"><h3>{c.name}</h3><span className={`badge ${c.review==='approved'?'success':'warn'}`}>{approvalLabel(c.review,c.reviewInvalidatedReason)}</span></div>{c.reviewInvalidatedReason&&<p className="approval-recheck">{c.reviewInvalidatedReason}</p>}<p className="caption">{c.occurrences.length} 슬롯 · {c.occurrences.reduce((n,o)=>n+o.durationMs,0)}ms · 기준 {short(c.referenceRevisionId)}</p>{['외형·의상·장비·방향','알파·추출 완전성','공통 배율·앵커·공중 궤적','테두리 OFF·셀 경계','순서·표시 시간·반복'].map(label=><Check key={label} label={label} checked={checks[`${p.revision}-${c.clipRevisionId}-${label}`]||false} onChange={v=>setChecks(vs=>({...vs,[`${p.revision}-${c.clipRevisionId}-${label}`]:v}))}/>)}<button className="primary" disabled={!c.occurrences.length||s.busy||!!s.commands.length||!!s.conflict||!!exportGates({...p,clips:p.clips.map(item=>item.clipId===c.clipId?{...item,review:'approved'}:item)},[c.clipId],false).length||!['외형·의상·장비·방향','알파·추출 완전성','공통 배율·앵커·공중 궤적','테두리 OFF·셀 경계','순서·표시 시간·반복'].every(l=>checks[`${p.revision}-${c.clipRevisionId}-${l}`])} onClick={()=>s.edit({type:'updateClip',clipId:c.clipId,changes:{review:'approved'}})}>동작 수동 승인 · 초안에 적용</button><p className="caption">기준·후보·앵커 승인을 마치고 저장하면 동작을 승인할 수 있습니다.</p><InspectionPanel s={s} clip={c} onNavigate={onNavigate}/></article>)}{!p.clips.length&&<Empty title="검수할 동작이 없습니다"/>}</Panel><Panel title="팀 테두리"><Check label="테두리 사용" checked={outline.enabled} onChange={enabled=>setOutline({enabled})}/><Input label="팀 이름" value={outline.teamLabel} onChange={e=>setOutline({teamLabel:e.target.value})}/><Input label="테두리 색" type="color" value={hex} onChange={e=>setOutline({colorRGBA:[parseInt(e.target.value.slice(1,3),16),parseInt(e.target.value.slice(3,5),16),parseInt(e.target.value.slice(5,7),16),outline.colorRGBA[3]]})}/><span className="mono">{hex.toUpperCase()}</span><Num label="두께 (셀 픽셀)" value={outline.thicknessPx} onChange={thicknessPx=>setOutline({thicknessPx})} min={1} max={16}/><Num label="복제당 불투명도" value={outline.opacityPerCopy} step={.05} min={0} max={1} onChange={opacityPerCopy=>setOutline({opacityPerCopy})}/><Select label="방향" value={outline.directions} onChange={e=>setOutline({directions:+e.target.value})}><option value={4}>4방향</option><option value={8}>8방향</option></Select><Select label="포함 범위" value={outline.mode} onChange={e=>setOutline({mode:e.target.value})}><option value="preview-only">편집 미리보기 전용</option><option value="bake">출력 파일에 포함</option></Select><div className="callout"><strong>테두리 없이도 확인하세요</strong><p>테두리를 끄더라도 알파 잔여물과 잘림 경고는 사라지지 않습니다. 파일 포함 모드는 최종 경계 검수를 다시 요구합니다.</p></div></Panel></div>
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
export function ExportStep({s}:{s:Studio}){
 const p=s.snapshot!;
 const [selected,setSelected]=useState<string[]>(p.clips.map(c=>c.clipId));
 // undefined follows the latest successful export; null keeps an explicit close.
 const [preview,setPreview]=useState<{runtime:Runtime;url:string;projectId:string}|null|undefined>(undefined);
 const [view,setView]=useState<'preview'|'settings'>('preview');
 const request=useRef(0),viewId=useId();
 const gates=exportGates(p,selected,!!s.commands.length||!!s.conflict);
 const clipRevisionIds=p.clips.filter(c=>selected.includes(c.clipId)).map(c=>c.clipRevisionId);
 const bake=s.jobs.filter(j=>j.operation==='bake'&&j.artifacts?.length).at(-1);
 const latest=s.exports.slice().reverse().find(e=>['succeeded','completed'].includes(e.status)&&e.manifest&&e.files?.some(f=>f.name==='atlas.png'));
 const latestAtlas=latest?.files?.find(f=>f.name==='atlas.png');
 const automatic=latest?.manifest&&latestAtlas?{runtime:latest.manifest,url:latestAtlas.url,projectId:p.projectId}:null;
 const current=preview===undefined?automatic:preview?.projectId===p.projectId?preview:null;
 useEffect(()=>{
  setSelected(p.clips.map(c=>c.clipId));setPreview(undefined);setView('preview');
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
 return <div className="export-workspace" data-view={view}>
  <div className="export-view-switch" role="group" aria-label="출력 작업 보기">
   <button aria-pressed={view==='preview'} aria-controls={`${viewId}-preview`} onClick={()=>setView('preview')}>출력 결과</button>
   <button aria-pressed={view==='settings'} aria-controls={`${viewId}-settings`} onClick={()=>setView('settings')}>설정·다운로드</button>
  </div>
  <section id={`${viewId}-preview`} className="export-preview panel" aria-label="출력 결과 미리보기">
   <div className="export-preview-heading">
    <div><h2>출력 결과</h2><p className="caption">{current?`출력 ${short(current.runtime.exportId)} · 저장 버전 ${current.runtime.projectRevision}`:'최근 성공한 출력이 여기에 표시됩니다.'}</p></div>
    <div className="row">
     {latest&&<button onClick={()=>{request.current++;setPreview(undefined);setView('preview');}}>최근 성공 출력</button>}
     {current&&<button onClick={closePreview}>닫기</button>}
    </div>
   </div>
   {current&&(current.runtime.projectRevision!==p.revision||!!s.commands.length)&&<p className="export-preview-version badge warn">현재 편집과 다른 버전 · 저장된 이전 결과를 표시합니다.</p>}
   {current?<RuntimePlayer runtime={current.runtime} atlasUrl={current.url} initialZoom="fit"/>:<div className="export-preview-empty"><Empty title="표시할 출력 결과를 선택해 주세요"><p>미리보기나 게임용 파일을 만든 뒤 이곳에서 재생할 수 있습니다. 이전 출력도 다시 열 수 있습니다.</p><button onClick={()=>setView('settings')}>출력 설정 열기</button></Empty></div>}
  </section>
  <aside id={`${viewId}-settings`} className="export-sidebar" aria-label="출력 설정과 다운로드">
   <section className="export-settings panel" aria-label="출력 설정">
    <div className="panel-heading"><h2>출력 설정</h2></div>
    <p className="muted">저장된 버전으로 미리보기와 게임용 파일을 만듭니다.</p>
    <div className="export-clip-selection" role="group" aria-label="출력할 동작">{p.clips.map(c=><Check key={c.clipId} label={`${c.name} · ${c.occurrences.length} 슬롯`} checked={selected.includes(c.clipId)} onChange={v=>setSelected(v?[...selected,c.clipId]:selected.filter(id=>id!==c.clipId))}/>)}</div>
    <div className="export-actions row">
     <button disabled={s.busy||!!s.commands.length||!selected.length||s.service?.worker!=='ready'} onClick={()=>s.job('bake',[],{clipIds:selected,clipRevisionIds})}>확정 미리보기 만들기</button>
     <button className="primary" disabled={s.busy||!!gates.length||s.service?.worker!=='ready'} onClick={()=>s.mutation(`/projects/${p.projectId}/exports`,{savedRevision:p.revision,clipRevisionIds,formats:['atlas','pngs','runtime','aseprite'],outlineMode:p.outline.mode,idempotencyKey:uid()})}>게임용 파일 출력</button>
    </div>
    {gates.length?<ul className="gate-list">{gates.map(g=><li key={g}>{g}</li>)}</ul>:<p className="success-text">수동 승인·저장 조건 충족. 출력 시 서버가 픽셀·경계·파일을 검사합니다.</p>}
    {bake&&<button onClick={()=>show(bake.result?.manifest,bake.artifacts||[])}>최근 미리보기 보기 · 버전 {bake.inputRevision}</button>}
    <details className="export-format-help"><summary>출력 파일 안내</summary>
     <ul className="deliverables"><li><strong>atlas.png + runtime.json</strong><span>프레임 영역, 순서, 가변 시간, 앵커, 반복</span></li><li><strong>pngs.zip</strong><span>순서별 PNG · 같은 아틀라스에서 추출</span></li><li><strong>animations.zip</strong><span>동작별 스트립·그리드 PNG, GIF, 무손실 WebP · 같은 최종 프레임 사용</span></li><li><strong>animation-manifest.json</strong><span>동작별 파일·시간·검증 결과 · 지원하지 않는 형식은 제외 이유 표시</span></li><li><strong>aseprite.json</strong><span>Aseprite 호환 정보 · runtime 동반</span></li><li><strong>bundle.zip</strong><span>게임용 산출물 전체 묶음 · 애니메이션 ZIP 포함</span></li></ul>
     <p className="caption">GIF는 최대 255색·이진 투명도·10ms 단위를 사용합니다. 10ms 미만 프레임이 있는 동작은 GIF에서 제외합니다. 색상·반투명도·정확한 시간이 필요하면 PNG/runtime 또는 무손실 WebP를 사용하세요.</p>
    </details>
    <p className="caption">테두리: {p.outline.enabled?(p.outline.mode==='bake'?'파일에 포함':'미리보기만 표시'):'사용 안 함'} · 저장 버전 {p.revision}</p>
   </section>
   <section className="export-history panel" aria-label="이전 출력과 다운로드">
    <div className="panel-heading"><h2>이전 출력과 다운로드</h2><span className="badge">{s.exports.length}건</span></div>
    <div className="export-history-list" tabIndex={0} aria-label="출력 이력 목록">
     {s.exports.slice().reverse().map(e=><article className={`list-card ${current?.runtime.exportId===e.exportId?'export-current':''}`} key={e.exportId}>
      <div className="row"><strong>출력 {short(e.exportId)}</strong><span className="badge">{statuses[e.status]||e.status}</span><span>저장 버전 {e.projectRevision??e.manifest?.projectRevision}</span>{(e.projectRevision??e.manifest?.projectRevision)!==p.revision&&<span className="badge warn">현재 편집과 다른 버전</span>}</div>
      <ExportFailure record={e} s={s}/>
      {!!e.files?.length&&<div className="row"><button aria-pressed={current?.runtime.exportId===e.exportId} onClick={()=>show(e.manifest,e.files||[])}>최종 결과 보기</button>{e.files.map(f=><a key={f.artifactId} className="button" href={f.url} download={f.name}>{f.name} ↓</a>)}</div>}
     </article>)}
     {!s.exports.length&&<Empty title="아직 내보낸 결과가 없습니다"/>}
    </div>
   </section>
  </aside>
 </div>;
}
export function HistoryStep({s}:{s:Studio}){const p=s.snapshot!,[restoreRevision,setRestore]=useState<number|null>(null),[duplicateName,setName]=useState(`${p.name} 사본`);return <div className="two-columns"><Panel title="저장 이력" eyebrow="VERSION HISTORY"><p className="muted">과거 상태로 돌아가도 원본과 이전 출력은 삭제되지 않습니다. 새 저장 버전이 만들어집니다.</p>{s.revisions.slice().reverse().map(r=><article className="revision" key={r.revision}><div><strong>버전 {r.revision}</strong><p>{r.reason}</p><small>{date(r.createdAt)}</small></div><button disabled={r.revision===p.revision||s.busy||!!s.commands.length} onClick={()=>setRestore(r.revision)}>이 버전 복원</button></article>)}{restoreRevision!==null&&<div className="warning" role="alert"><p>버전 {restoreRevision} 상태를 새 버전으로 복원합니다.</p><div className="row"><button onClick={()=>setRestore(null)}>취소</button><button onClick={async()=>{await s.mutation(`/projects/${p.projectId}/restore-revision`,{expectedRevision:p.revision,targetRevision:restoreRevision});setRestore(null);}}>복원 실행</button></div></div>}</Panel><div><Panel title="프로젝트 백업"><p>원본·정렬·순서·시간·생성 이력을 한 파일로 보관합니다.</p><button className="primary" disabled={s.busy||!!s.commands.length} onClick={()=>s.mutation(`/projects/${p.projectId}/backup`,{savedRevision:p.revision})}>백업 파일 만들기</button>{s.jobs.filter(j=>j.operation==='backup').slice(-1).map(j=><JobCard key={j.jobId} job={j} s={s}/>)}</Panel><Panel title="프로젝트 복제"><Input label="사본 이름" value={duplicateName} onChange={e=>setName(e.target.value)}/><button disabled={s.busy||!!s.commands.length||!duplicateName.trim()} onClick={()=>s.mutation(`/projects/${p.projectId}/duplicate`,{expectedRevision:p.revision,name:duplicateName})}>새 프로젝트로 복제</button></Panel><Panel title="초안 보관"><p className="muted">다른 창의 변경과 비교하거나 문제를 해결할 때 로컬 초안을 파일로 보관할 수 있습니다.</p><button onClick={()=>downloadJson(`${p.name}-draft.json`,{base:s.base,commands:s.commands})}>현재 초안 다운로드</button></Panel><Panel title="생성 이력">{p.generations.length?<pre>{JSON.stringify(p.generations,null,2)}</pre>:<p className="muted">실제 생성 이력이 없습니다. 가져온 이미지는 자료 목록에서 확인하세요.</p>}</Panel></div></div>}
