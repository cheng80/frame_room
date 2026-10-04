import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import type {Snapshot,MissingProjectFolder} from '../src/types';

// Unit harness only; native dialog and browser interaction require separate ego checks.
const hooks=vi.hoisted(()=>({current:null as any}));
vi.mock('react',()=>({
 useRef:(value:unknown)=>hooks.current.ref(value),
 useState:(value:unknown)=>hooks.current.state(value),
 useEffect:(fn:()=>unknown,deps:unknown[])=>hooks.current.effect(fn,deps),
 useMemo:(fn:()=>unknown)=>fn(),
}));
vi.mock('../src/api',async original=>({...await original<typeof import('../src/api')>(),api:vi.fn(),health:vi.fn()}));
import {api,ApiError} from '../src/api';
import {useStudio,type Studio} from '../src/useStudio';

class Harness {
 slots:any[]=[];cursor=0;effects:(()=>void)[]=[];value!:Studio;
 constructor(){this.render();}
 ref(value:unknown){const i=this.cursor++;return this.slots[i]??=({current:value});}
 state(value:unknown){const i=this.cursor++;const slot=this.slots[i]??={value};return [slot.value,(next:any)=>{slot.value=typeof next==='function'?next(slot.value):next;}];}
 effect(fn:()=>any,deps:unknown[]){const i=this.cursor++,old=this.slots[i];if(old&&deps.length===old.deps.length&&deps.every((v,j)=>Object.is(v,old.deps[j])))return;
  this.effects.push(()=>{old?.cleanup?.();this.slots[i]={deps,cleanup:fn()};});
 }
 render(){this.cursor=0;this.effects=[];hooks.current=this;this.value=useStudio(true);hooks.current=null;this.effects.forEach(fn=>fn());}
 close(){this.slots.forEach(s=>s?.cleanup?.());}
}
const a={projectId:'a',name:'목록 제거 시험',revision:3,characterName:'원본',storage:{layout:'project-folder',path:'/projects/a',available:true},assets:[],clips:[],frames:[],alignments:{},alignmentGroups:[]} as unknown as Snapshot;
const b={...a,projectId:'b',name:'보존 시험'};
let h:Harness;let storage:Map<string,string>;
const mockApi=vi.mocked(api);
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};}
beforeEach(()=>{
 storage=new Map();vi.stubGlobal('window',{addEventListener:vi.fn(),removeEventListener:vi.fn()});
 vi.stubGlobal('localStorage',{getItem:(key:string)=>storage.get(key)??null,setItem:(key:string,value:string)=>storage.set(key,value),removeItem:(key:string)=>storage.delete(key)});
 mockApi.mockReset();mockApi.mockImplementation(async (path,method)=>{
  if(method==='DELETE')return {deletedProjectId:path.split('/').at(-1)};
  if(path==='/projects')return {projects:[a,b]};
  if(path.endsWith('/jobs'))return {jobs:[{jobId:'j',status:'succeeded'}]};
  if(path.endsWith('/exports'))return {exports:[{exportId:'e'}]};
  if(path.endsWith('/revisions'))return {revisions:[{revision:3}]};
  return path==='/projects/a'?a:b;
 });h=new Harness();
});
afterEach(()=>{h.close();vi.unstubAllGlobals();});
async function openWithDraft(){await h.value.load('a');await h.value.refreshProjects();h.render();h.value.edit({type:'updateCharacter',name:'수정 초안'});h.render();}

