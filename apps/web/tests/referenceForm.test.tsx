import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import type {ReactElement} from 'react';
import type {Snapshot} from '../src/types';
import type {Studio} from '../src/useStudio';

// Component state only; layout and real typing are checked separately in ego.
const hooks=vi.hoisted(()=>({current:null as any}));
vi.mock('react',async original=>({...await original<typeof import('react')>(),
 useState:(value:unknown)=>hooks.current.state(value),useRef:(value:unknown)=>hooks.current.ref(value),
 useEffect:(fn:()=>void|(()=>void),deps?:unknown[])=>hooks.current.effect(fn,deps),useId:()=>'reference-test',
}));
import {ReferenceStep,hasUnstoredReferenceInput} from '../src/ReferenceStep';

type Node=ReactElement<any>;
// Walk element-valued props too: the form lives in SourceTool settings and SourcePane footer props.
function nodes(tree:any):Node[]{
 if(Array.isArray(tree))return tree.flatMap(nodes);
 if(!tree?.props)return [];
 return [tree,...Object.values(tree.props).flatMap(v=>Array.isArray(v)||(v as any)?.props?nodes(v):[])];
}
function text(tree:any):string{
 if(typeof tree==='string'||typeof tree==='number')return String(tree);
 if(Array.isArray(tree))return tree.map(text).join('');
 return tree?.props?text(tree.props.children):'';
}
class Harness{
 slots:any[]=[];cursor=0;tree:any;effects:any[]=[];effectCursor=0;pending:(()=>void)[]=[];
 constructor(public s:Studio,public initialReferenceRevisionId?:string){this.render();}
 state(initial:unknown){const slot=this.slots[this.cursor++]??={value:typeof initial==='function'?(initial as ()=>unknown)():initial};return [slot.value,(next:any)=>{slot.value=typeof next==='function'?next(slot.value):next;}];}
 ref(initial:unknown){return this.slots[this.cursor++]??={current:initial};}
 // Effects run after render only when their deps change, with the previous cleanup first, as in React.
 effect(fn:()=>any,deps?:unknown[]){const i=this.effectCursor++,slot=this.effects[i];if(slot&&deps&&deps.every((d,k)=>Object.is(d,slot.deps[k])))return;this.pending.push(()=>{slot?.cleanup?.();this.effects[i]={deps,cleanup:fn()};});}
 unmount(){this.effects.forEach(e=>e?.cleanup?.());this.effects=[];}
 render(){this.cursor=0;this.effectCursor=0;this.pending=[];hooks.current=this;this.tree=ReferenceStep({s:this.s,initialReferenceRevisionId:this.initialReferenceRevisionId});hooks.current=null;const run=this.pending;this.pending=[];run.forEach(fn=>fn());if(run.length)this.render();}
 fixed(){return nodes(this.tree).find(n=>n.type==='textarea'&&n.props.placeholder?.includes('짧은 은색 머리'))!;}
 type(value:string){this.fixed().props.onChange({target:{value}});this.render();}
 button(label:string){return nodes(this.tree).find(n=>n.type==='button'&&text(n)===label);}
}
const storage=new Map<string,string>();
const key=(id:string)=>`frame-room-reference-form:${id}`;
const project=(id='p'):Snapshot=>({projectId:id,revision:4,assets:[{assetId:'a1',url:'/a1.png'},{assetId:'a2',url:'/a2.png'}],references:[{referenceRevisionId:'r1',identityAssetId:'a1',styleAssetIds:[],poseAssetIds:[],fixedTraits:'은색 머리',allowedChanges:'',forbiddenTransfers:'',facing:'right',approval:'draft'}],activeReferenceRevisionId:null,clips:[],frames:[]} as unknown as Snapshot);
let s:Studio;
const listeners=new Set<unknown>();
beforeEach(()=>{
 storage.clear();listeners.clear();
 vi.stubGlobal('localStorage',{getItem:(k:string)=>storage.get(k)??null,setItem:(k:string,v:string)=>storage.set(k,v),removeItem:(k:string)=>storage.delete(k)});
 vi.stubGlobal('window',{addEventListener:(t:string,f:unknown)=>t==='beforeunload'&&listeners.add(f),removeEventListener:(t:string,f:unknown)=>listeners.delete(f)});
 s={snapshot:project(),commands:[],busy:false,mutation:vi.fn()} as unknown as Studio;
});
afterEach(()=>vi.unstubAllGlobals());

