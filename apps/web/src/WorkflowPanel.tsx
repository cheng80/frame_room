import type {Studio} from './useStudio';
import type {Clip} from './types';
import {inspectionState,nextWork,type WorkTarget} from './workflow';
import './workflow.css';

export function InspectionPanel({s,clip,onNavigate}:{s:Studio;clip?:Clip;onNavigate?:(target:WorkTarget)=>void}){
 const p=s.snapshot!,report=inspectionState(p,s.jobs,!!s.commands.length||!!s.conflict,clip?.clipId);
 const unavailable=s.busy||!!s.commands.length||!!s.conflict||!clip?.occurrences.length||s.service?.worker!=='ready'||report.state==='running';
 return <section className="workflow-inspection" aria-label="자동 검사 결과">
  <h3>자동 검사</h3><p className="caption">픽셀·경계·구조 검사입니다. 외형과 동작의 예술적 품질, 수동 승인을 대신하지 않습니다.</p>
  <p role="status" className={`workflow-status ${report.state==='current'&&!report.issues.length?'success-text':''}`}>{report.label}</p>
  {report.job&&<small>검사 입력 v{report.job.inputRevision} · 현재 저장 v{p.revision}{s.commands.length?' + 미저장 초안':''}</small>}
  <button disabled={unavailable} onClick={()=>clip&&s.job('inspect',[],{clipIds:[clip.clipId]})}>선택 동작 자동 검사 실행</button>
  {!!s.commands.length&&<p className="caption">초안을 먼저 저장하세요.</p>}
  {report.stale&&<p className="caption">아래는 과거 보고서입니다. 현재 편집 결과의 통과로 볼 수 없습니다.</p>}
  {report.issues.length>0&&<ul className="inspection-issues">{report.issues.map(issue=>{
   const c=p.clips.find(c=>c.clipId===issue.clipId),slot=c?.occurrences.findIndex(o=>o.occurrenceId===issue.occurrenceId)??-1;
   const candidate=p.frames.findIndex(f=>f.frameVersionId===issue.frameVersionId);
   const targetExists=(!issue.clipId||!!c)&&(!issue.occurrenceId||slot>=0)&&(!issue.frameVersionId||candidate>=0);
   return <li key={issue.key}><strong>{issue.severity==='error'?'검사 오류':issue.severity==='warning'?'검사 경고':'수동 승인 조건'}</strong><p>{issue.message}</p><small>{c?.name}{slot>=0?` · 슬롯 ${slot+1}`:''}{candidate>=0?` · 후보 ${candidate+1}`:''}</small>{issue.location&&<small>{issue.location}</small>}{onNavigate&&<button disabled={!targetExists} onClick={()=>onNavigate(issue.target)}>{targetExists?'해당 프레임·도구로 이동':'현재 편집에서 찾을 수 없음'}</button>}<details><summary>검사 코드</summary><code>{issue.code}</code></details></li>;
  })}</ul>}
 </section>;
}

export function NextWorkPanel({s,clip,onNavigate}:{s:Studio;clip?:Clip;onNavigate:(target:WorkTarget)=>void}){
 const items=nextWork(s.snapshot!,clip,!!s.commands.length,s.jobs,!!s.conflict);
 return <section className="next-work-panel" aria-label="다음 작업 안내"><h3>{clip?`${clip.name} · 다음 작업`:'프로젝트 · 다음 작업'}</h3><p className="caption">현재 선택한 동작과 저장 상태를 기준으로 안내합니다.</p><ol className="next-work-list">{items.map(item=><li key={item.id}><button disabled={s.busy} onClick={()=>onNavigate(item)}>{item.label}</button><small>{item.detail}</small></li>)}</ol><InspectionPanel s={s} clip={clip} onNavigate={onNavigate}/></section>;
}
