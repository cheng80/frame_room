import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {readFileSync} from 'node:fs';
import type {ReactElement} from 'react';
import type {Clip,Runtime,Snapshot} from '../src/types';

// A small hook lifecycle harness: unit-only, no DOM/browser or image creation.
// Effects retain React's dependency/cleanup semantics and run after ref commit.
const hooks=vi.hoisted(()=>({current:null as any}));
vi.mock('react',async importOriginal=>{
 const actual=await importOriginal<typeof import('react')>();
 return {...actual,
  useRef:(initial:unknown)=>hooks.current.ref(initial),
  useState:(initial:unknown)=>hooks.current.state(initial),
  useEffect:(setup:()=>unknown,deps:unknown[])=>hooks.current.effect(setup,deps,false),
  useLayoutEffect:(setup:()=>unknown,deps:unknown[])=>hooks.current.effect(setup,deps,true),
 };
});
vi.mock('../src/render',async importOriginal=>({
 ...await importOriginal<typeof import('../src/render')>(),
 drawOccurrence:vi.fn(()=>new Promise(()=>{})),loadImage:vi.fn(()=>new Promise(()=>{})),
}));
import {EditorCanvas,RuntimePlayer,canvasTimelineKey,fitCanvasZoom,startCanvasPlayback} from '../src/Canvas';

type Node=ReactElement<any>;
function nodes(tree:any):Node[]{
 if(!tree||typeof tree!=='object')return [];
 if(Array.isArray(tree))return tree.flatMap(nodes);
 if(!tree.props)return [];
 if(typeof tree.type==='function'&&tree.type.name==='ZoomControls')return nodes(tree.type(tree.props));
 return [tree,...nodes(tree.props.children)];
}
function text(tree:any):string{
 if(tree===null||tree===undefined||typeof tree==='boolean')return '';
 if(typeof tree==='string'||typeof tree==='number')return String(tree);
 if(Array.isArray(tree))return tree.map(text).join('');
 return text(tree.props?.children);
}
const stage={clientWidth:344,clientHeight:224};
const mounted:any[]=[];
class Harness {
 slots:any[]=[];cursor=0;dirty=false;tree:any;props:any;layouts:(()=>void)[]=[];effects:(()=>void)[]=[];
 constructor(public component:(props:any)=>any,props:any){this.props=props;mounted.push(this);this.render();}
 ref(initial:unknown){const i=this.cursor++;return (this.slots[i]??={current:initial});}
 state(initial:unknown){const i=this.cursor++;const slot=this.slots[i]??={value:typeof initial==='function'?initial():initial};
  slot.set??=(next:any)=>{const value=typeof next==='function'?next(slot.value):next;if(!Object.is(value,slot.value)){slot.value=value;this.dirty=true;}};
  return [slot.value,slot.set];
 }
 effect(setup:()=>any,deps:unknown[],layout:boolean){const i=this.cursor++,old=this.slots[i];
  if(old&&deps?.length===old.deps?.length&&deps.every((dep,j)=>Object.is(dep,old.deps[j])))return;
  (layout?this.layouts:this.effects).push(()=>{old?.cleanup?.();this.slots[i]={deps,cleanup:setup()};});
 }
 render(next?:any){if(next)this.props=next;let iterations=0;
  do{if(++iterations>20)throw new Error('unit harness render loop');this.dirty=false;this.cursor=0;this.layouts=[];this.effects=[];
   hooks.current=this;this.tree=this.component(this.props);hooks.current=null;
   for(const node of nodes(this.tree)){const ref=node.props.ref;if(ref&&typeof ref==='object')ref.current=node.type==='canvas'?{}:stage;}
   this.layouts.forEach(run=>run());this.effects.forEach(run=>run());
  }while(this.dirty);
 }
 all(type:string){return nodes(this.tree).filter(n=>n.type===type);}
 button(label:string){const found=this.all('button').find(n=>n.props['aria-label']===label||text(n).trim()===label);if(!found)throw new Error(`No button ${label}`);return found;}
 click(label:string){this.button(label).props.onClick();this.render();}
 canvas(){return this.all('canvas')[0];}
 unmount(){for(const slot of this.slots)slot?.cleanup?.();}
}
let now=0,nextRaf=1,queue:Map<number,FrameRequestCallback>;
let observers:ResizeObserverFake[]=[];
class ResizeObserverFake {
 target:any;disconnect=vi.fn();
 constructor(public callback:ResizeObserverCallback){observers.push(this);}
 observe(target:any){this.target=target;}
 resize(width:number,height:number){this.callback([{target:this.target,contentRect:{width,height}}] as any,this as any);}
}
function tick(time:number){now=time;const callbacks=[...queue.values()];queue.clear();callbacks.forEach(callback=>callback(now));}
const timeline={id:'idle',loop:true,slots:[{id:'a',durationMs:80},{id:'b',durationMs:120},{id:'c',durationMs:200}]};
function editorProps(){
 const clip={clipId:'idle',loop:true,occurrences:timeline.slots.map(s=>({occurrenceId:s.id,durationMs:s.durationMs,frameVersionId:'frame'}))} as Clip;
 const snapshot={frames:[{frameVersionId:'frame',nativeScaleGroupId:'group'}],alignmentGroups:[{alignmentGroupId:'group',cell:{width:512,height:512}}]} as Snapshot;
 return {snapshot,clip,selected:'a',onSelect:vi.fn()};
}
function runtimeData():Runtime{return {schemaVersion:1,exportId:'export',projectRevision:1,atlas:{file:'atlas.png',width:1536,height:512},frames:timeline.slots.map((s,i)=>({id:s.id,rect:{x:i*512,y:0,width:512,height:512},anchor:[256,494]})),clips:[{id:'idle',loop:true,endBehavior:'hold-last',occurrences:timeline.slots.map(s=>({id:s.id,renderedFrameId:s.id,durationMs:s.durationMs}))}]};}