describe('unsaved reference form input',()=>{
 it('marks typed input as unsaved and keeps it only under this project key',()=>{
  const h=new Harness(s);expect(h.button('입력 버리기')).toBeUndefined();expect(storage.has(key('p'))).toBe(false);
  h.type('은색 머리, 붉은 목도리');
  expect(text(nodes(h.tree).find(n=>n.type==='p'&&n.props.role==='status'))).toContain('저장하지 않은 기준 입력이 있습니다');
  expect(JSON.parse(storage.get(key('p'))!)).toMatchObject({editingReferenceId:'r1',form:{fixed:'은색 머리, 붉은 목도리',identity:'a1'}});
  expect([...storage.keys()]).toEqual([key('p')]);expect(s.mutation).not.toHaveBeenCalled();
 });
 it('restores the input after reopening, even when a clip reference would load another form',()=>{
  new Harness(s).type('새 특징');
  s.snapshot=project();const h=new Harness(s,'r1');
  expect(h.fixed().props.value).toBe('새 특징');expect(text(nodes(h.tree).find(n=>n.type==='p'&&n.props.role==='status'))).toContain('저장하지 않은 기준 입력이 있습니다');
  expect(new Harness({...s,snapshot:project('other')} as Studio).fixed().props.value).toBe('은색 머리');
 });
 it('drops stored IDs that no longer exist in the project',()=>{
  storage.set(key('p'),JSON.stringify({editingReferenceId:'gone',form:{name:'옛 이름',identity:'gone',styles:['a2','gone'],poses:['gone'],fixed:'남은 입력',allowed:'',forbidden:'',facing:'left'}}));
  const h=new Harness(s),settings=nodes(h.tree).find(n=>n.props.label==='편집할 저장 기준');
  expect(settings?.props.value).toBe('');expect(h.fixed().props.value).toBe('남은 입력');
  expect(JSON.parse(storage.get(key('p'))!).form).toMatchObject({identity:'a1',styles:['a2'],poses:[],facing:'left'});
 });
 it('discards the input on request and clears the browser copy',()=>{
  const h=new Harness(s);h.type('버릴 입력');h.button('입력 버리기')!.props.onClick();h.render();
  expect(h.fixed().props.value).toBe('은색 머리');expect(storage.has(key('p'))).toBe(false);expect(h.button('입력 버리기')).toBeUndefined();
 });
 it('clears the browser copy only after the explicit save returns the new reference',async()=>{
  const h=new Harness(s);h.type('저장할 특징');
  vi.mocked(s.mutation).mockImplementation(async(_path,body:any)=>{
   s.snapshot={...s.snapshot!,revision:5,references:[...s.snapshot!.references,{...body.reference,referenceRevisionId:'r2',approval:'draft'}]};return {referenceRevisionId:'r2'};
  });
  expect(storage.has(key('p'))).toBe(true);
  await h.button('새 기준 저장')!.props.onClick();h.render();
  expect(s.mutation).toHaveBeenCalledOnce();expect(storage.has(key('p'))).toBe(false);expect(h.button('입력 버리기')).toBeUndefined();
 });
 it('does not flag a new form opened before any asset existed',()=>{
  s.snapshot={...project(),assets:[],references:[]} as unknown as Snapshot;const h=new Harness(s);
  s.snapshot={...project(),references:[]} as unknown as Snapshot;h.render();expect(h.button('입력 버리기')).toBeUndefined();expect(storage.size).toBe(0);
 });
 it('warns, keeps the input and blocks leaving when the browser cannot keep it',()=>{
  vi.stubGlobal('localStorage',{getItem:()=>null,setItem:()=>{throw new DOMException('quota','QuotaExceededError');},removeItem:()=>{}});
  const h=new Harness(s);h.type('보관 실패 입력');
  const notice=nodes(h.tree).find(n=>n.type==='p'&&(n.props.role==='alert'||n.props.role==='status'))!;
  expect(notice.props.role).toBe('alert');expect(text(notice)).toContain('보관하지 못했습니다');expect(text(notice)).not.toContain('임시 보관되며');
  expect(h.fixed().props.value).toBe('보관 실패 입력');expect(hasUnstoredReferenceInput()).toBe(true);expect(listeners.size).toBe(1);
  h.type('보관 실패 입력 2');expect(listeners.size).toBe(1);
  h.button('입력 버리기')!.props.onClick();h.render();expect(hasUnstoredReferenceInput()).toBe(false);expect(listeners.size).toBe(0);
  h.type('다시 입력');expect(hasUnstoredReferenceInput()).toBe(true);h.unmount();expect(hasUnstoredReferenceInput()).toBe(false);expect(listeners.size).toBe(0);
 });
});
