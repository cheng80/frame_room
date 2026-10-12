import {afterEach,describe,expect,it,vi} from 'vitest';
import type {ReactElement} from 'react';
import type {Asset,Snapshot} from '../src/types';
import type {Studio} from '../src/useStudio';

const state=vi.hoisted(()=>({hooks:null as any}));
vi.mock('react',async original=>({...await original<typeof import('react')>(),useState:(value:unknown)=>state.hooks.state(value)}));
vi.mock('../src/VideoStep',()=>({VideoStep:()=>null}));
import {AssetNameInput} from '../src/AssetNameInput';
import {AssetsStep} from '../src/SourceSteps';
import {EditorDialog} from '../src/EditorDialog';
import {SpriteImage} from '../src/SpriteViewport';
import {applyDraft} from '../src/draft';

type Node=ReactElement<any>;
function nodes(tree:any):Node[]{if(Array.isArray(tree))return tree.flatMap(nodes);if(!tree?.props)return [];if(tree.type===EditorDialog&&!tree.props.open)return [];return [tree,...nodes(tree.props.children),...nodes(tree.props.actions),...nodes(tree.props.preview),...nodes(tree.props.settings),...nodes(tree.props.toolbar)];}
function text(tree:any):string{if(typeof tree==='string'||typeof tree==='number')return String(tree);if(Array.isArray(tree))return tree.map(text).join('');return tree?.props?text(tree.props.children):'';}
function nameInput(element:any){return element.type(element.props);}
class Harness {
 slots:any[]=[];cursor=0;tree:any;s:Studio;
 constructor(s:Studio){this.s=s;this.render();}
 state(initial:unknown){const slot=this.slots[this.cursor++]??={value:initial};return [slot.value,(next:any)=>{slot.value=typeof next==='function'?next(slot.value):next;}];}
 render(){this.cursor=0;state.hooks=this;this.tree=AssetsStep({s:this.s,onNext:vi.fn(),onGenerate:vi.fn()});state.hooks=null;}
 find(fn:(n:Node)=>boolean,tree=this.tree){const n=nodes(tree).find(fn);if(!n)throw new Error('Expected React element not found');return n;}
 click(label:string){const n=this.find(x=>x.type==='button'&&x.props['aria-label']===label);n.props.onClick();this.render();}
 get dialog(){return nodes(this.tree).find(n=>n.type===EditorDialog&&n.props.title==='자료 이미지 크게 보기');}
}

const asset=(overrides:Partial<Asset>={}):Asset=>({assetId:'a',sha256:'sha',decodedHash:'decoded',originalFilename:'sprite.png',mediaType:'image/png',width:32,height:24,role:'source',alphaStats:{transparent:1,partial:2,opaque:3},provenance:{kind:'imported'},url:'/assets/a.png',...overrides});
function fixture(assets:Asset[]):Snapshot{return {projectId:'p',schemaVersion:1,revision:2,name:'프로젝트',characterName:'캐릭터',createdAt:'',updatedAt:'',assets,references:[],activeReferenceRevisionId:null,frames:[],alignmentGroups:[],alignments:{},clips:[],outline:{},generationSettings:{},journal:[],generations:[]} as unknown as Snapshot;}
const studio=(snapshot:Snapshot,extra:Record<string,unknown>={})=>({snapshot,edit:vi.fn(),save:vi.fn(),commands:[],redoCommands:[],busy:false,conflict:null,...extra} as unknown as Studio);