describe('project detachment state',()=>{
 it('clears the selected project, draft and histories only after the server acknowledges deletion',async()=>{
  await openWithDraft();storage.set('frame-room-draft:b','keep');h.value.setConflict(b);h.render();
  expect(storage.has('frame-room-draft:a')).toBe(true);
  expect(await h.value.deleteProject(a)).toBe(true);h.render();
  expect(mockApi).toHaveBeenCalledWith('/projects/a','DELETE',{expectedRevision:3});
  expect(h.value.projects.map(p=>p.projectId)).toEqual(['b']);
  expect(h.value.base).toBeNull();expect(h.value.snapshot).toBeNull();expect(h.value.conflict).toBeNull();
  for(const values of [h.value.commands,h.value.redoCommands,h.value.jobs,h.value.exports,h.value.revisions])expect(values).toEqual([]);
  expect(storage.has('frame-room-draft:a')).toBe(false);expect(storage.get('frame-room-draft:b')).toBe('keep');
  expect(h.value.notice).toContain('목록에서 제거');expect(h.value.notice).toContain('데이터는 모두 유지');
 });
 it('preserves another open project and its unsaved edits when deleting from the list',async()=>{
  await openWithDraft();const before=storage.get('frame-room-draft:a');storage.set('frame-room-draft:b','discard');
  await h.value.deleteProject(b);h.render();
  expect(h.value.base?.projectId).toBe('a');expect(h.value.snapshot?.characterName).toBe('수정 초안');
  expect(storage.get('frame-room-draft:a')).toBe(before);expect(storage.has('frame-room-draft:b')).toBe(false);
  expect(h.value.jobs).toHaveLength(1);
 });
 it.each([[409,'PROJECT_BUSY'],[409,'REVISION_CONFLICT'],[0,'OFFLINE'],[500,'SERVER_ERROR'],[404,'HTTP_404']])('preserves drafts and project data on failure %s/%s',async(status,code)=>{
  await openWithDraft();const before=storage.get('frame-room-draft:a');const original=mockApi.getMockImplementation()!;
  mockApi.mockImplementation((path,method,body)=>method==='DELETE'?Promise.reject(new ApiError(status,code,'삭제 실패')):original(path,method,body));
  expect(await h.value.deleteProject(a)).toBeUndefined();h.render();
  expect(h.value.base).toEqual(a);expect(h.value.commands).toHaveLength(1);expect(h.value.projects).toHaveLength(2);
  expect(storage.get('frame-room-draft:a')).toBe(before);expect(h.value.jobs).toHaveLength(1);expect(h.value.busy).toBe(false);expect(h.value.error).not.toBe('');
 });
 it('ignores stale list and detail responses arriving after deletion',async()=>{
  await openWithDraft();const list=deferred<any>(),jobs=deferred<any>();const original=mockApi.getMockImplementation()!;
  mockApi.mockImplementation((path,method,body)=>method==='DELETE'?original(path,method,body):path==='/projects'?list.promise:path.endsWith('/jobs')?jobs.promise:original(path,method,body));
  const pendingList=h.value.refreshProjects(),pendingDetails=h.value.refreshDetails('a');
  await h.value.deleteProject(a);h.render();list.resolve({projects:[a,b]});jobs.resolve({jobs:[{jobId:'old'}]});
  await Promise.all([pendingList,pendingDetails]);h.render();
  expect(h.value.projects.map(p=>p.projectId)).toEqual(['b']);expect(h.value.jobs).toEqual([]);expect(h.value.exports).toEqual([]);expect(h.value.revisions).toEqual([]);
 });
 it('blocks duplicate clicks and keeps the project until deletion succeeds',async()=>{
  await openWithDraft();const ack=deferred<any>();mockApi.mockImplementation(()=>ack.promise);mockApi.mockClear();
  const pending=h.value.deleteProject(a);h.render();expect(h.value.busy).toBe(true);expect(h.value.base).toEqual(a);
  await h.value.deleteProject(a);expect(mockApi).toHaveBeenCalledTimes(1);
  ack.resolve({deletedProjectId:'a'});await pending;h.render();expect(h.value.base).toBeNull();
 });
 it('clears stale local state when another window already deleted the project',async()=>{
  await openWithDraft();mockApi.mockRejectedValue(new ApiError(404,'PROJECT_NOT_FOUND','프로젝트 없음'));
  expect(await h.value.deleteProject(a)).toBe(true);h.render();expect(h.value.base).toBeNull();expect(storage.has('frame-room-draft:a')).toBe(false);
 });
 it('reports a missing project as a failed load instead of opening the previous project',async()=>{
  await openWithDraft();mockApi.mockRejectedValue(new ApiError(404,'PROJECT_NOT_FOUND','프로젝트 없음'));
  expect(await h.value.load('missing')).toBe(false);h.render();expect(h.value.base?.projectId).toBe('a');
 });
});

describe('project storage location',()=>{
 it.each(['finder','explorer'] as const)('opens %s without switching projects or saving the current draft',async fileManager=>{
  await openWithDraft();const draft=storage.get('frame-room-draft:a');
  mockApi.mockResolvedValue({projectId:'b',path:'/projects/b',storageLayout:'project-folder',fileManager});mockApi.mockClear();
  await h.value.revealProject(b);h.render();
  expect(mockApi).toHaveBeenCalledExactlyOnceWith('/projects/b/reveal','POST',{});
  expect(h.value.base?.projectId).toBe('a');expect(h.value.commands).toHaveLength(1);expect(storage.get('frame-room-draft:a')).toBe(draft);
  expect(h.value.notice).toContain(fileManager==='finder'?'Finder':'탐색기');expect(h.value.notice).toContain('프로젝트 폴더');expect(h.value.notice).not.toContain('공용');
 });
 it('keeps the draft and reports file manager failure',async()=>{
  await openWithDraft();const draft=storage.get('frame-room-draft:a');
  mockApi.mockRejectedValue(new ApiError(503,'FILE_MANAGER_UNAVAILABLE','파일 관리자 실행 실패'));
  await h.value.revealProject(a);h.render();
  expect(h.value.error).toBe('파일 관리자 실행 실패');expect(h.value.commands).toHaveLength(1);expect(storage.get('frame-room-draft:a')).toBe(draft);expect(h.value.busy).toBe(false);
 });
});

