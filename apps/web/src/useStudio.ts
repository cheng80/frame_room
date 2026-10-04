import {useState,useRef,useEffect,useMemo} from 'react';
import {api,health,ApiError} from './api';
import {applyDraft,remapCommand} from './draft';
import {uid,type Snapshot,type MissingProjectFolder,type DraftCommand,type Operation,type Health,type Job,type Provider,type ExportRecord} from './types';
export function useStudio(standalone=false){
 const [service,setService]=useState<Health|null>(null),[projects,setProjects]=useState<Snapshot[]>([]),[base,setBase]=useState<Snapshot|null>(null),[commands,setCommands]=useState<DraftCommand[]>([]),[redoCommands,setRedo]=useState<DraftCommand[]>([]),[resolvedIds,setResolvedIds]=useState<Record<string,string>>({}),[busy,setBusyState]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[conflict,setConflict]=useState<Snapshot|null>(null),[jobs,setJobs]=useState<Job[]>([]),[providers,setProviders]=useState<Provider[]>([]),[exports,setExports]=useState<ExportRecord[]>([]),[revisions,setRevisions]=useState<{revision:number;createdAt:string;reason:string}[]>([]);
 const ref=useRef({base,commands,busy});ref.current={base,commands,busy};const jobStates=useRef('');const detailsEpoch=useRef(0);const projectsEpoch=useRef(0);const deletedProjects=useRef(new Set<string>());
 function setBusy(value:boolean){ref.current.busy=value;setBusyState(value);}
 const snapshot=useMemo(()=>base?applyDraft(base,commands):null,[base,commands]);
 function report(e:unknown){setError(e instanceof Error?e.message:'작업을 완료하지 못했습니다.');}
 async function refreshProjects(){const epoch=++projectsEpoch.current;const r=await api<{projects:Snapshot[]}>('/projects');if(epoch===projectsEpoch.current)setProjects(r.projects.filter(p=>!deletedProjects.current.has(p.projectId)));}
 async function connect(){try{setService(await health());await refreshProjects();const p=await api<{providers:Provider[]}>('/providers');setProviders(p.providers);}catch(e){setService(null);report(e);}}
 useEffect(()=>{if(!standalone)void connect();},[standalone]);
 useEffect(()=>{if(!base)return;try{const key=`frame-room-draft:${base.projectId}`;if(commands.length)localStorage.setItem(key,JSON.stringify({base,commands}));else localStorage.removeItem(key);}catch{setError('브라우저 초안 보관 공간이 부족합니다. 저장하거나 초안을 다운로드해 주세요.');}},[base,commands]);
 useEffect(()=>{const leave=(e:BeforeUnloadEvent)=>{if(ref.current.commands.length){e.preventDefault();}};window.addEventListener('beforeunload',leave);return()=>window.removeEventListener('beforeunload',leave);},[]);
 async function activateProject(server:Snapshot){
  const id=server.projectId;let cached:null|{base:Snapshot;commands:DraftCommand[]}=null;
  try{cached=JSON.parse(localStorage.getItem(`frame-room-draft:${id}`)||'null');}catch{}
  deletedProjects.current.delete(id);projectsEpoch.current++;
  setProjects(items=>items.some(p=>p.projectId===id)?items.map(p=>p.projectId===id?server:p):[server,...items]);
  const nextBase=cached?.commands.length?{...cached.base,storage:server.storage}:server,nextCommands=cached?.commands||[];
  ref.current.base=nextBase;ref.current.commands=nextCommands;
  setBase(nextBase);setCommands(nextCommands);setRedo([]);setResolvedIds({});
  setConflict(cached?.commands.length&&cached.base.revision!==server.revision?server:null);
  setNotice(cached?.commands.length?'이 브라우저에 보관된 편집 초안을 복구했습니다.':'프로젝트 폴더를 열었습니다.');
  setJobs([]);setExports([]);setRevisions([]);jobStates.current='';await refreshDetails(id);
 }
 async function load(id:string){if(ref.current.busy)return false;detailsEpoch.current++;setBusy(true);setError('');try{await activateProject(await api<Snapshot>(`/projects/${id}`));return true;}catch(e){report(e);return false;}finally{setBusy(false);}}
 async function refreshDetails(id:string){const epoch=detailsEpoch.current;const results=await Promise.allSettled([api<{jobs:Job[]}>(`/projects/${id}/jobs`),api<{exports:ExportRecord[]}>(`/projects/${id}/exports`),api<{revisions:{revision:number;createdAt:string;reason:string}[]}>(`/projects/${id}/revisions`)]);if(epoch!==detailsEpoch.current||deletedProjects.current.has(id))return;if(results[0].status==='fulfilled')setJobs(results[0].value.jobs);if(results[1].status==='fulfilled')setExports(results[1].value.exports);if(results[2].status==='fulfilled')setRevisions(results[2].value.revisions);}
 useEffect(()=>{if(!base||standalone)return;const id=base.projectId;let cancelled=false;let polling=false;const poll=async()=>{if(polling||document.hidden)return;polling=true;try{const [j,h]=await Promise.all([api<{jobs:Job[]}>(`/projects/${id}/jobs`),health()]);if(cancelled||ref.current.base?.projectId!==id)return;setService(h);setJobs(j.jobs);const state=j.jobs.map(j=>`${j.jobId}:${j.status}:${j.step}`).join('|');if(state!==jobStates.current){jobStates.current=state;await refreshDetails(id);const server=await api<Snapshot>(`/projects/${id}`);if(!cancelled&&ref.current.base?.projectId===id&&!ref.current.busy){if(!ref.current.commands.length)setBase(server);else if(server.revision!==ref.current.base.revision)setConflict(server);}}}catch{if(!cancelled&&ref.current.base?.projectId===id)setService(null);}finally{polling=false;}};const timer=setInterval(poll,2200);return()=>{cancelled=true;clearInterval(timer);};},[base?.projectId,standalone]);
 function edit(operation:Operation){if(ref.current.busy||!ref.current.base)return;const localId=['createClip','addOccurrence','duplicateOccurrence'].includes(operation.type)?`draft-${uid()}`:undefined;setCommands(c=>[...c,{operation,localId}]);setRedo([]);setNotice('');return localId;}
 function undo(){if(busy||!commands.length)return;setRedo(r=>[commands[commands.length-1],...r]);setCommands(c=>c.slice(0,-1));}
 function redo(){if(busy||!redoCommands.length)return;setCommands(c=>[...c,redoCommands[0]]);setRedo(r=>r.slice(1));}
 async function save(){const current=ref.current;if(!current.base||current.busy)return false;if(!current.commands.length)return true;if(conflict){setError('다른 저장 버전과 비교한 뒤 초안을 다시 적용해 주세요.');return false;}setBusy(true);setError('');setNotice('');let server=current.base;let pending=[...current.commands];const ids:Record<string,string>={};
 try{while(pending.length){const command=remapCommand(pending[0],ids);const before=server;const ack=await api<{savedRevision:number;snapshot?:Snapshot}>(`/projects/${server.projectId}/edits`,'PATCH',{expectedRevision:server.revision,operations:[command.operation]});server=ack.snapshot||await api<Snapshot>(`/projects/${server.projectId}`);if(server.revision<ack.savedRevision)throw new Error('저장 ACK와 프로젝트 버전이 일치하지 않습니다.');if(command.localId){let actual:string|undefined;if(command.operation.type==='createClip')actual=server.clips.find(c=>!before.clips.some(b=>b.clipId===c.clipId))?.clipId;else{const c=server.clips.find(c=>c.clipId===command.operation.clipId);const old=before.clips.find(c=>c.clipId===command.operation.clipId)?.occurrences||[];actual=c?.occurrences.find(o=>!old.some(b=>b.occurrenceId===o.occurrenceId))?.occurrenceId;}if(actual){ids[command.localId]=actual;const local=command.localId;setResolvedIds(previous=>({...previous,[local]:actual}));}}pending=pending.slice(1).map(c=>remapCommand(c,ids));setBase(server);setCommands(pending);}
 setRedo([]);setNotice(`저장됨 · 버전 ${server.revision}`);await refreshDetails(server.projectId);return true;
 }catch(e){
  if(e instanceof ApiError&&e.status===503){
   try{
    // A durable app-index write may precede a failed folder flush. This is not a save ACK.
    const latest=await api<Snapshot>(`/projects/${server.projectId}`);
    if(latest.storage){
     server={...server,storage:latest.storage};projectsEpoch.current++;
     setProjects(items=>items.map(p=>p.projectId===server.projectId?{...p,storage:latest.storage}:p));
     if(latest.storage.syncPending)setNotice('폴더 저장 보류 · 폴더 위치·권한·여유 공간을 확인해 주세요.');
    }
   }catch{}
  }
  setBase(server);setCommands(pending);
  if(e instanceof ApiError&&e.status===409){try{setConflict(await api<Snapshot>(`/projects/${server.projectId}`));}catch{}}
  report(e);return false;
 }finally{setBusy(false);}}
 async function reapply(){if(!conflict)return;setBase(conflict);setConflict(null);setError('');setNotice('최신 버전에 초안을 다시 적용했습니다. 내용을 확인한 뒤 저장해 주세요.');}
 async function run<T>(fn:()=>Promise<T>,message?:string){if(ref.current.busy)return;setBusy(true);setError('');try{const v=await fn();if(message)setNotice(message);return v;}catch(e){report(e);}finally{setBusy(false);}}
 async function mutation(path:string,body:unknown){if(commands.length){setError('먼저 편집 초안을 저장해 주세요.');return;}return run(async()=>{const r=await api<any>(path,'POST',body);if(base){setBase(await api<Snapshot>(`/projects/${base.projectId}`));await refreshDetails(base.projectId);}await refreshProjects();return r;},'요청을 접수했습니다.');}
 async function pickProjectFolder(purpose:'open'|'parent'){
  return run(async()=>{const result=await api<{path:string|null}>('/project-folders/pick','POST',{purpose});return result.path;});
 }
 async function openProjectFolder(path:string){
  if(!path.trim()){setError('프로젝트 폴더 경로를 입력해 주세요.');return;}
  return run(async()=>{
   const project=await api<Snapshot>('/project-folders/open','POST',{path:path.trim()});
   detailsEpoch.current++;await activateProject(project);return project;
  });
 }
 async function revealProject(project:Snapshot){
  return run(async()=>{
   const result=await api<{projectId:string;path:string;fileManager:'finder'|'explorer';storageLayout:'project-folder'}>(`/projects/${project.projectId}/reveal`,'POST',{});
   setNotice(`${result.fileManager==='finder'?'Finder':'탐색기'}에 프로젝트 폴더를 열었습니다. ${result.path}`);
   return result;
  });
 }
 function forgetProjects(ids:string[]){
  if(!ids.length)return;
  projectsEpoch.current++;const removed=new Set(ids);ids.forEach(id=>deletedProjects.current.add(id));
  setProjects(items=>items.filter(p=>!removed.has(p.projectId)));
  if(ref.current.base&&removed.has(ref.current.base.projectId)){
   detailsEpoch.current++;ref.current.base=null;ref.current.commands=[];
   setBase(null);setCommands([]);setRedo([]);setResolvedIds({});setConflict(null);
   setJobs([]);setExports([]);setRevisions([]);jobStates.current='';
  }
  let failed=false;for(const id of ids){try{localStorage.removeItem(`frame-room-draft:${id}`);}catch{failed=true;}}
  if(failed)setError('목록에서는 제거했지만 이 브라우저에 보관된 일부 초안을 지우지 못했습니다.');
 }
 async function missingProjectFolders(){
  return run(async()=>{const result=await api<{projects:MissingProjectFolder[]}>('/project-folders/missing');return result.projects;});
 }
 async function cleanupMissingFolders(projects:MissingProjectFolder[]){
  if(!projects.length){setNotice('정리할 없는 폴더가 없습니다.');return;}
  return run(async()=>{
   const result=await api<{removedProjectIds:string[];removedCount:number}>('/project-folders/cleanup','POST',{
    projects:projects.map(p=>({projectId:p.projectId,expectedRevision:p.revision,path:p.path})),
   });
   forgetProjects(result.removedProjectIds);
   setNotice(`없는 프로젝트 폴더 ${result.removedCount}개의 목록 등록을 정리했습니다. 실제 파일은 변경하지 않았습니다.`);
   await refreshProjects().catch(report);return result;
  });
 }
 async function deleteProject(project:Snapshot){
  return run(async()=>{
   try{await api(`/projects/${project.projectId}`,'DELETE',{expectedRevision:project.revision});}
   catch(e){
    // Another window may already have detached it. Clear only this project's local state.
    if(!(e instanceof ApiError&&e.status===404&&e.code==='PROJECT_NOT_FOUND')){
     if(e instanceof ApiError&&e.status===409){
      await refreshProjects().catch(()=>{});
      if(e.code==='REVISION_CONFLICT')throw new Error('프로젝트가 변경되어 목록에서 제거하지 않았습니다. 다시 확인한 뒤 제거해 주세요.');
     }
     throw e;
    }
   }
   forgetProjects([project.projectId]);
   setNotice(`“${project.name}” 프로젝트를 목록에서 제거했습니다. 폴더의 데이터는 모두 유지됩니다.`);
   return true;
  });
 }
 async function job(operation:string,assetIds:string[]=[],params:Record<string,unknown>={}){if(!base)return;return mutation(`/projects/${base.projectId}/jobs`,{operation,inputRevision:base.revision,assetIds,params,idempotencyKey:uid()});}
 return {resolveId:(id:string)=>resolvedIds[id]||id,service,projects,base,snapshot,commands,redoCommands,busy,error,notice,conflict,jobs,providers,exports,revisions,edit,undo,redo,save,reapply,load,run,job,pickProjectFolder,openProjectFolder,missingProjectFolders,cleanupMissingFolders,revealProject,deleteProject,mutation,connect,refreshProjects,refreshDetails,report,setError,setNotice,setBase,setCommands,setConflict,setExports};
}
export type Studio=ReturnType<typeof useStudio>;
