import {describe,expect,it,vi} from 'vitest';
import type {ReactElement} from 'react';
import type {Health,Provider} from '../src/types';

const hooks=vi.hoisted(()=>({current:null as any}));
vi.mock('react',async original=>({...await original<typeof import('react')>(),useState:(value:unknown)=>hooks.current.state(value),useEffect:vi.fn(),useRef:vi.fn(),useId:()=> 'provider-test'}));
import {ProviderConnections} from '../src/ProviderConnections';
import {EditorDialog} from '../src/EditorDialog';

type Node=ReactElement<any>;
function nodes(tree:any):Node[]{if(Array.isArray(tree))return tree.flatMap(nodes);if(!tree?.props||tree.type===EditorDialog&&!tree.props.open)return [];return [tree,...nodes(tree.props.children),...nodes(tree.props.actions)];}
function text(tree:any):string{if(typeof tree==='string'||typeof tree==='number')return String(tree);if(Array.isArray(tree))return tree.map(text).join('');return tree?.props?text(tree.props.children):'';}
class Harness{
 slots:any[]=[];cursor=0;tree:any;
 constructor(public props:any){this.render();}
 state(initial:unknown){const slot=this.slots[this.cursor++]??={value:initial};return [slot.value,(next:any)=>{slot.value=typeof next==='function'?next(slot.value):next;}];}
 render(){this.cursor=0;hooks.current=this;this.tree=ProviderConnections(this.props);hooks.current=null;}
 button(label:string){const n=nodes(this.tree).find(n=>n.type==='button'&&text(n)===label);if(!n)throw Error(`Missing button ${label}`);return n;}
 click(label:string){this.button(label).props.onClick();this.render();}
 dialog(){return nodes(this.tree).find(n=>n.type===EditorDialog);}
}
const health={api:'ready',worker:'ready',sessionToken:''} as Health;
const gpt:Provider={providerId:'codex',available:true,loginReady:true,defaultModel:'gpt-default',models:['gpt-image']};
const grok:Provider={providerId:'grok-video',available:true,loginReady:true,model:'grok-video-model'};
const setup=(props:Partial<Harness['props']>={})=>new Harness({providers:[gpt,grok],service:health,checking:false,error:'',onCheck:vi.fn(),...props});
describe('ProviderConnections',()=>{
 it('shows mixed ready and explicitly unavailable providers',()=>{
  const h=setup({providers:[gpt,{...grok,available:false}]});const badges=nodes(h.tree).filter(n=>String(n.props.className).startsWith('provider-connection '));
  expect(badges.map(n=>[n.props.className,text(n)])).toEqual([['provider-connection ready','GPT 이미지 · 연결 준비됨'],['provider-connection warning','Grok 영상 · 연결 확인 필요']]);
 });
 it('treats missing providers and unknown fields as unverifiable',()=>{
  const h=setup({providers:[{providerId:'codex',available:true},grok]});
  expect(nodes(h.tree).filter(n=>String(n.props.className).startsWith('provider-connection ')).map(n=>n.props.className)).toEqual(['provider-connection unknown','provider-connection ready']);
  const missing=setup({providers:[gpt]});expect(nodes(missing.tree).find(n=>n.props.className==='provider-connection unknown')).toBeDefined();
 });
 it('ignores cached ready providers while the service is offline',()=>{
  const h=setup({service:{...health,api:'offline'}});expect(nodes(h.tree).filter(n=>String(n.props.className).startsWith('provider-connection ')).every(n=>n.props.className==='provider-connection unknown')).toBe(true);
 });
 it('shows checking first and disables recheck while checking',()=>{
  const h=setup({checking:true,error:'offline'});expect(nodes(h.tree).filter(n=>String(n.props.className).startsWith('provider-connection ')).every(n=>n.props.className==='provider-connection checking')).toBe(true);
  h.click('GPT 이미지 · 확인 중');expect(h.button('연결 다시 확인').props.disabled).toBe(true);
 });
 it('keeps past success separate from current login and shows provider details',()=>{
  const h=setup({providers:[{...gpt,available:false,loginReady:false,lastSuccess:'yesterday',reason:'다시 로그인하세요',models:[{id:'image-id',name:'이미지 모델'}]},grok]});
  h.click('GPT 이미지 · 연결 확인 필요');const dialog=h.dialog();expect(dialog?.props.title).toBe('모델 연결 확인');
  expect(text(dialog)).toContain('최근 실제 생성 이력성공 이력 있음');expect(text(dialog)).toContain('로그인 상태확인 필요');expect(text(dialog)).toContain('다시 로그인하세요');expect(text(dialog)).toContain('gpt-default, 이미지 모델 (image-id)');expect(text(dialog)).toContain('로그인 확인은 실제 생성 성공이나 남은 사용량을 보장하지 않습니다.');
 });
 it('shows errors and marks provider status unverifiable',()=>{
  const h=setup({providers:[{...gpt,available:false,loginReady:false}],error:'상태 요청 실패'});
  expect(nodes(h.tree).filter(n=>String(n.props.className).startsWith('provider-connection ')).map(n=>n.props.className)).toEqual(['provider-connection unknown','provider-connection unknown']);
  h.click('GPT 이미지 · 확인 불가');expect(text(h.dialog())).toContain('상태 요청 실패');expect(text(h.dialog())).toContain('로그인 상태확인 불가');
 });
 it('calls onCheck once and opens and closes the details dialog',()=>{
  const onCheck=vi.fn(),h=setup({onCheck});h.click('GPT 이미지 · 연결 준비됨');expect(h.dialog()).toBeDefined();
  h.click('연결 다시 확인');expect(onCheck).toHaveBeenCalledOnce();
  h.dialog()!.props.onClose();h.render();expect(h.dialog()).toBeUndefined();
 });
 it('handles an omitted providers array safely',()=>{
  const h=setup({providers:undefined});expect(nodes(h.tree).filter(n=>String(n.props.className).startsWith('provider-connection ')).map(n=>n.props.className)).toEqual(['provider-connection unknown','provider-connection unknown']);
 });
});
