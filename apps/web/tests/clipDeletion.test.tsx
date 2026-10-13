import {beforeEach,describe,expect,it,vi} from 'vitest';
import {readFileSync} from 'node:fs';
import type {ReactElement} from 'react';
import type {Studio} from '../src/useStudio';
import {defaultTransform,type Snapshot} from '../src/types';
import {CandidateLibrary} from '../src/CandidateLibrary';

// Component events; native focus trapping and rendering are checked separately in ego.
const hooks=vi.hoisted(()=>({current:null as any}));
vi.mock('react',async original=>({...await original<typeof import('react')>(),
 useState:(value:unknown)=>hooks.current.state(value),useRef:(value:unknown)=>hooks.current.ref(value),useEffect:vi.fn(),useCallback:(fn:Function)=>fn,useId:()=> 'delete-test',
}));
import {EditStep} from '../src/AnimationWorkspace';
import {EditorDialog} from '../src/EditorDialog';
import {EditorCanvas} from '../src/Canvas';
import {ExportStep} from '../src/FinishSteps';
import {applyDraft} from '../src/draft';
import {Check,Select} from '../src/ui';
import {CandidateReview,CandidateRejection} from '../src/CandidateReview';
import {CandidateComparison} from '../src/CandidateComparison';
import {SpriteImage,ZoomControls} from '../src/SpriteViewport';

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
  s.base={...s.base!,activeReferenceRevisionId:'r2',references,assets:references.map((r,i)=>({assetId:r.identityAssetId,url:`/${i}.png`,originalFilename:`${i}.png`,width:32,height:48})),clips:s.base!.clips.map(c=>({...c,referenceRevisionId:'r1'}))} as Snapshot;
  s.snapshot=structuredClone(s.base);
 });
 it('shows the linked image, opens it without edits, and switches using the original reference ID',()=>{
  const h=new Harness(s),picture=()=>nodes(h.tree).find(n=>n.type==='img'&&n.props.alt==='선택한 동작의 기준 그림');
  expect(picture()!.props.src).toBe('/0.png');h.click('크게 보기');
  const dialog=nodes(h.tree).find(n=>n.type===EditorDialog&&n.props.title==='동작에 연결된 기준 그림')!;
  expect(dialog.props.open).toBe(true);expect(text(dialog)).toContain('기준 1 · 힐러 1 · 0.png');expect(s.edit).not.toHaveBeenCalled();
  expect(nodes(dialog).some(n=>n.type===SpriteImage&&n.props.src==='/0.png'&&n.props.width===32)).toBe(true);
  dialog.props.onClose();h.render();
  const select=nodes(h.tree).find(n=>n.type===Select&&n.props.label==='동작에 사용할 캐릭터 기준')!;
  expect(text(select)).toContain('기준 2 · 힐러 2 · 1.png');select.props.onChange({target:{value:'r2'}});h.render();
  expect(s.edit).toHaveBeenCalledExactlyOnceWith({type:'updateClip',clipId:'c',changes:{referenceRevisionId:'r2'}});
  expect(picture()!.props.src).toBe('/1.png');expect(s.snapshot!.clips[0].review).not.toBe('approved');
 });
 it('links a new clip to the newest saved reference when none is active',()=>{
  s.base!.activeReferenceRevisionId=null as any;s.snapshot=structuredClone(s.base);const h=new Harness(s);h.click('새 동작');
  nodes(h.tree).find(n=>n.props.label==='새 동작 이름')!.props.onChange({target:{value:'달리기'}});h.render();
  nodes(h.tree).find(n=>n.type==='form')!.props.onSubmit({preventDefault:vi.fn()});
  expect(s.edit).toHaveBeenCalledWith({type:'createClip',clip:{name:'달리기',referenceRevisionId:'r2'}});expect(s.snapshot!.activeReferenceRevisionId).toBeNull();
 });
 it('never substitutes the active image for an unlinked clip',()=>{
  s.snapshot!.clips[0].referenceRevisionId=null;const h=new Harness(s);
  expect(nodes(h.tree).some(n=>n.type===SpriteImage&&n.props.alt==='선택한 동작의 기준 그림')).toBe(false);
  expect(text(h.tree)).toContain('이 동작에 사용할 캐릭터 기준을 선택하세요.');
 });
 it('lets review comparison change images without changing the clip reference',()=>{
  const frame={frameVersionId:'f',imageAssetId:'a0',review:'pending'};
  const h=new Harness(s,'c',({s})=>CandidateComparison({s,frame:frame as any,clip:s.snapshot!.clips[0]}));
  const select=nodes(h.tree).find(n=>n.type===Select&&n.props.label==='나란히 비교할 저장 기준')!;
  select.props.onChange({target:{value:'r2'}});h.render();
  const image=nodes(h.tree).find(n=>n.type.name==='ComparisonImage'&&n.props.alt==='저장된 외형 기준')!;
  expect(image.props.asset.url).toBe('/1.png');expect(s.edit).not.toHaveBeenCalled();expect(s.snapshot!.clips[0].referenceRevisionId).toBe('r1');
 });
 it('lets pending saved references be selected for comparison without changing their records',()=>{
  s.snapshot!.references=s.snapshot!.references.map(reference=>({...reference,approval:'draft'}));
  const before=structuredClone(s.snapshot),frame={frameVersionId:'f',imageAssetId:'a0',review:'pending'};
  const h=new Harness(s,'c',({s})=>CandidateComparison({s,frame:frame as any,clip:s.snapshot!.clips[0]}));
  const select=nodes(h.tree).find(n=>n.type===Select&&n.props.label==='나란히 비교할 저장 기준')!;
  expect(text(select)).toContain('기준 1 · 힐러 1 · 0.png');expect(text(select)).toContain('기준 2 · 힐러 2 · 1.png');
  select.props.onChange({target:{value:'r2'}});h.render();
  const image=nodes(h.tree).find(n=>n.type.name==='ComparisonImage'&&n.props.alt==='저장된 외형 기준')!;
  expect(image.props.asset.url).toBe('/1.png');expect(s.snapshot).toEqual(before);expect(s.edit).not.toHaveBeenCalled();
 });
 it('compares both original images in a dialog with shared reference and zoom, without project edits',()=>{
  const frame={frameVersionId:'f',imageAssetId:'a0',review:'pending'};
  s.snapshot!.assets=s.snapshot!.assets.map(a=>({...a,width:32,height:48}));
  const before=structuredClone(s.snapshot);
  const h=new Harness(s,'c',({s})=>CandidateComparison({s,frame:frame as any,clip:s.snapshot!.clips[0]}));
  h.click('두 이미지 크게 비교');
  const dialog=()=>nodes(h.tree).find(n=>n.type===EditorDialog&&n.props.title==='저장 기준과 후보 크게 비교');
  const compared=()=>nodes(dialog()).filter(n=>n.type.name==='ComparisonImage');
  expect(compared().map(n=>n.props.asset.url)).toEqual(['/0.png','/0.png']);
  nodes(dialog()).find(n=>n.type===Select&&n.props.label==='나란히 비교할 저장 기준')!.props.onChange({target:{value:'r2'}});h.render();
  nodes(dialog()).find(n=>n.type===Select&&n.props.label==='비교 이미지 배율')!.props.onChange({target:{value:'2'}});h.render();
  expect(compared().map(n=>n.props.asset.url)).toEqual(['/1.png','/0.png']);
  expect(compared().map(n=>n.props.zoom)).toEqual([2,2]);
  dialog()!.props.onClose();h.render();expect(dialog()).toBeUndefined();
  const selects=nodes(h.tree).filter(n=>n.type===Select);
  expect(selects.find(n=>n.props.label==='나란히 비교할 저장 기준')!.props.value).toBe('r2');
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
  const dialog=nodes(h.tree).find(n=>n.type===EditorDialog&&n.props.title==='저장 기준과 후보 크게 비교')!;
  expect(dialog).toBeDefined();expect(text(dialog)).toContain('재생 슬롯 2 / 2');
  const compared=nodes(dialog).filter(n=>n.type.name==='ComparisonImage');
  expect(compared.map(n=>n.props.asset.url)).toEqual(['/0.png','/1.png']);expect(compared.map(n=>n.props.zoom)).toEqual([2,2]);
  expect(nodes(dialog).find(n=>n.type===Select&&n.props.label==='비교 이미지 배율')!.props.value).toBe('2');
  expect(s.edit).not.toHaveBeenCalled();
 });
 it('steps both differently sized images by their own fit scale and resets fit factor',()=>{
  s.snapshot!.assets=s.snapshot!.assets.map((asset,index)=>({...asset,width:index?1024:64,height:index?1024:64}));
  const frame={frameVersionId:'f',imageAssetId:'a1',review:'pending'};
  const h=new Harness(s,'c',({s})=>CandidateComparison({s,frame:frame as any,clip:s.snapshot!.clips[0]}));
  const images=()=>nodes(h.tree).filter(n=>n.type.name==='ComparisonImage');
  const controls=()=>nodes(h.tree).find(n=>n.type===ZoomControls)!;
  expect(images().map(n=>n.props.asset.width)).toEqual([64,1024]);
  controls().props.onStep(1);h.render();
  expect(images().map(n=>n.props.zoom)).toEqual(['fit','fit']);expect(images().map(n=>n.props.fitFactor)).toEqual([2,2]);
  expect(text(nodes(h.tree).find(n=>n.type===Select&&n.props.label==='비교 이미지 배율')!)).toContain('맞춤 기준 200%');
  controls().props.onStep(-1);h.render();controls().props.onStep(-1);h.render();
  expect(images().map(n=>n.props.fitFactor)).toEqual([0.5,0.5]);
  controls().props.setZoom('fit');h.render();
  expect(images().map(n=>n.props.fitFactor)).toEqual([1,1]);
  const select=nodes(h.tree).find(n=>n.type===Select&&n.props.label==='비교 이미지 배율')!;
  select.props.onChange({target:{value:'1'}});h.render();
  expect(images().map(n=>n.props.zoom)).toEqual([1,1]);
  images()[0].props.onFitZoom(images()[0].props.fitKey,200);h.render();
  controls().props.setZoom(64);h.render();controls().props.onStep(1);h.render();
  expect(images().map(n=>n.props.zoom)).toEqual([128,128]);
 });
 it('keeps rejection reason state keyed per candidate while removing approval display',()=>{
  const frame1={frameVersionId:'f1',imageAssetId:'a0',review:'pending',reviewReason:'첫 후보 사유'},frame2={...frame1,frameVersionId:'f2',reviewReason:'두 번째 후보 사유'};
  const render=(frame:any)=>CandidateReview({s,frame,clip:s.snapshot!.clips[0]});
  const first=render(frame1),second=render(frame2);
  const rejection=(tree:any)=>nodes(tree).find(n=>n.type===CandidateRejection)!;
  const comparison=(tree:any)=>nodes(tree).find(n=>n.type===CandidateComparison)!;
  expect(rejection(first).key).toBe('f1');expect(rejection(second).key).toBe('f2');
  expect(comparison(first).key).toBe(comparison(second).key);
  expect(text(first)).not.toContain('승인 대기');
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
  s.snapshot!.references=[{referenceRevisionId:'r'}] as any;s.snapshot!.frames=[{frameVersionId:'f',nativeScaleGroupId:'g',review:'pending'}] as any;s.snapshot!.alignmentGroups=[{alignmentGroupId:'g',groupRevisionId:'gr',frameVersionIds:['f']}] as any;s.snapshot!.alignments={f:{frameVersionId:'f',groupRevisionId:'gr',approval:'pending'}} as any;s.snapshot!.clips.forEach(c=>{c.referenceRevisionId='r';c.occurrences=[{occurrenceId:c.clipId+'-o',frameVersionId:'f',durationMs:125,timingMode:'fps'}] as any;});
  const h=new Harness(s,'c',ExportStep);s.snapshot!.clips=s.snapshot!.clips.filter(c=>c.clipId!=='c');h.render();
  expect(text(h.tree)).not.toContain('출력할 동작을 찾을 수 없습니다.');h.click('확정 미리보기 만들기');
  expect(s.job).toHaveBeenCalledExactlyOnceWith('bake',[],{clipIds:['other'],clipRevisionIds:['other-r']});
  s.snapshot!.clips=[];h.render();expect(h.button('확정 미리보기 만들기').props.disabled).toBe(true);
 });
});