describe('asset image names and preview',()=>{
 it('trims edits on blur and leaves internal spaces and source metadata untouched',()=>{
  const original=asset(),before=structuredClone(original),s=studio(fixture([original]));
  const input=nameInput(AssetNameInput({s,asset:original})),target={value:'  새 자료 이름  '};
  input.props.onBlur({currentTarget:target});
  expect(s.edit).toHaveBeenCalledExactlyOnceWith({type:'renameAsset',assetId:'a',name:'새 자료 이름'});
  expect(target.value).toBe('새 자료 이름');expect(original).toEqual(before);expect(input.props.maxLength).toBe(200);
 });
 it('ignores unchanged names and allows clearing to restore the original filename label',()=>{
  const item=asset({name:'이름'}),s=studio(fixture([item])),input=nameInput(AssetNameInput({s,asset:item}));
  input.props.onBlur({currentTarget:{value:'이름'}});expect(s.edit).not.toHaveBeenCalled();
  input.props.onBlur({currentTarget:{value:'   '}});expect(s.edit).toHaveBeenCalledExactlyOnceWith({type:'renameAsset',assetId:'a',name:''});
 });
 it('cancels Escape and ignores Enter during Korean composition',()=>{
  const s=studio(fixture([asset({name:'이전'})])),input=nameInput(AssetNameInput({s,asset:s.snapshot!.assets[0]})),target={value:'새 이름',blur:vi.fn()},preventDefault=vi.fn();
  input.props.onKeyDown({key:'Enter',nativeEvent:{isComposing:true},currentTarget:target,preventDefault});expect(target.blur).not.toHaveBeenCalled();
  input.props.onKeyDown({key:'Escape',currentTarget:target});expect(target.value).toBe('이전');expect(target.blur).toHaveBeenCalledOnce();
  input.props.onKeyDown({key:'Enter',nativeEvent:{isComposing:false},currentTarget:target,preventDefault});expect(target.blur).toHaveBeenCalledTimes(2);expect(preventDefault).toHaveBeenCalledOnce();
 });
 it.each([{busy:true},{conflict:{revision:3}}])('disables and does not commit while busy or conflicted',options=>{
  const s=studio(fixture([asset()]),options),input=nameInput(AssetNameInput({s,asset:s.snapshot!.assets[0]}));
  expect(input.props.disabled).toBe(true);input.props.onBlur({currentTarget:{value:'수정'}});expect(s.edit).not.toHaveBeenCalled();
 });
 it('labels legacy and custom names and opens previews from primary and folded video cards',()=>{
  const legacy=asset(),custom=asset({assetId:'custom',name:'  직접 이름  ',originalFilename:'custom.png'});
  const kinds=['video-input','video-frame-raw','video-frame'];
  const videos=kinds.map((kind,index)=>asset({assetId:`v${index}`,originalFilename:`video-${index}.png`,provenance:{kind}}));
  const s=studio(fixture([legacy,custom,...videos])),h=new Harness(s);
  expect(nodes(h.tree).some(n=>n.props['aria-label']==='자료 이미지 크게 보기 · sprite.png')).toBe(true);
  expect(nodes(h.tree).some(n=>n.props['aria-label']==='자료 이미지 크게 보기 · 직접 이름')).toBe(true);
  const original=structuredClone(s.snapshot!.assets);
  h.click('자료 이미지 크게 보기 · sprite.png');
  expect(h.dialog).toBeDefined();expect(text(h.dialog)).toContain('원본 파일: sprite.png · 32 × 24');expect(text(h.dialog)).toContain('가져온 원본');expect(nodes(h.dialog).some(n=>n.type===SpriteImage&&n.props.src==='/assets/a.png'&&n.props.width===32&&n.props.height===24)).toBe(true);
  h.dialog!.props.onClose();h.render();expect(h.dialog).toBeUndefined();
  const details=h.find(n=>n.type==='details'&&String(n.props.className).includes('source-tool-video-results'));
  for(const video of videos){
   h.click(`자료 이미지 크게 보기 · ${video.originalFilename}`);
   expect(h.dialog).toBeDefined();expect(nodes(h.dialog).some(n=>n.type===SpriteImage&&n.props.src===video.url)).toBe(true);
   h.dialog!.props.onClose();h.render();
  }
  expect(text(details)).toContain('영상 처리 결과');expect(s.snapshot!.assets).toEqual(original);
 });
 it('keeps the selected preview id and refreshes dialog labels when the snapshot name changes',()=>{
  const item=asset({name:'처음'}),snapshot=fixture([item]),s=studio(snapshot),h=new Harness(s);
  h.click('자료 이미지 크게 보기 · 처음');expect(text(h.dialog)).toContain('처음');
  s.snapshot=fixture([asset({...item,name:'갱신된 이름'})]);h.render();
  expect(h.dialog).toBeDefined();expect(text(h.dialog)).toContain('갱신된 이름');expect(text(h.dialog)).toContain('원본 파일: sprite.png');
 });
 it('renames only asset metadata and undo/redo preserves the complete project snapshot',()=>{
  const base=fixture([asset()]),before=structuredClone(base),commands=[{operation:{type:'renameAsset',assetId:'a',name:'  변경 이름  '}}] as any;
  const renamed=applyDraft(base,commands);expect(renamed.assets[0].name).toBe('변경 이름');expect(base).toEqual(before);
  expect({...renamed,assets:before.assets}).toEqual(before);
  const undo=applyDraft(base,commands.slice(0,-1));expect(undo).toEqual(before);
  expect(applyDraft(undo,commands)).toEqual(renamed);
 });
});

afterEach(()=>{state.hooks=null;});