describe('project folder registration',()=>{
 it.each(['open','parent'] as const)('requests the native picker for %s without editing the project',async purpose=>{
  await openWithDraft();const before=storage.get('frame-room-draft:a');mockApi.mockResolvedValue({path:'/chosen folder'});mockApi.mockClear();
  expect(await h.value.pickProjectFolder(purpose)).toBe('/chosen folder');h.render();
  expect(mockApi).toHaveBeenCalledExactlyOnceWith('/project-folders/pick','POST',{purpose});
  expect(h.value.base?.projectId).toBe('a');expect(storage.get('frame-room-draft:a')).toBe(before);
 });
 it('treats picker cancellation as a non-error',async()=>{
  mockApi.mockResolvedValue({path:null});expect(await h.value.pickProjectFolder('open')).toBeNull();h.render();expect(h.value.error).toBe('');
 });
 it('reports an unsupported picker without affecting the open draft',async()=>{
  await openWithDraft();mockApi.mockRejectedValue(new ApiError(501,'FOLDER_PICKER_UNAVAILABLE','경로를 직접 입력하세요.'));
  expect(await h.value.pickProjectFolder('parent')).toBeUndefined();h.render();expect(h.value.error).toBe('경로를 직접 입력하세요.');expect(h.value.commands).toHaveLength(1);
 });
 it('reopens a detached project and restores histories, later loads, and list refreshes',async()=>{
  await openWithDraft();await h.value.deleteProject(a);h.render();
  const moved={...a,storage:{...a.storage!,path:'/moved project'}};const original=mockApi.getMockImplementation()!;
  mockApi.mockImplementation((path,method,body)=>path==='/project-folders/open'?Promise.resolve(moved):path==='/projects/a'?Promise.resolve(moved):original(path,method,body));
  expect(await h.value.openProjectFolder(' /moved project ')).toEqual(moved);h.render();
  expect(mockApi).toHaveBeenCalledWith('/project-folders/open','POST',{path:'/moved project'});
  expect(h.value.base).toEqual(moved);expect(h.value.commands).toEqual([]);expect(h.value.jobs).toHaveLength(1);expect(h.value.revisions).toHaveLength(1);
  expect(h.value.projects.map(p=>p.projectId)).toContain('a');
  await h.value.refreshProjects();expect(await h.value.load('a')).toBe(true);h.render();
  expect(h.value.projects.map(p=>p.projectId)).toContain('a');expect(h.value.exports).toHaveLength(1);
 });
 it('allows a successful direct load after another window re-registers a detached project',async()=>{
  await openWithDraft();await h.value.deleteProject(a);h.render();await h.value.load('a');h.render();
  expect(h.value.jobs).toHaveLength(1);expect(h.value.projects.map(p=>p.projectId)).toContain('a');
 });
 it('ignores stale absent-list and detail responses after folder re-registration',async()=>{
  await openWithDraft();const list=deferred<any>(),jobs=deferred<any>();const original=mockApi.getMockImplementation()!;
  mockApi.mockImplementation((path,method,body)=>path==='/projects'?list.promise:path==='/projects/a/jobs'?jobs.promise:original(path,method,body));
  const pendingList=h.value.refreshProjects(),pendingDetails=h.value.refreshDetails('a');
  await h.value.deleteProject(a);h.render();
  mockApi.mockImplementation((path,method,body)=>path==='/project-folders/open'?Promise.resolve(a):original(path,method,body));
  await h.value.openProjectFolder('/projects/a');h.render();
  list.resolve({projects:[b]});jobs.resolve({jobs:[{jobId:'old'}]});await Promise.all([pendingList,pendingDetails]);h.render();
  expect(h.value.projects.map(p=>p.projectId)).toContain('a');expect(h.value.jobs[0].jobId).toBe('j');
 });
 it('uses the newly opened folder path when restoring a preserved browser draft',async()=>{
  await openWithDraft();const original=mockApi.getMockImplementation()!;
  mockApi.mockImplementation((path,method,body)=>path==='/project-folders/open'?Promise.resolve({...a,storage:{...a.storage!,path:'/new location'}}):original(path,method,body));
  await h.value.openProjectFolder('/new location');h.render();
  expect(h.value.snapshot?.characterName).toBe('수정 초안');expect(h.value.base?.storage?.path).toBe('/new location');
 });
 it.each([409,422,503])('preserves the open project and draft on folder error %s',async status=>{
  await openWithDraft();const before=storage.get('frame-room-draft:a');mockApi.mockRejectedValue(new ApiError(status,'FOLDER_ERROR','폴더를 열 수 없습니다.'));
  expect(await h.value.openProjectFolder('/invalid')).toBeUndefined();h.render();expect(h.value.base).toEqual(a);expect(storage.get('frame-room-draft:a')).toBe(before);expect(h.value.busy).toBe(false);
 });
 it('rejects an empty path without a request',async()=>{
  mockApi.mockClear();await h.value.openProjectFolder('  ');h.render();expect(mockApi).not.toHaveBeenCalled();expect(h.value.error).toContain('경로를 입력');
 });
});

