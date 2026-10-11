import {beforeEach,describe,expect,it,vi} from 'vitest';
import {readFileSync} from 'node:fs';
import type {ReactElement} from 'react';
import type {Studio} from '../src/useStudio';
import {defaultTransform,type Snapshot} from '../src/types';
import {CandidateLibrary} from '../src/CandidateLibrary';

// Component events; native focus trapping and rendering are checked separately in ego.
const hooks=vi.hoisted(()=>({current:null as any}));
vi.mock('react',async original=>({...await original<typeof import('react')>(),
 useState:(value:unknown)=>hooks.current.state(value),useRef:(value:unknown)=>hooks.current.ref(value),useEffect:vi.fn(),useId:()=> 'delete-test',
}));
import {EditStep} from '../src/AnimationWorkspace';
import {EditorDialog} from '../src/EditorDialog';
import {EditorCanvas} from '../src/Canvas';
import {ExportStep} from '../src/FinishSteps';
import {applyDraft} from '../src/draft';
import {Check,Select} from '../src/ui';
import {CandidateReview,CandidateRejection} from '../src/CandidateReview';
import {CandidateComparison} from '../src/CandidateComparison';

type Node=ReactElement<any>;
function nodes(tree:any):Node[]{
 if(Array.isArray(tree))return tree.flatMap(nodes);
 if(!tree?.props||tree.type===EditorDialog&&!tree.props.open)return [];
 return [tree,...nodes(tree.props.children)];
}
function text(tree:any):string{
 if(typeof tree==='string'||typeof tree==='number')return String(tree);
 if(Array.isArray(tree))return tree.map(text).join('');
 return tree?.props?text(tree.props.children):'';
}
class Harness{
 slots:any[]=[];cursor=0;tree:any;
 constructor(public s:Studio,public clipId='c',public component?:(props:any)=>any){this.render();}
 state(initial:unknown){const slot=this.slots[this.cursor++]??={value:initial};return [slot.value,(next:any)=>{slot.value=typeof next==='function'?next(slot.value):next;}];}
 ref(initial:unknown){return this.slots[this.cursor++]??={current:initial};}
 render(){this.cursor=0;hooks.current=this;this.tree=(this.component||EditStep)({s:this.s,clipId:this.clipId,onClip:(id:string)=>{this.clipId=id;}});hooks.current=null;}
 button(label:string){const n=nodes(this.tree).find(n=>n.type==='button'&&text(n)===label);if(!n)throw Error(`Missing button ${label}`);return n;}
 click(label:string){const n=this.button(label);expect(n.props.disabled).not.toBe(true);n.props.onClick();this.render();}
 dialog(){return nodes(this.tree).find(n=>n.type===EditorDialog&&n.props.title==='동작 삭제');}
 canvas(){return nodes(this.tree).find(n=>n.type===EditorCanvas)!;}
}
const project={projectId:'p',revision:3,outline:{enabled:false},assets:[],frames:[],references:[],alignmentGroups:[],alignments:{},clips:['c','other'].map(clipId=>({clipId,clipRevisionId:clipId+'-r',name:clipId==='c'?'초안 걷기':'완성 걷기',review:'approved',loop:true,defaultFps:8,occurrences:[]}))} as unknown as Snapshot;
let s:Studio;
beforeEach(()=>{
 s={snapshot:structuredClone(project),base:structuredClone(project),commands:[],redoCommands:[],busy:false,conflict:null,jobs:[],resolveId:(id:string)=>id,setNotice:vi.fn(),edit:vi.fn(op=>{s.commands.push({operation:op});s.snapshot=applyDraft(s.base!,s.commands);})} as unknown as Studio;
});
describe('clip reference picture',()=>{
 beforeEach(()=>{
  const references=['r1','r2'].map((id,i)=>({referenceRevisionId:id,identityAssetId:'a'+i,approval:'approved',fixedTraits:`힐러 ${i+1}, 금발`}));
  s.base={...s.base!,activeReferenceRevisionId:'r2',references,assets:references.map((r,i)=>({assetId:r.identityAssetId,url:`/${i}.png`,originalFilename:`${i}.png`})),clips:s.base!.clips.map(c=>({...c,referenceRevisionId:'r1'}))} as Snapshot;
  s.snapshot=structuredClone(s.base);
 });
 it('shows the linked image, opens it without edits, and switches using the original reference ID',()=>{
  const h=new Harness(s),picture=()=>nodes(h.tree).find(n=>n.type==='img'&&n.props.alt==='선택한 동작의 기준 그림');
  expect(picture()!.props.src).toBe('/0.png');h.click('크게 보기');
  const dialog=nodes(h.tree).find(n=>n.type===EditorDialog&&n.props.title==='동작에 연결된 기준 그림')!;
  expect(dialog.props.open).toBe(true);expect(text(dialog)).toContain('기준 1 · 힐러 1 · 0.png');expect(s.edit).not.toHaveBeenCalled();
  dialog.props.onClose();h.render();
  const select=nodes(h.tree).find(n=>n.type===Select&&n.props.label==='동작에 사용할 승인 기준')!;
  expect(text(select)).toContain('기준 2 · 힐러 2 · 1.png');select.props.onChange({target:{value:'r2'}});h.render();
  expect(s.edit).toHaveBeenCalledExactlyOnceWith({type:'updateClip',clipId:'c',changes:{referenceRevisionId:'r2'}});
  expect(picture()!.props.src).toBe('/1.png');expect(s.snapshot!.clips[0].review).not.toBe('approved');
 });
 it('never substitutes the active image for an unlinked clip',()=>{
  s.snapshot!.clips[0].referenceRevisionId=null;const h=new Harness(s);
  expect(nodes(h.tree).some(n=>n.type==='img'&&n.props.alt==='선택한 동작의 기준 그림')).toBe(false);
  expect(text(h.tree)).toContain('이 동작에 사용할 승인 기준을 선택하세요.');
 });
 it('lets review comparison change images without changing the clip reference',()=>{
  const frame={frameVersionId:'f',imageAssetId:'a0',review:'pending'};
  const h=new Harness(s,'c',({s})=>CandidateComparison({s,frame:frame as any,clip:s.snapshot!.clips[0]}));
  const select=nodes(h.tree).find(n=>n.type===Select&&n.props.label==='나란히 비교할 승인 기준')!;
  select.props.onChange({target:{value:'r2'}});h.render();
  const image=nodes(h.tree).find(n=>n.type==='img'&&n.props.alt==='승인된 외형 기준')!;
  expect(image.props.src).toBe('/1.png');expect(s.edit).not.toHaveBeenCalled();expect(s.snapshot!.clips[0].referenceRevisionId).toBe('r1');
 });
 it('compares both original images in a dialog with shared reference and zoom, without project edits',()=>{
  const frame={frameVersionId:'f',imageAssetId:'a0',review:'pending'};
  s.snapshot!.assets=s.snapshot!.assets.map(a=>({...a,width:32,height:48}));
  const before=structuredClone(s.snapshot);
  const h=new Harness(s,'c',({s})=>CandidateComparison({s,frame:frame as any,clip:s.snapshot!.clips[0]}));
  h.click('두 이미지 크게 비교');
  const dialog=()=>nodes(h.tree).find(n=>n.type===EditorDialog&&n.props.title==='승인 기준과 후보 크게 비교');
  expect(nodes(dialog()).filter(n=>n.type==='img').map(n=>n.props.src)).toEqual(['/0.png','/0.png']);
  nodes(dialog()).find(n=>n.type===Select&&n.props.label==='나란히 비교할 승인 기준')!.props.onChange({target:{value:'r2'}});h.render();
  nodes(dialog()).find(n=>n.type===Select&&n.props.label==='비교 이미지 배율')!.props.onChange({target:{value:'2'}});h.render();
  const images=nodes(dialog()).filter(n=>n.type==='img');
  expect(images.map(n=>n.props.src)).toEqual(['/1.png','/0.png']);
  expect(images.map(n=>n.props.style)).toEqual([{width:64,height:96},{width:64,height:96}]);
  dialog()!.props.onClose();h.render();expect(dialog()).toBeUndefined();
  const selects=nodes(h.tree).filter(n=>n.type===Select);
  expect(selects.find(n=>n.props.label==='나란히 비교할 승인 기준')!.props.value).toBe('r2');
  expect(selects.find(n=>n.props.label==='비교 이미지 배율')!.props.value).toBe('2');
  expect(s.edit).not.toHaveBeenCalled();expect(s.snapshot).toEqual(before);
 });
 it('keeps the comparison open and its settings while moving frames',()=>{
  let frame={frameVersionId:'f1',imageAssetId:'a0',review:'pending',reviewReason:'첫 후보 사유'};
  const navigation={label:'재생 슬롯 1 / 2',next:vi.fn(()=>{frame={...frame,frameVersionId:'f2',imageAssetId:'a1',reviewReason:'두 번째 후보 사유'};navigation.label='재생 슬롯 2 / 2';})};
  const h=new Harness(s,'c',({s})=>CandidateComparison({s,frame:frame as any,clip:s.snapshot!.clips[0],navigation}));
  h.click('두 이미지 크게 비교');
  const select=nodes(h.tree).find(n=>n.type===Select&&n.props.label==='비교 이미지 배율')!;
  select.props.onChange({target:{value:'2'}});
  h.render();
  h.click('다음 프레임');
  const dialog=nodes(h.tree).find(n=>n.type===EditorDialog&&n.props.title==='승인 기준과 후보 크게 비교')!;
  expect(dialog).toBeDefined();expect(text(dialog)).toContain('재생 슬롯 2 / 2');
  expect(nodes(dialog).filter(n=>n.type==='img').map(n=>n.props.src)).toEqual(['/0.png','/1.png']);
  expect(nodes(dialog).find(n=>n.type===Select&&n.props.label==='비교 이미지 배율')!.props.value).toBe('2');
  expect(s.edit).not.toHaveBeenCalled();
 });
 it('resets review input per candidate while keeping the comparison widget mounted',()=>{
  const frame1={frameVersionId:'f1',imageAssetId:'a0',review:'pending',reviewReason:'첫 후보 사유'},frame2={...frame1,frameVersionId:'f2',reviewReason:'두 번째 후보 사유'};
  const render=(frame:any)=>CandidateReview({s,frame,clip:s.snapshot!.clips[0]});
  const first=render(frame1),second=render(frame2);
  const reason=(tree:any)=>nodes(tree).find(n=>n.type===CandidateRejection)!;
  const comparison=(tree:any)=>nodes(tree).find(n=>n.type===CandidateComparison)!;
  expect(reason(first).key).toBe('f1');expect(reason(second).key).toBe('f2');
  expect(comparison(first).key).toBe(comparison(second).key);
  const h=new Harness(s,'c',()=>CandidateRejection({s,frame:frame2 as any}));
  expect(nodes(h.tree).find(n=>n.type==='textarea')!.props.value).toBe('두 번째 후보 사유');
  h.click('사유 기록·후보 거절');
  expect(s.edit).toHaveBeenCalledExactlyOnceWith({type:'setFrameReview',frameVersionId:'f2',review:'rejected',reason:'두 번째 후보 사유'});
 });
 it('uses playback slots including repeated candidates and stops at each end without editing the project',()=>{
  s.snapshot!.frames=[{frameVersionId:'f1',imageAssetId:'a0'},{frameVersionId:'f2',imageAssetId:'a1'}] as any;
  s.snapshot!.clips[0].occurrences=['f1','f1','f2'].map((frameVersionId,i)=>({occurrenceId:`o${i}`,frameVersionId,durationMs:125,transform:defaultTransform()})) as any;
  const h=new Harness(s);
  const review=()=>nodes(h.tree).find(n=>n.type===CandidateReview)!;
  const key=review().key;expect(review().props.navigation.previous).toBeUndefined();
  review().props.navigation.next();h.render();expect(review().props.navigation.label).toBe('재생 슬롯 2 / 3');expect(review().props.frame.frameVersionId).toBe('f1');
  review().props.navigation.next();h.render();expect(review().props.frame.frameVersionId).toBe('f2');expect(review().props.navigation.next).toBeUndefined();
  review().props.navigation.previous();h.render();expect(review().props.navigation.label).toBe('재생 슬롯 2 / 3');
  expect(review().key).toBe(key);expect(s.edit).not.toHaveBeenCalled();
 });
 it('navigates available library candidates and skips hidden candidates',()=>{
  s.snapshot!.frames=[{frameVersionId:'f1',imageAssetId:'a0'},{frameVersionId:'hidden',imageAssetId:'a0',hidden:true},{frameVersionId:'f3',imageAssetId:'a1'}] as any;
  const h=new Harness(s);nodes(h.tree).find(n=>n.type===CandidateLibrary)!.props.onSelect('f1');h.render();
  const review=()=>nodes(h.tree).find(n=>n.type===CandidateReview)!;
  expect(review().props.navigation.label).toBe('후보 1 / 2');
  review().props.navigation.next();h.render();expect(review().props.frame.frameVersionId).toBe('f3');expect(review().props.navigation.next).toBeUndefined();
  review().props.navigation.previous();h.render();expect(review().props.frame.frameVersionId).toBe('f1');expect(review().props.navigation.previous).toBeUndefined();
  expect(s.edit).not.toHaveBeenCalled();
 });
 it('can leave a selected hidden candidate after turning the hidden filter off',()=>{
  s.snapshot!.frames=[{frameVersionId:'f1',imageAssetId:'a0'},{frameVersionId:'hidden',imageAssetId:'a0',hidden:true},{frameVersionId:'f3',imageAssetId:'a1'}] as any;
  const h=new Harness(s),toggle=()=>nodes(h.tree).find(n=>n.type===Check&&n.props.label==='숨긴 후보 포함')!;
  toggle().props.onChange(true);h.render();
  nodes(h.tree).find(n=>n.type===CandidateLibrary)!.props.onSelect('hidden');h.render();
  toggle().props.onChange(false);h.render();
  const review=()=>nodes(h.tree).find(n=>n.type===CandidateReview)!;
  expect(review().props.navigation.label).toBe('후보 2 / 3');
  review().props.navigation.next();h.render();
  expect(review().props.frame.frameVersionId).toBe('f3');expect(review().props.navigation.label).toBe('후보 2 / 2');
  review().props.navigation.previous();h.render();expect(review().props.frame.frameVersionId).toBe('f1');
  expect(s.edit).not.toHaveBeenCalled();
 });
});
describe('library clip deletion',()=>{
 it('sizes the confirmation to its content instead of stretching between modal insets',()=>{
  const css=readFileSync(new URL('../src/editor-shell.css',import.meta.url),'utf8');
  const rule=css.match(/\.editor-tool\.project-delete-dialog\{([^}]+)\}/)![1];
  expect(rule).toContain('height:fit-content;');expect(rule).toContain('max-height:calc(100dvh - 24px)');
 });
 it('requires confirmation and cancel leaves the snapshot untouched',()=>{
  const h=new Harness(s),before=structuredClone(s.snapshot);h.click('선택 동작 삭제');
  expect(text(h.dialog())).toContain('초안 걷기');expect(text(h.dialog())).toContain('0슬롯');
  expect(text(h.dialog())).toContain('후보·원본은 유지됩니다');expect(h.button('취소').props.autoFocus).toBe(true);
  expect(s.edit).not.toHaveBeenCalled();h.click('취소');expect(h.dialog()).toBeUndefined();expect(s.snapshot).toEqual(before);
 });
 it('deletes the confirmed target even if selection changes and preserves the other clip',()=>{
  const h=new Harness(s);h.click('선택 동작 삭제');h.clipId='other';h.render();h.click('삭제 초안에 적용');
  expect(s.edit).toHaveBeenCalledExactlyOnceWith({type:'deleteClip',clipId:'c'});expect(h.dialog()).toBeUndefined();
  expect(s.snapshot!.clips).toEqual([project.clips[1]]);expect(h.canvas().props.clip.clipId).toBe('other');
 });
 it('falls back to the remaining clip, and undo restores the prior selection',()=>{
  const h=new Harness(s);h.click('선택 동작 삭제');h.click('삭제 초안에 적용');expect(h.canvas().props.clip.clipId).toBe('other');
  s.commands=[];s.snapshot=applyDraft(project,[]);h.render();expect(h.canvas().props.clip.clipId).toBe('c');
 });
 it('handles deleting the last clip with an empty library and preserves candidates',()=>{
  s.base={...structuredClone(project),clips:[project.clips[0]]};s.snapshot=structuredClone(s.base);const h=new Harness(s);
  h.click('선택 동작 삭제');h.click('삭제 초안에 적용');
  expect(h.canvas().props.clip).toBeUndefined();expect(h.button('선택 동작 삭제').props.disabled).toBe(true);
  expect(text(h.tree)).toContain('아직 동작이 없습니다.');expect(h.button('새 동작')).toBeDefined();
 });
 it.each(['busy','conflict'])('blocks deletion while %s, including an already open dialog',reason=>{
  const h=new Harness(s);h.click('선택 동작 삭제');if(reason==='busy')s.busy=true;else s.conflict=project;h.render();
  expect(h.button('선택 동작 삭제').props.disabled).toBe(true);expect(h.button('삭제 초안에 적용').props.disabled).toBe(true);
  h.button('삭제 초안에 적용').props.onClick();expect(s.edit).not.toHaveBeenCalled();
 });
 it('drops a deleted clip from open export selections and blocks bake after the last deletion',()=>{
  s.exports=[];s.service={worker:'ready'} as Studio['service'];s.job=vi.fn();
  const h=new Harness(s,'c',ExportStep);s.snapshot!.clips=s.snapshot!.clips.filter(c=>c.clipId!=='c');h.render();
  expect(text(h.tree)).not.toContain('출력할 동작을 찾을 수 없습니다.');h.click('확정 미리보기 만들기');
  expect(s.job).toHaveBeenCalledExactlyOnceWith('bake',[],{clipIds:['other'],clipRevisionIds:['other-r']});
  s.snapshot!.clips=[];h.render();expect(h.button('확정 미리보기 만들기').props.disabled).toBe(true);
 });
});
