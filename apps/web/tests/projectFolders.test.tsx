import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import type {ReactElement} from 'react';
import type {Snapshot,MissingProjectFolder} from '../src/types';
import type {Studio} from '../src/useStudio';

// Component-event tests only; the parent task performs the ego browser checks.
const state=vi.hoisted(()=>({hooks:null as any,studio:null as unknown as Studio}));
vi.mock('react',async original=>({...await original<typeof import('react')>(),
 useState:(value:unknown)=>state.hooks.state(value),useRef:(value:unknown)=>state.hooks.ref(value),useEffect:vi.fn(),
}));
vi.mock('../src/useStudio',()=>({useStudio:()=>state.studio}));
vi.mock('../src/api',async original=>({...await original<typeof import('../src/api')>(),api:vi.fn()}));
import App from '../src/App';
import {EditorDialog} from '../src/EditorDialog';
import {api} from '../src/api';

type Node=ReactElement<any>;
function nodes(tree:any):Node[]{
 if(Array.isArray(tree))return tree.flatMap(nodes);
 if(!tree?.props)return [];
 if(tree.type===EditorDialog&&!tree.props.open)return [];
 return [tree,...nodes(tree.props.children)];
}
function text(tree:any):string{
 if(typeof tree==='string'||typeof tree==='number')return String(tree);
 if(Array.isArray(tree))return tree.map(text).join('');
 return tree?.props?text(tree.props.children):'';
}
class Harness {
 slots:any[]=[];cursor=0;tree:any;
 constructor(){this.render();}
 state(initial:unknown){const slot=this.slots[this.cursor++]??={value:initial};return [slot.value,(next:any)=>{slot.value=typeof next==='function'?next(slot.value):next;}];}
 ref(initial:unknown){return this.slots[this.cursor++]??={current:initial};}
 render(){this.cursor=0;state.hooks=this;this.tree=App();state.hooks=null;}
 button(label:string){const dialog=nodes(this.tree).filter(n=>n.type===EditorDialog).at(-1);const n=nodes(dialog||this.tree).find(n=>n.type==='button'&&(n.props['aria-label']===label||text(n)===label));if(!n)throw new Error(`Missing button: ${label}`);return n;}
 async click(label:string){const n=this.button(label);expect(n.props.disabled).not.toBe(true);await n.props.onClick();this.render();}
 field(label:string){const n=nodes(this.tree).find(n=>n.props.label===label);if(!n)throw new Error(`Missing field: ${label}`);return n;}
 change(label:string,value:string){this.field(label).props.onChange({target:{value}});this.render();}
 dialog(title:string){return nodes(this.tree).find(n=>n.type===EditorDialog&&n.props.title===title);}
 async submit(){await nodes(this.tree).find(n=>n.type==='form')!.props.onSubmit({preventDefault:vi.fn()});this.render();}
}
const project={projectId:'a',name:'걷기',characterName:'기사',revision:3,updatedAt:'2026-10-04T12:00:00Z',assets:[],frames:[],clips:[],storage:{layout:'project-folder',path:'/Users/test/My Projects/기사',available:true}} as unknown as Snapshot;
const missing:MissingProjectFolder[]=[{projectId:'a',name:project.name,path:'/Volumes/Old/기사',revision:3}];
const mockApi=vi.mocked(api);
let s:Studio;
beforeEach(()=>{
 vi.stubGlobal('location',{hash:'',pathname:'/'});vi.stubGlobal('history',{replaceState:vi.fn()});
 mockApi.mockReset();mockApi.mockResolvedValue(project);
 s={snapshot:null,base:null,projects:[project],commands:[],redoCommands:[],jobs:[],busy:false,error:'',notice:'',conflict:null,service:{api:'ready',worker:'ready',desktop:{fileManager:'finder'}},
  run:vi.fn(async fn=>fn()),load:vi.fn(async()=>true),refreshProjects:vi.fn(async()=>{}),
  pickProjectFolder:vi.fn(async()=>'/chosen'),openProjectFolder:vi.fn(async()=>project),deleteProject:vi.fn(async()=>true),
  missingProjectFolders:vi.fn(async()=>missing),cleanupMissingFolders:vi.fn(async()=>({removedProjectIds:['a'],removedCount:1})),
  setError:vi.fn(),revealProject:vi.fn(),report:vi.fn(),
 } as unknown as Studio;state.studio=s;
});
afterEach(()=>vi.unstubAllGlobals());

