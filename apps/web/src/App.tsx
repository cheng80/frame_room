import {useState,useEffect,useRef} from 'react';
import {BookOpen,Boxes,FolderOpen,ScanFace,Download,History,Activity,Undo2,Redo2,Save,ArrowLeft,Plus,ExternalLink,ChevronRight,Trash2} from 'lucide-react';
import {useStudio,type Studio} from './useStudio';
import {api,downloadJson} from './api';
import {uid,type Snapshot,type MissingProjectFolder,type Job,type Asset} from './types';
import {Panel,Input,Num,Empty,date} from './ui';
import {ImageGenerationStep} from './SourceSteps';
import {hasUnstoredReferenceInput} from './ReferenceStep';
import {AlignmentStep} from './EditSteps';
import {ProductionWorkflow} from './ProductionWorkflow';
import {JobsStep,HistoryStep,JobCard} from './FinishSteps';
import {FileViewer} from './Canvas';
import {SpriteImage} from './SpriteViewport';
import {EditorDialog} from './EditorDialog';
import {ProviderConnections} from './ProviderConnections';
import {projectCoverAsset} from './referenceLabel';
import './editor-shell.css';

const labels:Record<string,string>={generateAsset:'자료 이미지 생성',review:'동작 검수·팀 테두리',export:'게임용 파일 출력',jobs:'백그라운드 작업',history:'이력·백업',conflict:'저장 충돌 해결',create:'새 프로젝트',openFolder:'프로젝트 폴더 열기'};
function Feedback({s,details=false}:{s:Studio;details?:boolean}){const id=s.base?.projectId;return <>{s.error?<div className="shell-error" role="alert"><span>{s.error}</span><button onClick={()=>s.setError('')}>오류 닫기</button><button onClick={s.connect}>연결 확인</button></div>:null}{details&&id&&s.detailsError?<div className="shell-error" role="status"><span>{s.detailsError}</span><button onClick={()=>void s.refreshDetails(id)}>다시 조회</button></div>:null}</>;}
export function Conflict({s}:{s:Studio}){const [discard,setDiscard]=useState(false);return s.conflict?<section className="conflict"><h3>다른 창이나 완료된 작업이 저장한 변경이 있습니다</h3><p>내 기준 v{s.base?.revision} → 서버 v{s.conflict.revision}. 편집 초안 {s.commands.length}개는 보존되어 있습니다.</p><div className="two-columns"><div><h3>내 초안</h3><pre>{JSON.stringify(s.commands.map(c=>c.operation),null,2)}</pre></div><div><h3>서버 최신 이력</h3><pre>{JSON.stringify(s.conflict.journal.slice(-6),null,2)}</pre></div></div><div className="row"><button onClick={s.reapply}>최신 버전에 내 초안 다시 적용</button><button onClick={()=>downloadJson('frame-room-draft.json',{base:s.base,commands:s.commands})}>초안 파일로 보관</button><button onClick={()=>setDiscard(true)}>내 초안 버리고 서버 버전 열기</button></div>{discard&&<div className="warning" role="alert"><p>편집 초안 {s.commands.length}개를 이 브라우저에서 지우고 서버 v{s.conflict.revision}을 엽니다. 되돌릴 수 없습니다. 보관하려면 먼저 초안 파일로 보관한 뒤 파일이 저장됐는지 확인하세요.</p><div className="row"><button autoFocus onClick={()=>setDiscard(false)}>취소</button><button className="danger" onClick={()=>{s.setBase(s.conflict);s.setCommands([]);s.setConflict(null);setDiscard(false);}}>초안 버리고 서버 버전 열기</button></div></div>}</section>:<p>저장 충돌이 해결되었습니다. 편집 내용을 확인하고 저장하세요.</p>;}