describe('export gates and selection',()=>{
 beforeEach(()=>{
  s.exports=[];s.service={worker:'ready'} as Studio['service'];s.job=vi.fn();s.save=vi.fn();
  s.snapshot!.references=[{referenceRevisionId:'r'}] as any;s.snapshot!.frames=[{frameVersionId:'f',nativeScaleGroupId:'g',review:'pending'}] as any;s.snapshot!.alignmentGroups=[{alignmentGroupId:'g',groupRevisionId:'gr',frameVersionIds:['f']}] as any;s.snapshot!.alignments={f:{frameVersionId:'f',groupRevisionId:'gr',approval:'pending'}} as any;s.snapshot!.clips.forEach(c=>{c.referenceRevisionId='r';c.occurrences=[{occurrenceId:c.clipId+'-o',frameVersionId:'f',durationMs:125,timingMode:'fps'}] as any;});
 });
 it('includes clips created after the export tab opened and keeps explicit exclusions',()=>{
  const h=new Harness(s,'c',ExportStep);s.snapshot!.clips.push({...s.snapshot!.clips[1],clipId:'new',clipRevisionId:'new-r',name:'새 공격'});h.render();
  nodes(h.tree).find(n=>n.type===Check&&n.props.label.startsWith('초안 걷기'))!.props.onChange(false);h.render();
  h.click('확정 미리보기 만들기');expect(s.job).toHaveBeenCalledExactlyOnceWith('bake',[],{clipIds:['other','new'],clipRevisionIds:['other-r','new-r']});
 });
 it('names a disconnected worker instead of claiming the export is ready',()=>{
  s.service={worker:'offline'} as any;const h=new Harness(s,'c',ExportStep);
  expect(h.button('확정 미리보기 만들기').props.disabled).toBe(true);expect(text(h.tree)).toContain('작업 처리기가 연결되지 않았습니다.');expect(text(h.tree)).not.toContain('준비됨');
 });
 it('offers saving next to the unsaved-draft gate, but not during a conflict',()=>{
  s.commands=[{operation:{type:'updateCharacter',name:'x'}}] as any;const h=new Harness(s,'c',ExportStep);
  h.click('편집 초안 저장');expect(s.save).toHaveBeenCalledOnce();expect(s.job).not.toHaveBeenCalled();
  s.conflict=project;h.render();expect(()=>h.button('편집 초안 저장')).toThrow();
 });
});