describe('pending project folder save',()=>{
 it('reads storage after a 503 without accepting the newer revision or dropping local commands',async()=>{
  await openWithDraft();const commands=h.value.commands;
  const latest={...a,revision:4,characterName:'인덱스에만 저장된 변경',storage:{...a.storage!,syncPending:true}};
  mockApi.mockImplementation(async(path,method)=>{if(method==='PATCH')throw new ApiError(503,'PROJECT_FOLDER_SYNC_FAILED','폴더 저장 실패');return latest;});mockApi.mockClear();
  expect(await h.value.save()).toBe(false);h.render();
  expect(mockApi).toHaveBeenCalledWith('/projects/a');expect(h.value.base?.revision).toBe(3);expect(h.value.base?.characterName).toBe('원본');
  expect(h.value.base?.storage).toEqual(latest.storage);expect(h.value.commands).toEqual(commands);expect(h.value.snapshot?.characterName).toBe('수정 초안');
  expect(h.value.projects.find(p=>p.projectId==='a')).toMatchObject({revision:3,storage:{syncPending:true}});
  expect(h.value.error).toBe('폴더 저장 실패');expect(h.value.notice).toContain('폴더 저장 보류');expect(h.value.conflict).toBeNull();
  expect(JSON.parse(storage.get('frame-room-draft:a')!)).toMatchObject({base:{revision:3,storage:{syncPending:true}},commands:JSON.parse(JSON.stringify(commands))});
 });
 it('retains only acknowledged progress when a later save command cannot flush to its folder',async()=>{
  await openWithDraft();h.value.edit({type:'updateCharacter',name:'다음 초안'});h.render();let requests=0;
  const acknowledged={...a,revision:4,characterName:'수정 초안'};
  mockApi.mockImplementation(async(path,method)=>{
   if(method==='PATCH'){if(++requests===1)return {savedRevision:4,snapshot:acknowledged};throw new ApiError(503,'PROJECT_FOLDER_SYNC_FAILED','폴더 저장 실패');}
   return {...acknowledged,revision:5,characterName:'다음 초안',storage:{...a.storage!,syncPending:true}};
  });
  expect(await h.value.save()).toBe(false);h.render();
  expect(h.value.base).toMatchObject({revision:4,characterName:'수정 초안',storage:{syncPending:true}});
  expect(h.value.commands.map(c=>c.operation)).toEqual([{type:'updateCharacter',name:'다음 초안'}]);expect(h.value.snapshot?.characterName).toBe('다음 초안');
 });
 it('preserves the original save error and draft when the storage query also fails',async()=>{
  await openWithDraft();h.value.setNotice('저장됨 · 버전 2');h.render();
  mockApi.mockImplementation(async(path,method)=>{throw method==='PATCH'?new ApiError(503,'PROJECT_FOLDER_SYNC_FAILED','원래 저장 오류'):new ApiError(0,'OFFLINE','조회 연결 끊김');});
  expect(await h.value.save()).toBe(false);h.render();expect(h.value.error).toBe('원래 저장 오류');expect(h.value.base).toEqual(a);expect(h.value.commands).toHaveLength(1);expect(h.value.notice).not.toContain('저장됨');
 });
 it('keeps the existing revision-conflict flow after an unacknowledged save',async()=>{
  await openWithDraft();const latest={...a,revision:4,storage:{...a.storage!,syncPending:true}};
  mockApi.mockImplementation(async(path,method)=>{if(method==='PATCH')throw new ApiError(409,'REVISION_CONFLICT','저장 충돌');return latest;});
  expect(await h.value.save()).toBe(false);h.render();expect(h.value.base?.revision).toBe(3);expect(h.value.commands).toHaveLength(1);expect(h.value.conflict).toEqual(latest);
 });
});