export default function App(){
 const [page,setPage]=useState(location.hash==='#viewer'?'viewer':'projects');
 const s=useStudio(page==='viewer');const p=s.snapshot;
 const [clip,setClip]=useState(''),[activeTool,setActiveTool]=useState('assets'),[toolOpen,setToolOpen]=useState(false);
 const [workflowStep,setWorkflowStep]=useState(0),[sourceMode,setSourceMode]=useState<'generate'|'extract'>('generate');
 const [currentSelection,setCurrentSelection]=useState<{frameVersionId?:string;assetId?:string}>({});
 const [toolSelection,setToolSelection]=useState<{frameVersionId?:string;assetId?:string}>({});
 const [name,setName]=useState(''),[character,setCharacter]=useState(''),[width,setWidth]=useState(512),[height,setHeight]=useState(512),[restoreJob,setRestoreJob]=useState<Job|null>(null);
 const [deleteTarget,setDeleteTarget]=useState<Snapshot|null>(null);
 const [parentDirectory,setParentDirectory]=useState(''),[folderPath,setFolderPath]=useState('');
 const [missingFolders,setMissingFolders]=useState<MissingProjectFolder[]|null>(null);
 const [projectImage,setProjectImage]=useState<Asset|null>(null);
 const openedRoute=useRef('');
 const service=s.service?.api==='ready'?(s.service.worker==='ready'?'로컬 서비스 연결됨':'작업 처리기 연결 끊김'):'서버 연결 끊김';
 const fileManager=s.service?.desktop?.fileManager;
 const storageTitle=fileManager?`${fileManager==='finder'?'Finder':'탐색기'}에서 이 프로젝트 폴더 열기`:'폴더 위치 열기는 macOS와 Windows 로컬 서버에서 지원합니다.';
 const openTool=(id:string,selection?:{frameVersionId?:string;assetId?:string})=>{setToolSelection(selection||currentSelection);const steps:Record<string,number>={assets:0,reference:1,generate:2,extract:2,align:3,review:4,export:5};if(page==='editor'&&id in steps){setWorkflowStep(steps[id]);if(id==='generate'||id==='extract')setSourceMode(id);if(id!=='align'){setToolOpen(false);return;}}setActiveTool(id);setToolOpen(true);};
 const closeTool=()=>setToolOpen(false);
 const openVideoClip=(id:string)=>{setClip(id);setWorkflowStep(3);setToolOpen(false);};
 // Reference input that the browser could not keep would vanish when the editor unmounts.
 // The hashchange listener is registered once, so read the current page through a ref.
 const pageRef=useRef(page);pageRef.current=page;
 const leaveBlocked=()=>{if(pageRef.current!=='editor'||!hasUnstoredReferenceInput())return false;s.setError('보관하지 못한 기준 입력이 있습니다. 캐릭터 기준에서 새 기준 저장 또는 입력 버리기를 한 뒤 이동해 주세요.');return true;};
 const goProjects=()=>{if(leaveBlocked())return;setPage('projects');setToolOpen(false);history.replaceState(null,'',location.pathname);openedRoute.current='';void s.refreshProjects();};
 const showProject=(id:string)=>{setWorkflowStep(0);setSourceMode('generate');setClip('');setCurrentSelection({});setToolSelection({});setPage('editor');history.replaceState(null,'',`#project=${encodeURIComponent(id)}`);openedRoute.current=id;};
 const open=async(id:string)=>{if(leaveBlocked()||!await s.load(id))return false;showProject(id);return true;};
 useEffect(()=>{const id=new URLSearchParams(location.hash.slice(1)).get('project');if(id&&s.service&&openedRoute.current!==id){openedRoute.current=id;void open(id);}},[s.service]);
 useEffect(()=>{function hash(){const viewer=location.hash==='#viewer',id=new URLSearchParams(location.hash.slice(1)).get('project');if(!viewer&&(!id||openedRoute.current===id))return;
  // Keep the address on the project still shown when leaving is blocked; replaceState fires no hashchange.
  if(leaveBlocked()){history.replaceState(null,'',openedRoute.current?`#project=${encodeURIComponent(openedRoute.current)}`:location.pathname);return;}
  if(viewer){setPage('viewer');setToolOpen(false);}else void open(id!);}window.addEventListener('hashchange',hash);return()=>window.removeEventListener('hashchange',hash);},[]);
 useEffect(()=>{const key=(e:KeyboardEvent)=>{const target=e.target as HTMLElement;if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='s'){e.preventDefault();if(!e.repeat)saveShortcut(target);return;}if(['INPUT','TEXTAREA','SELECT'].includes(target.tagName)||target.isContentEditable)return;if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?s.redo():s.undo();}if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='y'){e.preventDefault();s.redo();}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[s.save,s.undo,s.redo]);
 useEffect(()=>{if(!restoreJob||['succeeded','failed','canceled'].includes(restoreJob.status))return;const id=setInterval(async()=>{try{const j=await api<Job>(`/jobs/${restoreJob.jobId}`);setRestoreJob(j);if(j.status==='succeeded')await s.refreshProjects();}catch(e){s.report(e);}},1500);return()=>clearInterval(id);},[restoreJob?.jobId,restoreJob?.status]);
 // Number and name fields commit on blur; apply the typed value before saving and keep focus in place.
 function saveShortcut(target:HTMLElement){
  if(!p)return;
  if(['INPUT','TEXTAREA','SELECT'].includes(target.tagName)){
   target.blur();target.focus();
   if((target as HTMLInputElement).validity?.valid===false){s.setError('입력값을 확인해 주세요. 올바르지 않은 값은 저장하지 않았습니다.');return;}
  }
  void s.save();
 }
 async function create(e:React.FormEvent){e.preventDefault();const result=await s.run(()=>api<Snapshot>('/projects','POST',{name,characterName:character,cell:{width,height},...(parentDirectory.trim()?{parentDirectory:parentDirectory.trim()}:{})}));if(result&&await open(result.projectId)){await s.refreshProjects();setToolOpen(false);setActiveTool('assets');}}
 async function pickFolder(purpose:'open'|'parent'){const path=await s.pickProjectFolder(purpose);if(path!==null&&path!==undefined)(purpose==='open'?setFolderPath:setParentDirectory)(path);}
 async function openFolder(e:React.FormEvent){e.preventDefault();const project=await s.openProjectFolder(folderPath);if(project){showProject(project.projectId);setToolOpen(false);setActiveTool('assets');}}
 function clearProjectSelection(ids:string[]){
  if(p&&ids.includes(p.projectId)){setClip('');setCurrentSelection({});setToolSelection({});openedRoute.current='';history.replaceState(null,'',location.pathname);}
  if(restoreJob?.result?.projectId&&ids.includes(restoreJob.result.projectId))setRestoreJob(null);
 }
 async function removeProject(){
  if(!deleteTarget||s.busy)return;
  const deleted=await s.deleteProject(deleteTarget);
  if(deleted){clearProjectSelection([deleteTarget.projectId]);setDeleteTarget(null);}
 }
 async function checkMissingFolders(){const items=await s.missingProjectFolders();if(items)setMissingFolders(items);}
 async function cleanupFolders(){if(!missingFolders?.length||s.busy)return;const result=await s.cleanupMissingFolders(missingFolders);if(result){clearProjectSelection(result.removedProjectIds);setMissingFolders(null);}}
 const running=s.jobs.filter(j=>['queued','running'].includes(j.status)).length;
 const savedText=p?.storage?.syncPending?`폴더 저장 보류${s.conflict?' · 저장 충돌':s.commands.length?` · 미저장 ${s.commands.length}개`:''}`:s.busy?'저장·처리 중…':s.conflict?'저장 충돌':s.commands.length?`미저장 ${s.commands.length}개`:p?`저장됨 · v${p.revision}`:'로컬 작업 공간';
 const tool=activeTool==='align'?{label:'크기·발 정렬',description:'후보와 좌표를 나란히 보고 공통 배율과 발을 맞춥니다.'}:undefined;
 const toolContent=p?<>{activeTool==='generateAsset'&&<ImageGenerationStep key={`asset-${p.projectId}`} s={s} assetMode onBack={()=>openTool('assets')}/>} {activeTool==='align'&&<AlignmentStep s={s} initialFrameId={toolSelection.frameVersionId}/>} {activeTool==='jobs'&&<JobsStep s={s} onSelectClip={openVideoClip}/>} {activeTool==='history'&&<HistoryStep s={s}/>} {activeTool==='conflict'&&<Conflict s={s}/>}</>:null;
 return <div className={`studio-shell studio-${page}`}>
  <a className="skip-link" href="#main">작업 영역으로 건너뛰기</a>
  <header className="studio-header">
   <button className="studio-brand" onClick={goProjects} aria-label="프레임룸 프로젝트 목록"><Boxes size={20}/><span>프레임룸</span></button>
   {page==='editor'&&p?<><ChevronRight size={14} className="header-divider"/><div className="document-title"><h1 title={p.name}>{p.name}</h1><span>{p.characterName}</span></div><span className={`document-save ${s.commands.length||p.storage?.syncPending?'unsaved':''}`} role="status">{savedText}</span><div className="studio-header-actions"><button disabled={!s.commands.length||s.busy} onClick={s.undo} title="되돌리기 · ⌘Z" aria-label="되돌리기"><Undo2 size={16}/></button><button disabled={!s.redoCommands.length||s.busy} onClick={s.redo} title="다시 적용 · ⇧⌘Z" aria-label="다시 적용"><Redo2 size={16}/></button><button disabled={!s.commands.length||s.busy||!!s.conflict} onClick={()=>s.save()}><Save size={15}/><span>저장</span></button><button className="primary" onClick={()=>openTool('export')}><Download size={15}/><span>내보내기</span></button></div></>:<div className="studio-header-actions"><a className="button guide-link" href="/guide/index.html" target="_blank" rel="noopener noreferrer"><BookOpen size={15}/>사용 설명서</a><span className={`service ${s.service?'online':''}`}>{service}</span><button onClick={()=>{setPage('viewer');location.hash='viewer';}}><ExternalLink size={15}/>파일 뷰어</button></div>}
  </header>
  {page==='editor'&&p&&<nav className="workspace-commands" aria-label="제작 도구"><div className="tool-command-group utility-commands"><button aria-label="이력·백업" title="이력·백업" onClick={()=>openTool('history')}><History size={15}/><span>이력·백업</span></button><button aria-label={`작업 센터${running?` · ${running}개 처리 중`:``}`} title="작업 센터" onClick={()=>openTool('jobs')}><Activity size={15}/><span>작업 {running>0?running:''}</span></button><a className="button guide-link" href="/guide/index.html" target="_blank" rel="noopener noreferrer" aria-label="사용 설명서 (새 탭)" title="사용 설명서"><BookOpen size={15}/><span>사용 설명서</span></a><button onClick={()=>{if(leaveBlocked())return;setPage('viewer');location.hash='viewer';}} title="독립 파일 뷰어" aria-label="독립 파일 뷰어"><ExternalLink size={15}/></button></div></nav>}
  <Feedback s={s} details={page==='editor'}/>
  {page==='editor'&&s.conflict&&<div className="conflict-banner"><span>다른 창이나 완료된 작업의 변경과 내 초안을 비교해 주세요.</span><button onClick={()=>openTool('conflict')}>저장 충돌 해결</button></div>}
  {page==='editor'&&p?<main id="main" className="studio-work-area"><fieldset className="workspace-fieldset" disabled={s.busy}><ProductionWorkflow key={p.projectId} s={s} step={workflowStep} onStep={setWorkflowStep} clipId={clip} onClip={setClip} onTool={openTool} onSelectionChange={setCurrentSelection} sourceMode={sourceMode} onSourceMode={setSourceMode} sourceAssetId={toolSelection.assetId}/></fieldset></main>:page==='viewer'?<main id="main" className="standalone-workspace"><button className="viewer-back" onClick={()=>{if(p){setPage('editor');history.replaceState(null,'',`#project=${p.projectId}`);}else goProjects();}}><ArrowLeft size={15}/>{p?'편집기로':'프로젝트로'}</button><FileViewer/></main>:<main id="main" className="project-browser">
   <section className="project-browser-toolbar"><div><h1>프로젝트</h1><p>프로젝트마다 폴더 하나에 원본, 편집 이력과 출력 파일을 함께 보관합니다.</p></div><div className="row project-browser-actions"><button disabled={s.busy||!s.service} onClick={()=>openTool('openFolder')}><FolderOpen size={16}/>프로젝트 폴더 열기</button><label className="file-button">백업 복원<input type="file" accept=".zip,application/zip" disabled={s.busy||!s.service} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;const body=new FormData();body.append('backupZip',file);body.append('idempotencyKey',uid());const result=await s.run(()=>api<Job>('/projects/restore','POST',body));if(result)setRestoreJob(result);e.target.value='';}}/></label><button className="primary" disabled={s.busy||!s.service} onClick={()=>openTool('create')}><Plus size={16}/>새 프로젝트</button></div></section>
   {restoreJob&&<Panel title="백업 복원"><JobCard job={restoreJob} s={s}/>{restoreJob.result?.projectId&&<button onClick={()=>open(restoreJob.result!.projectId!)}>복원된 프로젝트 열기</button>}</Panel>}
   <div className="project-storage-toolbar"><p className="project-storage-note">폴더를 옮기거나 이름을 바꾸려면 저장하고 작업을 마친 뒤 Finder에서 폴더를 옮기고, <strong>프로젝트 폴더 열기</strong>로 새 위치를 여세요. 삭제는 폴더까지 지우므로 이동에 사용하지 마세요.</p><button disabled={s.busy||!s.service} onClick={checkMissingFolders}>없는 폴더 정리</button></div>
   <div className="project-list-heading"><span>캐릭터 · 프로젝트</span><span>저장 정보</span><span>동작 / 후보</span></div>
   <div className="project-list">{s.projects.map(project=>{const cover=projectCoverAsset(project);return <div className="project-row" key={project.projectId}>
    <button className="project-file" disabled={s.busy||project.storage?.available===false} onClick={()=>open(project.projectId)}><div className="project-file-identity"><div className="project-file-thumb checker">{cover&&project.storage?.available!==false?<img src={cover.url} alt=""/>:<FolderOpen size={24}/>}</div><div><strong>{project.name}</strong><small>{project.characterName}</small><small className="project-folder-path" title={project.storage?.path}>{project.storage?.path||'폴더 경로 확인 필요'}</small>{project.storage&&<small className={`project-folder-status ${project.storage.available&&!project.storage.syncPending?'':'unavailable'}`}>{project.storage.syncPending?`폴더 저장 보류${project.storage.available?'':' · 폴더 접근 불가'}`:project.storage.available?'폴더 연결됨':'폴더 접근 불가 · 경로와 연결을 확인해 주세요'}</small>}</div></div><span className="project-file-date">v{project.revision}<small>{date(project.updatedAt)}</small></span><span className="project-file-count">{project.clips?.length||0} / {project.frames?.length||0}<ChevronRight size={15}/></span></button>
    <div className="project-actions">
     {cover&&project.storage?.available!==false&&<button type="button" aria-label={`${project.name} 캐릭터 크게 보기`} onClick={()=>setProjectImage(cover)}><ScanFace size={15}/><span>캐릭터 보기</span></button>}
     <button className="project-reveal" aria-label={`${project.name} 프로젝트 폴더 위치 열기`} title={storageTitle} disabled={s.busy||!fileManager||project.storage?.available===false} onClick={()=>s.revealProject(project)}><FolderOpen size={15}/><span>폴더 위치</span></button>
     <button className="project-delete" aria-label={`${project.name} 프로젝트 삭제`} title="프로젝트와 프로젝트 폴더 삭제" disabled={s.busy||!s.service} onClick={()=>{s.setError('');setDeleteTarget(project);}}><Trash2 size={15}/><span>삭제</span></button>
    </div>
   </div>;})}</div>
   {!s.projects.length&&(s.service?<Empty title="프로젝트를 만들거나 폴더를 열어 주세요"><p>기존 프로젝트는 폴더를 선택하면 편집을 이어갈 수 있습니다.</p><button disabled={s.busy} onClick={()=>openTool('create')}>새 프로젝트</button></Empty>:<Empty title={s.providersChecking?'로컬 서버에 연결하는 중입니다':'로컬 서버에 연결되지 않았습니다'}><p>연결되면 저장된 프로젝트 목록이 표시됩니다. 프로젝트 폴더는 변경되지 않습니다.</p><button disabled={s.providersChecking} onClick={s.connect}>{s.providersChecking?'확인 중…':'연결 확인'}</button></Empty>)}
  </main>}
  <footer className="studio-status"><span className={`service ${s.service?'online':''}`}>{page==='viewer'?'독립 파일 재생':service}</span>{page!=='viewer'&&<ProviderConnections providers={s.providers} service={s.service} checking={s.providersChecking} error={s.providersError} onCheck={s.connect}/>}<span className="studio-notice" role="status">{s.notice||((page==='editor'&&p)?`${p.assets.length}개 자료 · ${p.frames.length}개 후보 · ${p.clips.length}개 동작`:'원본과 편집 이력은 이 컴퓨터에 저장됩니다.')}</span>{page!=='viewer'&&<button disabled={s.providersChecking} onClick={s.connect}>{s.providersChecking?'확인 중…':'연결 확인'}</button>}</footer>
  <EditorDialog open={!!projectImage} title="프로젝트 캐릭터 보기" className="reference-image-dialog" onClose={()=>setProjectImage(null)}>
   {projectImage&&<SpriteImage src={projectImage.url} width={projectImage.width} height={projectImage.height} alt="프로젝트 대표 캐릭터"/>}
  </EditorDialog>
  <EditorDialog open={toolOpen} onClose={closeTool} closeDisabled={s.busy&&(activeTool==='create'||activeTool==='openFolder')} title={tool?.label||labels[activeTool]||'작업 도구'} description={tool?.description} className={`tool-${activeTool}`} actions={page==='editor'&&p?<><span className="tool-save-state" role="status">{savedText}</span><button disabled={!s.commands.length||s.busy||!!s.conflict} onClick={()=>s.save()}><Save size={14}/>저장</button></>:undefined}>
   <Feedback s={s} details={page==='editor'}/>
   <div className={`tool-content tool-content-${activeTool}`}>
    {activeTool==='create'?<form className="new-project-form" onSubmit={create}><fieldset disabled={s.busy}>
     <Input label="프로젝트 이름" required maxLength={200} value={name} onChange={e=>setName(e.target.value)} placeholder="예: 하늘 해적" autoFocus/>
     <Input label="캐릭터 이름" required maxLength={200} value={character} onChange={e=>setCharacter(e.target.value)} placeholder="예: 스카이 거너"/>
     <div className="project-folder-input"><Input label="저장할 부모 폴더 (선택)" value={parentDirectory} onChange={e=>setParentDirectory(e.target.value)} placeholder="비우면 기본 프로젝트 폴더 사용" autoComplete="off" spellCheck={false}/><button type="button" disabled={s.busy||!s.service} onClick={()=>pickFolder('parent')}>폴더 선택</button></div>
     <p className="caption">선택한 위치 안에 새 프로젝트 폴더를 만듭니다. 선택창을 사용할 수 없으면 경로를 직접 입력하세요.</p>
     <div className="number-grid"><Num label="기본 셀 너비 (px)" value={width} min={1} max={4096} onChange={setWidth}/><Num label="기본 셀 높이 (px)" value={height} min={1} max={4096} onChange={setHeight}/></div>
     <button className="primary" disabled={s.busy||!s.service}>프로젝트 만들기</button>
    </fieldset></form>:activeTool==='openFolder'?<form className="new-project-form" onSubmit={openFolder}><fieldset disabled={s.busy}>
     <div className="project-folder-input"><Input label="프로젝트 폴더 경로" required value={folderPath} onChange={e=>setFolderPath(e.target.value)} placeholder="프로젝트 폴더의 전체 경로" autoFocus autoComplete="off" spellCheck={false}/><button type="button" disabled={s.busy||!s.service} onClick={()=>pickFolder('open')}>폴더 선택</button></div>
     <p className="caption">프로젝트 폴더를 선택하거나 경로를 직접 입력하세요. 폴더 안의 project.json 또는 project.sqlite3 경로도 열 수 있습니다.</p>
     <p className="caption">원본, 저장된 편집 이력과 출력 파일을 함께 엽니다. 이전 생성 작업은 자동으로 다시 실행하지 않습니다.</p>
     <button className="primary" disabled={s.busy||!s.service||!folderPath.trim()}>폴더 열기</button>
    </fieldset></form>:<fieldset className="tool-fieldset" disabled={s.busy}>{toolContent}</fieldset>}
   </div>
   {!['create','openFolder'].includes(activeTool)&&<div className="tool-footer"><span>{['generate','generateAsset'].includes(activeTool)?'생성 작업은 도구를 닫아도 계속됩니다.':'편집 중인 동작과 프레임 선택은 유지됩니다.'}</span><button onClick={closeTool}>편집기로 돌아가기</button></div>}
  </EditorDialog>
  <EditorDialog open={!!deleteTarget} onClose={()=>{if(!s.busy)setDeleteTarget(null);}} title="프로젝트 삭제" className="project-delete-dialog" closeDisabled={s.busy}>
   <Feedback s={s}/>
   <div className="project-delete-content">
    <p><strong>“{deleteTarget?.name}”</strong> 프로젝트를 삭제할까요?</p>
    {deleteTarget?.storage&&<p className="project-folder-path">{deleteTarget.storage.path}</p>}
    <p><strong>이 프로젝트 폴더와 그 안의 원본, 저장된 편집 이력, 작업·출력 파일을 모두 삭제합니다. 되돌릴 수 없습니다.</strong> 폴더가 이미 없으면 목록 등록만 지웁니다.</p>
    <p>이 브라우저의 미저장 편집 초안도 지워집니다. 보관하려면 먼저 Finder에서 폴더를 복사해 두세요. 폴더를 옮기려는 경우에는 삭제하지 말고, 옮긴 뒤 <strong>프로젝트 폴더 열기</strong>로 새 위치를 여세요.</p>
    <div className="project-delete-actions"><button autoFocus disabled={s.busy} onClick={()=>setDeleteTarget(null)}>취소</button><button className="danger" disabled={s.busy||!s.service} onClick={removeProject}>{s.busy?'삭제 중…':'프로젝트와 폴더 삭제'}</button></div>
   </div>
  </EditorDialog>
  <EditorDialog open={missingFolders!==null} onClose={()=>{if(!s.busy)setMissingFolders(null);}} title="없는 폴더 정리" className="project-delete-dialog" closeDisabled={s.busy}>
   <Feedback s={s}/>
   <div className="project-delete-content">
    {missingFolders?.length?<><p>폴더가 없는 프로젝트 <strong>{missingFolders.length}개</strong>를 목록에서 정리합니다. 이름과 경로를 확인해 주세요.</p><ul className="missing-project-list">{missingFolders.map(project=><li key={project.projectId}><strong>{project.name}</strong><span className="project-folder-path">{project.path}</span></li>)}</ul><p>앱의 목록 등록과 이 브라우저의 해당 편집 초안만 정리합니다. 실제 파일은 변경하지 않습니다. 이동했거나 외장 디스크가 분리된 폴더는 위치를 확인한 뒤 다시 열 수 있습니다.</p></>:<p role="status">정리할 없는 폴더가 없습니다. 등록된 프로젝트 폴더가 모두 존재합니다.</p>}
    <div className="project-delete-actions"><button autoFocus disabled={s.busy} onClick={()=>setMissingFolders(null)}>{missingFolders?.length?'취소':'닫기'}</button><button disabled={s.busy||!s.service} onClick={checkMissingFolders}>다시 확인</button>{!!missingFolders?.length&&<button disabled={s.busy||!s.service} onClick={cleanupFolders}>{s.busy?'정리 중…':`${missingFolders.length}개 등록 정리`}</button>}</div>
   </div>
  </EditorDialog>
 </div>;
}