describe('result preview selection',()=>{
 it('uses the newest applicable bake without editing existing records',()=>{
  s.exports=[];s.service={worker:'ready'} as any;
  const runtime=(id:string)=>({schemaVersion:1,exportId:id,projectRevision:3,atlas:{file:'atlas.png',width:64,height:64},frames:[],clips:[{id:'c',occurrences:[]}]} as any);
  const job=(id:string,createdAt:string)=>({jobId:id,operation:'bake',inputRevision:3,status:'succeeded',createdAt,result:{manifest:runtime(id)},artifacts:[{artifactId:id,name:'atlas.png',url:`/${id}.png`}]} as any);
  const newer=job('new','2026-10-12T02:00:00Z'),older=job('old','2026-10-12T01:00:00Z');s.jobs=[newer,older];
  const before=structuredClone(s.snapshot),h=new Harness(s,'c',ExportStep);
  expect(nodes(h.tree).find(n=>n.props.runtime)?.props.runtime.exportId).toBe('new');s.jobs=[older,newer];h.render();expect(nodes(h.tree).find(n=>n.props.runtime)?.props.runtime.exportId).toBe('new');expect(s.snapshot).toEqual(before);expect(s.edit).not.toHaveBeenCalled();
 });
});

describe('review tab preview',()=>{
 const review=(props:any)=>ExportStep({...props,mode:'review'});
 beforeEach(()=>{
  s.exports=[];s.job=vi.fn();s.mutation=vi.fn();
  s.snapshot!.clips.forEach(c=>{c.occurrences=[{occurrenceId:c.clipId+'-1',frameVersionId:'f',durationMs:125,timingMode:'fps'},{occurrenceId:c.clipId+'-2',frameVersionId:'f',durationMs:250,timingMode:'manual'}] as any;});
 });
 function baked(revision=3){
  const manifest={schemaVersion:1,exportId:'baked',projectRevision:revision,atlas:{file:'atlas.png',width:64,height:64},frames:[],clips:['other','c'].map(id=>({id,occurrences:[]}))};
  s.jobs=[{jobId:'baked',operation:'bake',inputRevision:revision,status:'succeeded',result:{manifest},artifacts:[{artifactId:'atlas',name:'atlas.png',url:'/atlas.png'}]}] as any;
 }
 it('immediately previews the selected working clip without generating or editing data',()=>{
  const before=structuredClone(s.snapshot),h=new Harness(s,'c',review);
  expect(h.canvas().props.snapshot).toBe(s.snapshot);expect(h.canvas().props.clip.clipId).toBe('c');
  expect(text(h.tree)).toContain('현재 동작의 작업 미리보기');
  h.canvas().props.onSelect('c-2');h.render();expect(h.canvas().props.selected).toBe('c-2');
  h.clipId='other';h.render();expect(h.canvas().props.clip.clipId).toBe('other');
  expect(s.snapshot).toEqual(before);expect(s.edit).not.toHaveBeenCalled();expect(s.job).not.toHaveBeenCalled();expect(s.mutation).not.toHaveBeenCalled();
 });
 it.each(['stale','draft'])('shows working edits when the baked output is %s, while retaining the previous output',reason=>{
  baked(reason==='stale'?2:3);if(reason==='draft')s.commands=[{operation:{type:'updateClip',clipId:'c',changes:{name:'수정 중'}}}] as any;
  const jobs=structuredClone(s.jobs),h=new Harness(s,'c',review);
  expect(h.canvas().props.snapshot).toBe(s.snapshot);expect(nodes(h.tree).some(n=>n.props.runtime)).toBe(false);
  h.click('최근 성공 결과');expect(nodes(h.tree).find(n=>n.props.runtime)!.props.runtime.exportId).toBe('baked');
  expect(text(h.tree)).toContain('저장된 이전 결과를 표시합니다.');
  h.click('작업 미리보기');expect(h.canvas().props.clip.clipId).toBe('c');expect(s.jobs).toEqual(jobs);
 });
 it('plays the selected clip in a current multi-clip bake and can return to the working preview',()=>{
  baked();const h=new Harness(s,'c',review);
  expect(nodes(h.tree).find(n=>n.props.runtime)!.props.runtime.clips.map((c:any)=>c.id)).toEqual(['c']);
  h.clipId='other';h.render();expect(nodes(h.tree).find(n=>n.props.runtime)!.props.runtime.clips.map((c:any)=>c.id)).toEqual(['other']);
  h.click('작업 미리보기');expect(h.canvas().props.clip.clipId).toBe('other');
 });
 it('explains missing frames and links back to editing',()=>{
  s.snapshot!.clips[0].occurrences=[];const onNavigate=vi.fn(),h=new Harness(s,'c',props=>review({...props,onNavigate}));
  expect(h.canvas()).toBeUndefined();expect(nodes(h.tree).some(n=>n.props.title==='확인할 동작 프레임이 없습니다')).toBe(true);
  h.click('프레임 편집으로 이동');expect(onNavigate).toHaveBeenCalledExactlyOnceWith({action:'pixel',clipId:'c'});expect(s.job).not.toHaveBeenCalled();
 });
 it('keeps an export preview closed after the user closes it',()=>{
  baked();const h=new Harness(s,'c',ExportStep);h.click('닫기');
  expect(nodes(h.tree).some(n=>n.props.runtime)).toBe(false);h.render();expect(nodes(h.tree).some(n=>n.props.runtime)).toBe(false);
  h.click('최근 성공 결과');expect(nodes(h.tree).find(n=>n.props.runtime)!.props.runtime.exportId).toBe('baked');
 });
});