describe('missing folder index cleanup',()=>{
 const missing:MissingProjectFolder[]=[{projectId:'a',name:a.name,path:'/gone/a',revision:3}];
 it('previews the server list without clearing any data',async()=>{
  await openWithDraft();const before=storage.get('frame-room-draft:a');mockApi.mockResolvedValue({projects:missing});mockApi.mockClear();
  expect(await h.value.missingProjectFolders()).toEqual(missing);h.render();
  expect(mockApi).toHaveBeenCalledExactlyOnceWith('/project-folders/missing');expect(h.value.base).toEqual(a);expect(storage.get('frame-room-draft:a')).toBe(before);
 });
 it('sends only the confirmed ID, revision and path, then clears acknowledged IDs and refreshes',async()=>{
  await openWithDraft();storage.set('frame-room-draft:b','keep');const original=mockApi.getMockImplementation()!;
  mockApi.mockImplementation((path,method,body)=>path==='/project-folders/cleanup'?Promise.resolve({removedProjectIds:['a'],removedCount:1}):original(path,method,body));mockApi.mockClear();
  expect(await h.value.cleanupMissingFolders(missing)).toEqual({removedProjectIds:['a'],removedCount:1});h.render();
  expect(mockApi).toHaveBeenCalledWith('/project-folders/cleanup','POST',{projects:[{projectId:'a',expectedRevision:3,path:'/gone/a'}]});
  expect(mockApi).toHaveBeenCalledWith('/projects');expect(h.value.projects.map(p=>p.projectId)).toEqual(['b']);expect(h.value.base).toBeNull();
  expect(h.value.commands).toEqual([]);expect(h.value.jobs).toEqual([]);expect(h.value.exports).toEqual([]);expect(h.value.revisions).toEqual([]);
  expect(storage.has('frame-room-draft:a')).toBe(false);expect(storage.get('frame-room-draft:b')).toBe('keep');expect(h.value.notice).toContain('실제 파일은 변경하지 않았습니다');
 });
 it('keeps the active project and draft when only another missing project is acknowledged',async()=>{
  await openWithDraft();const before=storage.get('frame-room-draft:a'),original=mockApi.getMockImplementation()!;
  mockApi.mockImplementation((path,method,body)=>path==='/project-folders/cleanup'?Promise.resolve({removedProjectIds:['b'],removedCount:1}):original(path,method,body));
  await h.value.cleanupMissingFolders([{...missing[0],projectId:'b'}]);h.render();expect(h.value.base).toEqual(a);expect(storage.get('frame-room-draft:a')).toBe(before);expect(h.value.jobs).toHaveLength(1);
 });
 it.each(['FOLDER_AVAILABLE','PROJECT_BUSY','REVISION_CONFLICT','PROJECT_PATH_CHANGED'])('keeps all local data when cleanup is rejected for %s',async code=>{
  await openWithDraft();const before=storage.get('frame-room-draft:a');mockApi.mockRejectedValue(new ApiError(409,code,'조건이 바뀌었습니다. 다시 확인하세요.'));
  expect(await h.value.cleanupMissingFolders(missing)).toBeUndefined();h.render();
  expect(h.value.base).toEqual(a);expect(h.value.projects).toHaveLength(2);expect(h.value.commands).toHaveLength(1);expect(storage.get('frame-room-draft:a')).toBe(before);expect(h.value.busy).toBe(false);
 });
 it('never submits an empty cleanup list',async()=>{
  mockApi.mockClear();expect(await h.value.cleanupMissingFolders([])).toBeUndefined();h.render();expect(mockApi).not.toHaveBeenCalled();expect(h.value.notice).toContain('정리할 없는 폴더가 없습니다');
 });
 it('prevents duplicate cleanup while the acknowledgement is pending',async()=>{
  await openWithDraft();const ack=deferred<any>(),original=mockApi.getMockImplementation()!;
  mockApi.mockImplementation((path,method,body)=>path==='/project-folders/cleanup'?ack.promise:original(path,method,body));mockApi.mockClear();
  const pending=h.value.cleanupMissingFolders(missing);h.render();expect(h.value.busy).toBe(true);expect(h.value.base).toEqual(a);
  await h.value.cleanupMissingFolders(missing);expect(mockApi).toHaveBeenCalledTimes(1);
  ack.resolve({removedProjectIds:['a'],removedCount:1});await pending;h.render();expect(h.value.base).toBeNull();
 });
});
