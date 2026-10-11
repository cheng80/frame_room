import {useEffect,useRef,useId,type ReactNode} from 'react';
import {X} from 'lucide-react';

/** Native dialog owns focus trapping, background inertness and Escape. */
export function EditorDialog({open,title,description,actions,children,onClose,className='',closeDisabled=false}:{open:boolean;title:string;description?:string;actions?:ReactNode;children:ReactNode;onClose:()=>void;className?:string;closeDisabled?:boolean}) {
 const titleId=useId();
 const ref=useRef<HTMLDialogElement>(null);
 const trigger=useRef<HTMLElement|null>(null);
 const onCloseRef=useRef(onClose);onCloseRef.current=onClose;
 useEffect(()=>{
  const dialog=ref.current;if(!dialog)return;
  if(open&&!dialog.open){trigger.current=document.activeElement as HTMLElement;dialog.showModal();}
  if(!open&&dialog.open){dialog.close();trigger.current?.focus();}
 },[open]);
 return <dialog ref={ref} className={`editor-tool ${className}`} aria-labelledby={titleId} onKeyDown={e=>{
  if(e.key!=='Tab'||e.defaultPrevented||(e.target as HTMLElement).closest('dialog')!==e.currentTarget)return;
  const controls=Array.from(e.currentTarget.querySelectorAll<HTMLElement>('button,a[href],input,select,textarea,summary,[tabindex]')).filter(el=>el.tabIndex>=0&&!el.matches(':disabled')&&el.getClientRects().length);
  const first=controls[0],last=controls.at(-1);
  if(!first){e.preventDefault();return;}
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
 }} onCancel={e=>{if(e.target!==e.currentTarget)return;e.preventDefault();if(!closeDisabled)onCloseRef.current();}} onClose={e=>{if(e.target===e.currentTarget)onCloseRef.current();}}>
  <header className="tool-header"><div><h2 id={titleId}>{title}</h2>{description&&<p>{description}</p>}</div><div className="tool-header-actions">{actions}<button aria-label="도구 닫기" title="닫기 · Esc" disabled={closeDisabled} onClick={onClose}><X size={18}/></button></div></header>
  {children}
 </dialog>;
}