describe('export location and history',()=>{
 beforeEach(()=>{
  s.exports=[];s.service={worker:'ready',desktop:{fileManager:'finder'}} as any;s.revealProject=vi.fn();s.job=vi.fn();s.mutation=vi.fn();
  s.snapshot!.storage={layout:'project-folder',path:'/Users/test/캐릭터/',available:true};
 });
 const cards=(h:Harness)=>nodes(h.tree).filter(n=>['article','details'].includes(n.type as string)&&n.props.className?.includes('list-card'));
 it('shows the actual automatic output root before export and opens only the project folder on request',()=>{
  const before=structuredClone(s.snapshot),h=new Harness(s,'c',ExportStep),input=nodes(h.tree).find(n=>n.props.label==='자동 저장 폴더')!;
  expect(input.props.value).toBe('/Users/test/캐릭터/outputs');expect(input.props.readOnly).toBe(true);expect(text(h.tree)).toContain('브라우저의 다운로드 설정');
  h.click('프로젝트 폴더 열기');expect(s.revealProject).toHaveBeenCalledExactlyOnceWith(s.snapshot);expect(s.snapshot).toEqual(before);expect(s.edit).not.toHaveBeenCalled();expect(s.job).not.toHaveBeenCalled();expect(s.mutation).not.toHaveBeenCalled();
 });
 it('keeps Windows separators and trailing roots intact',()=>{
  s.snapshot!.storage!.path='C:\\작업 폴더\\캐릭터\\';const h=new Harness(s,'c',ExportStep);
  expect(nodes(h.tree).find(n=>n.props.label==='자동 저장 폴더')!.props.value).toBe('C:\\작업 폴더\\캐릭터\\outputs');
 });
 it.each(['busy','unsupported','missing'])('disables the folder action when %s without hiding its path',reason=>{
  if(reason==='busy')s.busy=true;if(reason==='unsupported')s.service!.desktop!.fileManager=null;if(reason==='missing')s.snapshot!.storage!.available=false;
  const h=new Harness(s,'c',ExportStep);expect(h.button('프로젝트 폴더 열기').props.disabled).toBe(true);expect(nodes(h.tree).find(n=>n.props.label==='자동 저장 폴더')!.props.value).toContain('/outputs');
 });
 it('sorts same-revision exports by completion time, shows request times and picks the latest successful output',()=>{
  const record=(id:string,status='succeeded')=>({exportId:id,jobId:'job-'+id,status,projectRevision:3,manifest:{schemaVersion:1,exportId:id,projectRevision:3,atlas:{file:'atlas.png',width:64,height:64},frames:[],clips:[{id:'c',occurrences:[]}]},files:[{artifactId:id,name:'atlas.png',url:`/${id}.png`},{artifactId:id+'-zip',name:'bundle.zip',url:`/${id}.zip`}]} as any);
  s.exports=[record('older'),record('newest'),record('failed','failed')];
  s.jobs=[{jobId:'job-newest',createdAt:'2026-10-12T01:00:00Z',updatedAt:'2026-10-12T03:00:00Z',attemptId:'new-attempt'},{jobId:'job-older',createdAt:'2026-10-12T02:00:00Z',updatedAt:'2026-10-12T02:05:00Z'},{jobId:'job-failed',createdAt:'2026-10-12T04:00:00Z',updatedAt:'2026-10-12T04:01:00Z'}] as any;
  s.jobs.push({jobId:'old-bake',operation:'bake',status:'succeeded',inputRevision:3,createdAt:'2026-10-12T00:00:00Z',updatedAt:'2026-10-12T00:01:00Z',result:{manifest:{...s.exports[0].manifest!,exportId:'old-preview'}},artifacts:[{artifactId:'old-preview',name:'atlas.png',url:'/old-preview.png'}]});
  const before=structuredClone(s.exports),jobs=structuredClone(s.jobs),h=new Harness(s,'c',ExportStep);
  expect(cards(h).map(c=>c.key)).toEqual(['failed','newest','older']);expect(text(cards(h)[0])).not.toContain('최신 출력');expect(text(cards(h)[1])).toContain('최신 출력');expect(text(cards(h)[2])).not.toContain('최신 출력');
  const timestamps=nodes(cards(h)[1]).find(n=>n.props.className==='export-timestamps')!;
  expect(nodes(timestamps).filter(n=>n.type==='time').map(n=>n.props.dateTime)).toEqual(['2026-10-12T03:00:00Z','2026-10-12T01:00:00Z']);
  expect(text(cards(h)[1])).toContain('/Users/test/캐릭터/outputs/job-newest/new-attempt');
  expect(nodes(cards(h)[1]).find(n=>n.type==='a'&&text(n)==='전체 파일 ZIP 다운로드')!.props).toMatchObject({href:'/newest.zip',download:'bundle.zip'});
  expect(nodes(h.tree).find(n=>n.props.runtime)!.props.runtime.exportId).toBe('newest');expect(s.exports).toEqual(before);expect(s.jobs).toEqual(jobs);
  s.exports.reverse();s.jobs.reverse();h.render();expect(cards(h).map(c=>c.key)).toEqual(['failed','newest','older']);
  s.jobs.find(j=>j.jobId==='old-bake')!.updatedAt='2026-10-12T04:10:00Z';h.render();expect(nodes(h.tree).find(n=>n.props.runtime)!.props.runtime.exportId).toBe('old-preview');
 });
 it('does not fabricate dates or a latest label for records without timestamps',()=>{
  s.exports=[{exportId:'unknown',status:'succeeded',manifest:{exportId:'unknown',clips:[{id:'c'}]},files:[{name:'atlas.png',url:'/unknown.png'}]}] as any;
  const h=new Harness(s,'c',ExportStep);expect(text(cards(h)[0])).toContain('출력 시각 기록 없음');expect(text(cards(h)[0])).not.toContain('최신 출력');expect(nodes(cards(h)[0]).some(n=>n.type==='time')).toBe(false);
 });
 it('keeps the newest failed export expanded and summarizes older records with their timestamps',()=>{
  const record=(exportId:string,status:string)=>({exportId,jobId:`job-${exportId}`,status,projectRevision:3,manifest:{exportId,projectRevision:3,clips:[{id:'c'}]},files:[]} as any);
  s.exports=[record('older','succeeded'),record('newest','failed')];
  s.jobs=[
   {jobId:'job-newest',createdAt:'2026-10-12T04:00:00Z'},
   {jobId:'job-older',createdAt:'2026-10-12T02:00:00Z',updatedAt:'2026-10-12T03:00:00Z'},
  ] as any;
  const h=new Harness(s,'c',ExportStep),[newest,older]=cards(h);
  expect(newest.type).toBe('article');expect(text(newest)).toContain('실패');
  expect(older.type).toBe('details');expect(older.props.open).toBeUndefined();
  const summary=nodes(older).find(n=>n.type==='summary')!;
  expect(text(summary)).toContain('출력 older');expect(text(summary)).toContain('완료');expect(text(summary)).not.toContain('요청');
  expect(nodes(summary).filter(n=>n.type==='time').map(n=>n.props.dateTime)).toEqual(['2026-10-12T03:00:00Z']);
  const timestamps=nodes(older).find(n=>n.props.className==='export-timestamps')!;
  expect(nodes(timestamps).filter(n=>n.type==='time').map(n=>n.props.dateTime)).toEqual(['2026-10-12T03:00:00Z','2026-10-12T02:00:00Z']);
 });
 it('keeps all clip selections available in the collapsed selector without editing the project',()=>{
  const h=new Harness(s,'c',ExportStep);expect(text(h.tree)).toContain('출력할 동작 · 2 / 2개 선택');
  const selection=nodes(h.tree).find(n=>n.type===Check&&n.props.label==='초안 걷기 · 0 슬롯')!;selection.props.onChange(false);h.render();expect(text(h.tree)).toContain('출력할 동작 · 1 / 2개 선택');expect(s.edit).not.toHaveBeenCalled();
 });
});