describe('project folder forms',()=>{
 it('creates beneath an optional parent directory and uses the server-selected folder',async()=>{
  const h=new Harness();await h.click('새 프로젝트');h.change('프로젝트 이름','기사');h.change('캐릭터 이름','기사');
  await h.click('폴더 선택');expect(s.pickProjectFolder).toHaveBeenCalledWith('parent');expect(h.field('저장할 부모 폴더 (선택)').props.value).toBe('/chosen');
  h.change('저장할 부모 폴더 (선택)',' /manual parent ');await h.submit();
  expect(mockApi).toHaveBeenCalledExactlyOnceWith('/projects','POST',{name:'기사',characterName:'기사',cell:{width:512,height:512},parentDirectory:'/manual parent'});
  expect(s.load).toHaveBeenCalledWith('a');expect(history.replaceState).toHaveBeenCalledWith(null,'','#project=a');
 });
 it('omits parentDirectory when the user chooses the default location',async()=>{
  const h=new Harness();await h.click('새 프로젝트');h.change('프로젝트 이름','기사');h.change('캐릭터 이름','기사');await h.submit();
  expect(mockApi.mock.calls[0][2]).not.toHaveProperty('parentDirectory');
 });
 it.each([null,undefined])('keeps a typed fallback path when the native picker returns %s',async result=>{
  vi.mocked(s.pickProjectFolder).mockResolvedValue(result);
  const h=new Harness();await h.click('프로젝트 폴더 열기');h.change('프로젝트 폴더 경로','/typed project/project.json');await h.click('폴더 선택');
  expect(s.pickProjectFolder).toHaveBeenCalledWith('open');expect(h.field('프로젝트 폴더 경로').props.value).toBe('/typed project/project.json');
  expect(s.openProjectFolder).not.toHaveBeenCalled();await h.submit();
  expect(s.openProjectFolder).toHaveBeenCalledExactlyOnceWith('/typed project/project.json');expect(s.load).not.toHaveBeenCalled();expect(h.dialog('프로젝트 폴더 열기')).toBeUndefined();
 });
 it('waits for an explicit open after choosing a folder and blocks an empty path',async()=>{
  const h=new Harness();await h.click('프로젝트 폴더 열기');expect(h.button('폴더 열기').props.disabled).toBe(true);await h.click('폴더 선택');
  expect(h.field('프로젝트 폴더 경로').props.value).toBe('/chosen');expect(s.openProjectFolder).not.toHaveBeenCalled();
  await h.submit();expect(s.openProjectFolder).toHaveBeenCalledWith('/chosen');expect(mockApi).not.toHaveBeenCalled();
 });
 it('keeps the entered path and dialog open after registration fails',async()=>{
  vi.mocked(s.openProjectFolder).mockResolvedValue(undefined);const h=new Harness();await h.click('프로젝트 폴더 열기');h.change('프로젝트 폴더 경로','/missing');await h.submit();
  expect(h.dialog('프로젝트 폴더 열기')).toBeDefined();expect(h.field('프로젝트 폴더 경로').props.value).toBe('/missing');expect(history.replaceState).not.toHaveBeenCalled();
 });
});