beforeEach(()=>{
 now=0;nextRaf=1;queue=new Map();observers=[];
 vi.spyOn(performance,'now').mockImplementation(()=>now);
 vi.stubGlobal('requestAnimationFrame',vi.fn((fn:FrameRequestCallback)=>{const id=nextRaf++;queue.set(id,fn);return id;}));
 vi.stubGlobal('cancelAnimationFrame',vi.fn((id:number)=>queue.delete(id)));
 vi.stubGlobal('ResizeObserver',ResizeObserverFake);
 vi.stubGlobal('getComputedStyle',()=>({paddingLeft:'12px',paddingRight:'12px',paddingTop:'12px',paddingBottom:'12px'}));
 vi.stubGlobal('window',{devicePixelRatio:1,addEventListener:vi.fn(),removeEventListener:vi.fn()});
});
afterEach(()=>{mounted.splice(0).forEach(host=>host.unmount());vi.restoreAllMocks();vi.unstubAllGlobals();});

describe('canvas viewport and dock',()=>{
 it.each([[512,512,240,180,180,180],[512,256,240,180,240,120],[256,512,240,180,90,180],[512,512,40,30,30,30]])('fits %ix%i in %ix%i without per-axis distortion',(w,h,availableW,availableH,expectedW,expectedH)=>{
  const z=fitCanvasZoom(w,h,availableW,availableH);expect(w*z).toBe(expectedW);expect(h*z).toBe(expectedH);
 });
 it.each([0,-1,NaN,Infinity])('does not expand layout before a valid stage measurement (%s)',size=>expect(fitCanvasZoom(512,512,size,200)).toBe(0));
 it('defaults to FIT, follows ResizeObserver and preserves manual overrides until 맞춤',()=>{
  const host=new Harness(EditorCanvas,editorProps());
  expect(host.canvas().props.style).toMatchObject({width:200,height:200});
  expect(host.button('맞춤').props['aria-pressed']).toBe(true);
  observers[0].resize(280,140);host.render();expect(host.canvas().props.style.width).toBe(140);
  host.click('1:1');expect(host.canvas().props.style.width).toBe(512);
  observers[0].resize(100,80);host.render();expect(host.canvas().props.style.width).toBe(512);
  host.click('게임 128px');expect(host.canvas().props.style.width).toBe(128);
  host.click('확대');expect(host.canvas().props.style.width).toBe(256);
  host.click('축소');expect(host.canvas().props.style.width).toBe(128);
  host.click('맞춤');expect(host.canvas().props.style.width).toBe(80);
  expect(observers).toHaveLength(1);
 });
 it('resizes rectangular cells with the same scale in each axis',()=>{
  const props=editorProps();props.snapshot.alignmentGroups[0].cell.height=256;
  const host=new Harness(EditorCanvas,props);
  expect(host.canvas().props.style).toMatchObject({width:320,height:160});
 });
 it('disconnects its observer when unmounted',()=>{
  const host=new Harness(EditorCanvas,editorProps());host.unmount();expect(observers[0].disconnect).toHaveBeenCalledOnce();
  mounted.splice(mounted.indexOf(host),1);
 });
 it('falls back to a window resize listener when ResizeObserver is unavailable',()=>{
  vi.stubGlobal('ResizeObserver',undefined);
  const host=new Harness(EditorCanvas,editorProps());
  expect(host.canvas().props.style.width).toBe(200);expect(window.addEventListener).toHaveBeenCalledWith('resize',expect.any(Function));
  host.unmount();expect(window.removeEventListener).toHaveBeenCalledWith('resize',expect.any(Function));mounted.splice(mounted.indexOf(host),1);
 });
 it('scopes every docking rule to the animation workspace shell',()=>{
  const css=readFileSync(new URL('../src/canvas-dock.css',import.meta.url),'utf8').replace(/\/\*[\s\S]*?\*\//g,'');
  const rules=[...css.matchAll(/([^{}]+)\{([^{}]+)\}/g)];
  expect(rules.length).toBeGreaterThan(3);
  for(const [,selector] of rules)for(const part of selector.split(','))expect(part.trim()).toMatch(/^\.animation-workspace \.canvas-shell(?:\s|$)/);
  const stageRule=rules.find(([,selector])=>selector.includes('> .stage'))![2];
  expect(stageRule).toContain('flex: 1 1 0');expect(stageRule).toContain('min-height: 0');expect(stageRule).toContain('overflow: auto');
 });
});

describe('canvas playback clock',()=>{
 it('ignores immutable object identity but tracks semantic timing, ordering and loop changes',()=>{
  const key=canvasTimelineKey(timeline);expect(canvasTimelineKey(structuredClone(timeline))).toBe(key);
  expect(canvasTimelineKey({...timeline,loop:false})).not.toBe(key);
  expect(canvasTimelineKey({...timeline,slots:[...timeline.slots].reverse()})).not.toBe(key);
  expect(canvasTimelineKey({...timeline,slots:timeline.slots.map(s=>({...s,durationMs:s.durationMs+1}))})).not.toBe(key);
 });
 it('plays exact 80/200/400ms boundaries and catches up without duplicated callbacks',()=>{
  const selected=vi.fn(),end=vi.fn(),stop=startCanvasPlayback(timeline,0,1,selected,end);
  tick(79);expect(selected).not.toHaveBeenCalled();tick(80);expect(selected).toHaveBeenLastCalledWith(1);
  tick(199);expect(selected).toHaveBeenCalledTimes(1);tick(200);expect(selected).toHaveBeenLastCalledWith(2);
  tick(399);expect(selected).toHaveBeenCalledTimes(2);tick(400);expect(selected).toHaveBeenLastCalledWith(0);
  tick(999);expect(selected).toHaveBeenLastCalledWith(1);expect(end).not.toHaveBeenCalled();stop();expect(queue.size).toBe(0);
 });
 it('holds the final frame and stops scheduling on a one-shot clip',()=>{
  const selected=vi.fn(),end=vi.fn();startCanvasPlayback({...timeline,loop:false},0,1,selected,end);
  tick(500);expect(selected).toHaveBeenLastCalledWith(2);expect(end).toHaveBeenCalledOnce();expect(queue.size).toBe(0);
 });
 it('starts from the selected slot with the chosen playback speed',()=>{
  const selected=vi.fn();startCanvasPlayback(timeline,1,2,selected,vi.fn());
  tick(59);expect(selected).not.toHaveBeenCalled();tick(60);expect(selected).toHaveBeenLastCalledWith(2);
 });
 it('cancels a queued callback even if it was already captured for dispatch',()=>{
  const selected=vi.fn(),stop=startCanvasPlayback(timeline,0,1,selected,vi.fn()),callback=[...queue.values()][0];
  stop();callback(200);expect(selected).not.toHaveBeenCalled();expect(queue.size).toBe(0);
 });
 it('uses the newest onSelect without resetting sub-frame elapsed time on clones or resize',()=>{
  const props=editorProps(),host=new Harness(EditorCanvas,props);host.click('재생');tick(79);
  const updated=vi.fn();observers[0].resize(180,100);
  host.render({...props,clip:structuredClone(props.clip),snapshot:structuredClone(props.snapshot),onSelect:updated});
  expect(cancelAnimationFrame).not.toHaveBeenCalled();tick(80);expect(updated).toHaveBeenCalledWith('b');expect(props.onSelect).not.toHaveBeenCalled();
  host.render({...host.props,selected:'b',onSelect:updated});
  observers[0].resize(100,60);host.render();tick(199);expect(updated).toHaveBeenCalledTimes(1);
  tick(200);expect(updated).toHaveBeenLastCalledWith('c');expect(cancelAnimationFrame).not.toHaveBeenCalled();
 });
 it('restarts only when actual timeline semantics change',()=>{
  const props=editorProps(),host=new Harness(EditorCanvas,props);host.click('재생');tick(60);
  const next=structuredClone(props.clip);next.loop=false;
  host.render({...props,clip:next});expect(cancelAnimationFrame).toHaveBeenCalledOnce();expect(queue.size).toBe(1);
 });
 it('retains arrows, Home, End and Space without intercepting nested controls',()=>{
  const props=editorProps(),host=new Harness(EditorCanvas,props);
  const stageNode=()=>host.all('div').find(n=>String(n.props.className).startsWith('stage '))!;
  const key=(key:string,nested=false)=>{const currentTarget={},preventDefault=vi.fn();stageNode().props.onKeyDown({key,code:key===' '?'Space':key,target:nested?{}:currentTarget,currentTarget,preventDefault});host.render();return preventDefault;};
  key('ArrowRight');expect(props.onSelect).toHaveBeenLastCalledWith('b');
  host.render({...host.props,selected:'b'});key('ArrowLeft');expect(props.onSelect).toHaveBeenLastCalledWith('a');
  expect(key('End')).toHaveBeenCalledOnce();expect(props.onSelect).toHaveBeenLastCalledWith('c');
  expect(key('Home')).toHaveBeenCalledOnce();expect(props.onSelect).toHaveBeenLastCalledWith('a');
  key(' ');expect(queue.size).toBe(1);key(' ',true);expect(queue.size).toBe(1);key(' ');expect(queue.size).toBe(0);
 });
 it('does not begin playback on an empty timeline',()=>{
  const props=editorProps();props.clip.occurrences=[];const host=new Harness(EditorCanvas,props);
  expect(host.button('재생').props.disabled).toBe(true);
  const node=host.all('div').find(n=>String(n.props.className).startsWith('stage '))!,target={};
  node.props.onKeyDown({code:'Space',target,currentTarget:target,preventDefault:vi.fn()});host.render();expect(queue.size).toBe(0);
 });
});

describe('standalone runtime compatibility',()=>{
 it('keeps 1:1 default and numeric presets, with optional FIT',()=>{
  const host=new Harness(RuntimePlayer,{runtime:runtimeData(),atlasUrl:'local-atlas'});
  expect(host.canvas().props.style.width).toBe(512);
  const select=nodes(host.tree).find(n=>n.props.label==='표시 크기')!;
  select.props.onChange({target:{value:'fit'}});host.render();expect(host.canvas().props.style.width).toBe(200);
  expect(host.tree.props.className).toContain('canvas-shell');
 });
 it('does not reset slots or restart RAF on a runtime clone or stage resize',()=>{
  const runtime=runtimeData(),host=new Harness(RuntimePlayer,{runtime,atlasUrl:'local-atlas'});host.click('재생');tick(80);host.render();
  expect(text(host.tree)).toContain('2 / 3');tick(199);observers[0].resize(120,80);
  host.render({runtime:structuredClone(runtime),atlasUrl:'local-atlas'});expect(text(host.tree)).toContain('2 / 3');
  tick(200);host.render();expect(text(host.tree)).toContain('3 / 3');expect(cancelAnimationFrame).not.toHaveBeenCalled();
 });
 it('resets playback when the actual export is replaced',()=>{
  const runtime=runtimeData(),host=new Harness(RuntimePlayer,{runtime,atlasUrl:'local-atlas'});host.click('재생');tick(80);host.render();
  host.render({runtime:{...runtime,exportId:'new-export'},atlasUrl:'new-atlas'});
  expect(text(host.tree)).toContain('1 / 3');expect(queue.size).toBe(0);
 });
});