describe('export settings and history tabs',()=>{
 beforeEach(()=>{
  s.exports=[];s.service={worker:'ready'} as any;s.job=vi.fn();s.mutation=vi.fn();
  s.snapshot!.references=[{referenceRevisionId:'r'}] as any;
  s.snapshot!.frames=[{frameVersionId:'f',nativeScaleGroupId:'g',review:'pending'}] as any;
  s.snapshot!.alignmentGroups=[{alignmentGroupId:'g',groupRevisionId:'gr',frameVersionIds:['f']}] as any;
  s.snapshot!.alignments={f:{frameVersionId:'f',groupRevisionId:'gr',approval:'pending'}} as any;
  s.snapshot!.clips.forEach(c=>{c.referenceRevisionId='r';c.occurrences=[{occurrenceId:c.clipId+'-o',frameVersionId:'f',durationMs:125,timingMode:'fps'}] as any;});
 });
 const tabs=(h:Harness)=>nodes(h.tree).filter(n=>n.props.role==='tab');
 const panels=(h:Harness)=>nodes(h.tree).filter(n=>n.props.role==='tabpanel');
 it('links persistent panels to tabs and switches by click and keyboard without editing or losing clip selections',()=>{
  const h=new Harness(s,'c',ExportStep),tablist=()=>nodes(h.tree).find(n=>n.props.role==='tablist')!;
  const [settings,history]=tabs(h),[options,records]=panels(h);
  expect(tablist().props['aria-label']).toBe('출력 설정과 이력');expect(text(settings)).toBe('출력 설정');expect(text(history)).toBe('출력 이력 0');
  expect(settings.props).toMatchObject({'aria-selected':true,tabIndex:0});expect(history.props).toMatchObject({'aria-selected':false,tabIndex:-1});
  expect(options.props).toMatchObject({className:'export-settings panel','aria-labelledby':settings.props.id,hidden:false});
  expect(records.props).toMatchObject({className:'export-history panel','aria-labelledby':history.props.id,hidden:true});
  const selection=nodes(h.tree).find(n=>n.type===Check&&n.props.label==='초안 걷기 · 1 슬롯')!;selection.props.onChange(false);h.render();
  for(const [key,index] of [['ArrowRight',1],['Home',0],['End',1],['ArrowLeft',0]] as const){
   const focus=[vi.fn(),vi.fn()],preventDefault=vi.fn();tablist().props.onKeyDown({key,preventDefault,currentTarget:{querySelectorAll:()=>focus.map(fn=>({focus:fn}))}});h.render();
   expect(preventDefault).toHaveBeenCalledOnce();expect(focus[index]).toHaveBeenCalledOnce();expect(tabs(h)[index].props['aria-selected']).toBe(true);
  }
  tabs(h)[0].props.onClick();h.render();
  expect(panels(h).map(panel=>panel.props.hidden)).toEqual([false,true]);expect(text(h.tree)).toContain('출력할 동작 · 1 / 2개 선택');
  expect(s.edit).not.toHaveBeenCalled();expect(s.job).not.toHaveBeenCalled();expect(s.mutation).not.toHaveBeenCalled();
 });
 it('moves to history after successful export and preserves the existing request payload',async()=>{
  s.mutation=vi.fn().mockResolvedValue({exportId:'export-1'});const h=new Harness(s,'c',ExportStep);
  await h.button('게임용 파일 출력').props.onClick();h.render();
  expect(s.mutation).toHaveBeenCalledExactlyOnceWith('/projects/p/exports',expect.objectContaining({savedRevision:3,clipRevisionIds:['c-r','other-r'],formats:['atlas','pngs','runtime','aseprite'],outlineMode:s.snapshot!.outline.mode,idempotencyKey:expect.any(String)}));
  expect(tabs(h).map(tab=>tab.props['aria-selected'])).toEqual([false,true]);expect(h.tree.props['data-view']).toBe('settings');
  expect(panels(h).map(panel=>panel.props.hidden)).toEqual([true,false]);expect(s.edit).not.toHaveBeenCalled();expect(s.job).not.toHaveBeenCalled();
 });
 it('keeps settings selected when export mutation returns undefined',async()=>{
  s.mutation=vi.fn().mockResolvedValue(undefined);const h=new Harness(s,'c',ExportStep);
  h.click('설정·다운로드');await h.button('게임용 파일 출력').props.onClick();h.render();
  expect(tabs(h).map(tab=>tab.props['aria-selected'])).toEqual([true,false]);expect(h.tree.props['data-view']).toBe('settings');
  expect(panels(h).map(panel=>panel.props.hidden)).toEqual([false,true]);expect(s.edit).not.toHaveBeenCalled();expect(s.job).not.toHaveBeenCalled();
 });
});