describe('project folder list and detachment',()=>{
 it('warns about a pending folder save even when the folder is available',()=>{
  s.projects=[{...project,storage:{...project.storage!,syncPending:true}}];const h=new Harness();
  const status=nodes(h.tree).find(n=>String(n.props.className).startsWith('project-folder-status'))!;
  expect(text(status)).toBe('폴더 저장 보류');expect(status.props.className).toContain('unavailable');expect(text(h.tree)).not.toContain('폴더 연결됨');
 });
 it.each([0,1])('never labels a pending folder as saved in the editor header (%s draft commands)',async count=>{
  s.snapshot={...project,storage:{...project.storage!,syncPending:true}};s.base=s.snapshot;
  s.commands=Array.from({length:count},()=>({operation:{type:'updateCharacter',name:'초안'}}));const h=new Harness();
  await nodes(h.tree).find(n=>n.props.className==='project-file')!.props.onClick();h.render();
  const status=nodes(h.tree).find(n=>String(n.props.className).startsWith('document-save'))!;
  expect(text(status)).toContain('폴더 저장 보류');expect(text(status)).not.toContain('저장됨');expect(status.props.className).toContain('unsaved');
  if(count)expect(text(status)).toContain('미저장 1개');
 });
 it('shows the full folder path and availability with a project-specific reveal action',async()=>{
  const h=new Harness();expect(text(h.tree)).toContain(project.storage!.path);expect(text(h.tree)).toContain('폴더 연결됨');
  expect(h.button('걷기 프로젝트 폴더 위치 열기').props.title).toBe('Finder에서 이 프로젝트 폴더 열기');
  await h.click('걷기 프로젝트 폴더 위치 열기');expect(s.revealProject).toHaveBeenCalledExactlyOnceWith(project);
 });
 it('blocks opening or revealing unavailable folders while retaining the list-removal action',()=>{
  s.projects=[{...project,storage:{...project.storage!,available:false}}];const h=new Harness();
  expect(text(h.tree)).toContain('폴더 접근 불가');expect(nodes(h.tree).find(n=>n.props.className==='project-file')!.props.disabled).toBe(true);
  expect(h.button('걷기 프로젝트 폴더 위치 열기').props.disabled).toBe(true);expect(h.button('걷기 목록에서 제거').props.disabled).toBe(false);
 });
 it('explains folder preservation and drafts before explicit list removal',async()=>{
  const h=new Harness();await h.click('걷기 목록에서 제거');const dialog=h.dialog('프로젝트 목록에서 제거');
  expect(text(dialog)).toContain('모두 유지');expect(text(dialog)).toContain('미저장 편집 초안은 지워집니다');expect(text(dialog)).toContain(project.storage!.path);
  expect(text(dialog)).not.toContain('되돌릴 수 없습니다');expect(s.deleteProject).not.toHaveBeenCalled();
  await h.click('목록에서 제거');expect(s.deleteProject).toHaveBeenCalledExactlyOnceWith(project);expect(h.dialog('프로젝트 목록에서 제거')).toBeUndefined();
 });
});

describe('missing project folder cleanup dialog',()=>{
 it('fetches the missing list first and shows its names and paths before cleanup',async()=>{
  const h=new Harness();await h.click('없는 폴더 정리');expect(s.missingProjectFolders).toHaveBeenCalledOnce();expect(s.cleanupMissingFolders).not.toHaveBeenCalled();
  const dialog=h.dialog('없는 폴더 정리');expect(text(dialog)).toContain('걷기');expect(text(dialog)).toContain('/Volumes/Old/기사');expect(text(dialog)).toContain('실제 파일은 변경하지 않습니다');
  await h.click('1개 등록 정리');expect(s.cleanupMissingFolders).toHaveBeenCalledExactlyOnceWith(missing);expect(h.dialog('없는 폴더 정리')).toBeUndefined();
 });
 it('shows a friendly empty result and never offers cleanup when no folders are missing',async()=>{
  vi.mocked(s.missingProjectFolders).mockResolvedValue([]);const h=new Harness();await h.click('없는 폴더 정리');
  expect(text(h.dialog('없는 폴더 정리'))).toContain('정리할 없는 폴더가 없습니다');expect(nodes(h.tree).filter(n=>n.type==='button'&&text(n).includes('개 등록 정리'))).toEqual([]);
  await h.click('닫기');expect(s.cleanupMissingFolders).not.toHaveBeenCalled();expect(h.dialog('없는 폴더 정리')).toBeUndefined();
 });
 it('does not open a confirmation dialog after a failed preview',async()=>{
  vi.mocked(s.missingProjectFolders).mockResolvedValue(undefined);const h=new Harness();await h.click('없는 폴더 정리');expect(h.dialog('없는 폴더 정리')).toBeUndefined();expect(s.cleanupMissingFolders).not.toHaveBeenCalled();
 });
 it('rechecks after rejection and removes the action when the folder exists again',async()=>{
  vi.mocked(s.cleanupMissingFolders).mockResolvedValue(undefined);const h=new Harness();await h.click('없는 폴더 정리');await h.click('1개 등록 정리');expect(h.dialog('없는 폴더 정리')).toBeDefined();
  vi.mocked(s.missingProjectFolders).mockResolvedValue([]);await h.click('다시 확인');expect(s.missingProjectFolders).toHaveBeenCalledTimes(2);
  expect(nodes(h.tree).filter(n=>n.type==='button'&&text(n).includes('개 등록 정리'))).toEqual([]);expect(s.cleanupMissingFolders).toHaveBeenCalledOnce();
 });
 it('cancels without submitting cleanup',async()=>{
  const h=new Harness();await h.click('없는 폴더 정리');await h.click('취소');expect(s.cleanupMissingFolders).not.toHaveBeenCalled();
 });
});
