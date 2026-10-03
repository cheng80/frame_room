import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {Play,Pause,ChevronLeft,ChevronRight,ZoomIn,ZoomOut} from 'lucide-react';
import {drawOccurrence,loadImage,occurrenceAt,validateRuntime} from './render';
import {Check,Select,Panel,Empty,short} from './ui';
import type {Snapshot,Clip,Point,Runtime} from './types';
import './canvas-dock.css';

type Zoom = 'fit' | number;
export type CanvasTimeline = {id:string;loop:boolean;slots:{id:string;durationMs:number}[]};

/** FIT uses the stage's content box (padding is not usable canvas space). */
export function fitCanvasZoom(width:number,height:number,availableWidth:number,availableHeight:number){
 if(![width,height,availableWidth,availableHeight].every(v=>Number.isFinite(v)&&v>0))return 0;
 return Math.min(availableWidth/width,availableHeight/height);
}

/** Only a semantic timeline change may restart playback, not an immutable clone. */
export function canvasTimelineKey(timeline:CanvasTimeline){
 return JSON.stringify({id:timeline.id,loop:timeline.loop,slots:timeline.slots.map(s=>({id:s.id,durationMs:s.durationMs}))});
}

/** Clock-based RAF loop, also exercised without a browser by the unit oracle. */
export function startCanvasPlayback(timeline:CanvasTimeline,index:number,speed:number,onFrame:(index:number)=>void,onEnd:()=>void){
 const durations=timeline.slots.map(s=>s.durationMs);
 if(!durations.length||durations.some(d=>!Number.isFinite(d)||d<=0)||!Number.isFinite(speed)||speed<=0){onEnd();return()=>{};}
 let active=true,raf:number|undefined,current=Math.max(0,Math.min(durations.length-1,index));
 const total=durations.reduce((sum,d)=>sum+d,0);
 const start=performance.now()-durations.slice(0,current).reduce((sum,d)=>sum+d,0)/speed;
 const tick=(now:number)=>{
  if(!active)return;
  const elapsed=Math.max(0,(now-start)*speed),next=occurrenceAt(durations,elapsed,timeline.loop);
  if(next!==current){current=next;onFrame(next);}
  if(!active)return;
  if(!timeline.loop&&elapsed>=total){active=false;onEnd();return;}
  raf=requestAnimationFrame(tick);
 };
 raf=requestAnimationFrame(tick);
 return()=>{active=false;if(raf!==undefined)cancelAnimationFrame(raf);};
}

function usePlayback(playing:boolean,key:string,index:number,speed:number,onFrame:(index:number)=>void,onEnd:()=>void){
 const latest=useRef({index,onFrame,onEnd});
 useLayoutEffect(()=>{latest.current={index,onFrame,onEnd};},[index,onFrame,onEnd]);
 useEffect(()=>{
  if(!playing)return;
  const timeline:CanvasTimeline=JSON.parse(key);
  return startCanvasPlayback(timeline,latest.current.index,speed,i=>latest.current.onFrame(i),()=>latest.current.onEnd());
 },[playing,key,speed]);
}

function useCanvasViewport(width:number,height:number,initialZoom:Zoom='fit'){
 const stage=useRef<HTMLDivElement>(null);
 const [mode,setMode]=useState<Zoom>(initialZoom),[size,setSize]=useState({width:0,height:0});
 useLayoutEffect(()=>{
  const element=stage.current;if(!element)return;
  const update=(w:number,h:number)=>setSize(old=>old.width===w&&old.height===h?old:{width:Math.max(0,w),height:Math.max(0,h)});
  const measure=()=>{
   const css=getComputedStyle(element),number=(value:string)=>parseFloat(value)||0;
   update(element.clientWidth-number(css.paddingLeft)-number(css.paddingRight),element.clientHeight-number(css.paddingTop)-number(css.paddingBottom));
  };
  measure();
  if(typeof ResizeObserver==='undefined'){window.addEventListener('resize',measure);return()=>window.removeEventListener('resize',measure);}
  const observer=new ResizeObserver(entries=>{
   for(const entry of entries)if(entry.target===element)update(entry.contentRect.width,entry.contentRect.height);
  });
  observer.observe(element);
  return()=>observer.disconnect();
 },[]);
 const zoom=mode==='fit'?fitCanvasZoom(width,height,size.width,size.height):mode;
 return {stage,mode,zoom,setZoom:setMode};
}

