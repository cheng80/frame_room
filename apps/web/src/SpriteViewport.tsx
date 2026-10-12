import {useLayoutEffect,useRef,useState,type ReactNode} from 'react';
import {ZoomIn,ZoomOut} from 'lucide-react';
import './sprite-viewport.css';

export type Zoom = 'fit' | number;
/** FIT uses the stage's content box (padding is not usable canvas space). */
export function fitCanvasZoom(width:number,height:number,availableWidth:number,availableHeight:number){
 if(![width,height,availableWidth,availableHeight].every(v=>Number.isFinite(v)&&v>0))return 0;
 return Math.min(availableWidth/width,availableHeight/height);
}

export function useCanvasViewport(width:number,height:number,initialZoom:Zoom='fit'){
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
 const fitZoom=fitCanvasZoom(width,height,size.width,size.height);
 const zoom=mode==='fit'?fitZoom:mode;
 return {stage,mode,zoom,fitZoom,setZoom:setMode};
}

export function ZoomControls({width,mode,zoom,fitZoom=1,setZoom,gamePreview=false,onStep}:{width:number;mode:Zoom;zoom:number;fitZoom?:number;setZoom:(zoom:Zoom)=>void;gamePreview?:boolean;onStep?:(direction:-1|1)=>void}){
 const minimum=Math.min(1/64,(fitZoom||1)/4),maximum=Math.max(64,fitZoom*4);
 return <>
  <button type="button" title="축소" aria-label="축소" disabled={zoom>0&&zoom<=minimum} onClick={()=>onStep?onStep(-1):setZoom(Math.max(minimum,(zoom||1)/2))}><ZoomOut size={16}/></button>
  <button type="button" title="화면에 맞춤 · 처음 보기로" aria-pressed={mode==='fit'} onClick={()=>setZoom('fit')}>맞춤</button>
  <button type="button" title="원래 크기 · 1:1 픽셀" aria-pressed={mode===1} onClick={()=>setZoom(1)}>1:1</button>
  {gamePreview&&<button type="button" aria-pressed={mode===128/width} onClick={()=>setZoom(128/width)}>게임 128px</button>}
  <button type="button" title="확대" aria-label="확대" disabled={zoom>=maximum} onClick={()=>onStep?onStep(1):setZoom(Math.min(maximum,(zoom||1)*2))}><ZoomIn size={16}/></button>
  <span className="muted">{mode==='fit'?'맞춤 · ':''}{Math.round(zoom*100)}%</span>
 </>;
}

export function SpriteViewport({width,height,label,children,className=''}:{width:number;height:number;label:string;children:ReactNode;className?:string}){
 const viewport=useCanvasViewport(width,height);
 return <div className={`sprite-viewport ${className}`}>
  <div className="sprite-zoom-controls" role="group" aria-label={`${label} 보기 배율`}><ZoomControls width={width} {...viewport}/></div>
  <div ref={viewport.stage} className="sprite-stage checker" role="region" tabIndex={0} aria-label={`${label} 이미지 영역`}>
   <div className="sprite-frame" style={{width:width*viewport.zoom,height:height*viewport.zoom}}>{children}</div>
  </div>
 </div>;
}

export function SpriteImage({src,alt,width,height,className}:{src:string;alt:string;width?:number;height?:number;className?:string}){
 const [natural,setNatural]=useState({src:'',width:1,height:1}),[failed,setFailed]=useState('');
 const w=width||(natural.src===src?natural.width:1),h=height||(natural.src===src?natural.height:1);
 return <SpriteViewport width={w} height={h} label={alt} className={className}>
  {failed===src?<p className="error" role="alert">이미지를 읽지 못했습니다.</p>:<img src={src} alt={alt} onLoad={e=>{const image=e.currentTarget;setNatural({src,width:image.naturalWidth,height:image.naturalHeight});}} onError={()=>setFailed(src)}/>}
 </SpriteViewport>;
}