function ZoomControls({width,mode,zoom,setZoom}:{width:number;mode:Zoom;zoom:number;setZoom:(zoom:Zoom)=>void}){
 return <>
  <button title="축소" aria-label="축소" onClick={()=>setZoom(Math.max(.125,(zoom||1)/2))}><ZoomOut size={16}/></button>
  <button aria-pressed={mode==='fit'} onClick={()=>setZoom('fit')}>맞춤</button>
  <button aria-pressed={mode===1} onClick={()=>setZoom(1)}>1:1</button>
  <button aria-pressed={mode===128/width} onClick={()=>setZoom(128/width)}>게임 128px</button>
  <button title="확대" aria-label="확대" onClick={()=>setZoom(Math.min(8,(zoom||1)*2))}><ZoomIn size={16}/></button>
  <span className="muted">{mode==='fit'?'맞춤 · ':''}{Math.round(zoom*100)}%</span>
 </>;
}

export function EditorCanvas({snapshot,clip,selected,onSelect,onPixel,tool='select',onion=false}:{snapshot:Snapshot;clip?:Clip;selected:string;onSelect:(id:string)=>void;onPixel?:(p:Point)=>void;tool?:string;onion?:boolean}){
 const canvas=useRef<HTMLCanvasElement>(null);
 const [playing,setPlaying]=useState(false),[background,setBackground]=useState('checker'),[speed,setSpeed]=useState(1),[showOutline,setShowOutline]=useState(true),[error,setError]=useState('');
 const occurrences=clip?.occurrences||[],index=Math.max(0,occurrences.findIndex(o=>o.occurrenceId===selected)),occ=occurrences[index];
 const frame=snapshot.frames.find(f=>f.frameVersionId===occ?.frameVersionId),group=snapshot.alignmentGroups.find(g=>g.alignmentGroupId===frame?.nativeScaleGroupId);
 const width=group?.cell.width||512,height=group?.cell.height||512,viewport=useCanvasViewport(width,height);
 const timelineKey=canvasTimelineKey({id:clip?.clipId||'',loop:clip?.loop??true,slots:occurrences.map(o=>({id:o.occurrenceId,durationMs:o.durationMs}))});
 usePlayback(playing,timelineKey,index,speed,i=>{if(occurrences[i])onSelect(occurrences[i].occurrenceId);},()=>setPlaying(false));
 useEffect(()=>{
  let active=true;setError('');if(!occ)return;
  void(async()=>{try{
   const im=await drawOccurrence(snapshot,occ,showOutline);
   if(!active||!canvas.current)return;
   const c=canvas.current;c.width=im.width;c.height=im.height;
   const ctx=c.getContext('2d')!;ctx.imageSmoothingEnabled=false;ctx.clearRect(0,0,c.width,c.height);
   if(onion){for(const neighbor of [occurrences[index-1],occurrences[index+1]].filter(Boolean)){
    const ghost=await drawOccurrence(snapshot,neighbor,false);if(!active)return;ctx.globalAlpha=.2;ctx.drawImage(ghost,0,0);
   }}
   ctx.globalAlpha=1;ctx.drawImage(im,0,0);
  }catch(e){if(active)setError((e as Error).message);}})();
  return()=>{active=false;};
 },[snapshot,occ,onion,showOutline]);
 const step=(delta:number)=>{setPlaying(false);if(occurrences.length)onSelect(occurrences[Math.max(0,Math.min(occurrences.length-1,index+delta))].occurrenceId);};
 return <div className="canvas-shell">
  <div className="canvas-toolbar">
   <span className="badge">편집 미리보기</span>
   <Select label="보기 배경" value={background} onChange={e=>setBackground(e.target.value)}><option value="checker">투명 격자</option><option value="dark">어두운 배경</option><option value="light">밝은 배경</option><option value="green">게임 배경</option></Select>
   <ZoomControls width={width} {...viewport}/>
  </div>
  <div ref={viewport.stage} className={`stage ${background}`} tabIndex={0} aria-label="애니메이션 편집 캔버스. Space 재생, 좌우 프레임 이동, Home 처음, End 마지막" onKeyDown={e=>{
   if(e.target!==e.currentTarget)return;
   if(e.code==='Space'){e.preventDefault();if(occ)setPlaying(p=>!p);}
   if(e.key==='ArrowLeft'){e.preventDefault();step(-1);}
   if(e.key==='ArrowRight'){e.preventDefault();step(1);}
   if(e.key==='Home'){e.preventDefault();step(-occurrences.length);}
   if(e.key==='End'){e.preventDefault();step(occurrences.length);}
  }}>
   {occ?<canvas ref={canvas} style={{width:width*viewport.zoom,height:height*viewport.zoom,cursor:tool==='select'?'default':'crosshair'}} aria-label={`선택 슬롯 ${index+1}, ${width}×${height}, ${occ.durationMs}밀리초`} onPointerDown={e=>{
    if(tool==='select'||!onPixel)return;e.currentTarget.setPointerCapture(e.pointerId);
    const r=e.currentTarget.getBoundingClientRect();if(r.width&&r.height)onPixel({x:Math.floor((e.clientX-r.left)/r.width*width),y:Math.floor((e.clientY-r.top)/r.height*height)});
   }} onPointerMove={e=>{
    if(!e.buttons||tool==='select'||!onPixel)return;
    const r=e.currentTarget.getBoundingClientRect();if(r.width&&r.height)onPixel({x:Math.floor((e.clientX-r.left)/r.width*width),y:Math.floor((e.clientY-r.top)/r.height*height)});
   }}/>:<Empty title="재생할 프레임이 없습니다"><p>아래 후보를 재생 순서에 추가해 주세요.</p></Empty>}
  </div>
  {error&&<p role="alert" className="error">{error}</p>}
  <div className="playbar">
   <button aria-label="이전 프레임" disabled={!occ} onClick={()=>step(-1)}><ChevronLeft size={17}/></button>
   <button className="play" disabled={!occ} onClick={()=>setPlaying(p=>!p)}>{playing?<Pause size={17}/>:<Play size={17}/>} {playing?'일시 정지':'재생'}</button>
   <button aria-label="다음 프레임" disabled={!occ} onClick={()=>step(1)}><ChevronRight size={17}/></button>
   <span className="mono">{occ?index+1:0} / {occurrences.length}</span>
   <Select label="미리보기 속도" value={speed} onChange={e=>setSpeed(Number(e.target.value))}>{[.25,.5,1,2].map(v=><option key={v} value={v}>{v}×</option>)}</Select>
   <Check label="테두리 보기" checked={showOutline} onChange={setShowOutline}/>
  </div>
  <p className="caption">빠른 편집 화면입니다. 최종 픽셀·경계 검수는 출력 결과에서 확인하세요.</p>
 </div>;
}

export function RuntimePlayer({runtime,atlasUrl,initialZoom=1}:{runtime:Runtime;atlasUrl:string;initialZoom?:Zoom}){
 const [clipId,setClipId]=useState(runtime.clips[0]?.id),[index,setIndex]=useState(0),[playing,setPlaying]=useState(false),[error,setError]=useState('');
 const canvas=useRef<HTMLCanvasElement>(null),clip=runtime.clips.find(c=>c.id===clipId)||runtime.clips[0];
 const occurrence=clip?.occurrences[index]||clip?.occurrences[0],f=runtime.frames.find(f=>f.id===occurrence?.renderedFrameId);
 // Standalone file viewer retains its original 1:1 default and numeric presets.
 const viewport=useCanvasViewport(f?.rect.width||512,f?.rect.height||512,initialZoom);
 const timelineKey=canvasTimelineKey({id:clip?.id||'',loop:clip?.loop??true,slots:(clip?.occurrences||[]).map(o=>({id:o.id,durationMs:o.durationMs}))});
 useEffect(()=>{setIndex(0);setPlaying(false);},[clip?.id,runtime.exportId,atlasUrl]);
 usePlayback(playing,timelineKey,index,1,setIndex,()=>setPlaying(false));
 useEffect(()=>{
  let active=true;setError('');if(!f)return;
  loadImage(atlasUrl).then(i=>{
   if(!active||!canvas.current)return;
   if(i.width!==runtime.atlas.width||i.height!==runtime.atlas.height)throw new Error('아틀라스 크기와 runtime 정보가 다릅니다.');
   const c=canvas.current;c.width=f.rect.width;c.height=f.rect.height;
   const ctx=c.getContext('2d')!;ctx.imageSmoothingEnabled=false;ctx.clearRect(0,0,c.width,c.height);
   ctx.drawImage(i,f.rect.x,f.rect.y,f.rect.width,f.rect.height,0,0,c.width,c.height);
  }).catch(e=>{if(active)setError(e.message);});
  return()=>{active=false;};
 },[atlasUrl,f,runtime.atlas.width,runtime.atlas.height]);
 return <div className="canvas-shell runtime-canvas-shell">
  <div className="canvas-toolbar row">
   <Select label="재생 동작" value={clip?.id} onChange={e=>setClipId(e.target.value)}>{runtime.clips.map(c=><option key={c.id} value={c.id}>{c.name||c.id}</option>)}</Select>
   <Select label="표시 크기" value={viewport.mode} onChange={e=>viewport.setZoom(e.target.value==='fit'?'fit':+e.target.value)}><option value="fit">맞춤</option>{[.25,.5,1,2,4].map(z=><option key={z} value={z}>{z*100}%</option>)}</Select>
   <span className="badge success">출력 결과 재생 · 버전 {runtime.projectRevision}</span>
  </div>
  <div ref={viewport.stage} className="stage checker">{f&&<canvas ref={canvas} style={{width:f.rect.width*viewport.zoom,height:f.rect.height*viewport.zoom}} aria-label="출력 아틀라스 프레임"/>}</div>
  {error&&<p className="error" role="alert">{error}</p>}
  <div className="playbar">
   <button disabled={!occurrence} onClick={()=>{setPlaying(false);setIndex(Math.max(0,index-1));}}>이전</button>
   <button className="primary" disabled={!occurrence} onClick={()=>setPlaying(p=>!p)}>{playing?'일시 정지':'재생'}</button>
   <button disabled={!occurrence} onClick={()=>{setPlaying(false);setIndex(Math.min(clip.occurrences.length-1,index+1));}}>다음</button>
   <span>{occurrence?index+1:0} / {clip?.occurrences.length||0} · {occurrence?.durationMs} ms · {clip?.loop?'반복':'단발 · 마지막 유지'}</span>
  </div>
  <p className="caption">앵커 ({f?.anchor?.join(', ')}) · 출력 {short(runtime.exportId)} · 추가 변형 없이 원본 아틀라스 영역을 표시합니다.</p>
 </div>;
}
export function FileViewer(){const [runtime,setRuntime]=useState<Runtime|null>(null),[atlas,setAtlas]=useState<File|null>(null),[url,setUrl]=useState(''),[error,setError]=useState(''),[verified,setVerified]=useState(false);useEffect(()=>{setVerified(false);if(!atlas||!runtime)return;let active=true;const object=URL.createObjectURL(atlas);(async()=>{try{const im=await loadImage(object);if(im.width!==runtime.atlas.width||im.height!==runtime.atlas.height)throw new Error('PNG 크기가 runtime.json과 일치하지 않습니다.');if(runtime.atlas.sha256){const bytes=await atlas.arrayBuffer();const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(b=>b.toString(16).padStart(2,'0')).join('');if(hash!==runtime.atlas.sha256)throw new Error('파일 SHA-256이 다릅니다. 같은 출력의 파일을 선택해 주세요.');}if(active){setUrl(object);setVerified(true);setError('');}}catch(e){if(active)setError((e as Error).message);}})();return()=>{active=false;URL.revokeObjectURL(object);};},[runtime,atlas]);return <Panel title="출력 파일 뷰어" eyebrow="INDEPENDENT PLAYER"><p className="muted">프로젝트나 서버 없이 runtime.json과 atlas.png만으로 순서·시간·앵커를 확인합니다.</p><div className="row"><label className="file-button">runtime.json 선택<input type="file" accept=".json,application/json" onChange={async e=>{const file=e.target.files?.[0];if(!file)return;try{setRuntime(validateRuntime(JSON.parse(await file.text())));setError('');}catch(err){setRuntime(null);setError((err as Error).message);}}}/></label><label className="file-button">atlas.png 선택<input type="file" accept="image/png" onChange={e=>setAtlas(e.target.files?.[0]||null)}/></label></div>{error&&<p role="alert" className="error">{error}</p>}{runtime&&verified?<RuntimePlayer runtime={runtime} atlasUrl={url}/>:<Empty title="같은 출력의 파일 두 개를 선택하세요"><p>임의 JSON 실행이나 파일 업로드 없이 이 브라우저에서 검사합니다.</p></Empty>}</Panel>}
