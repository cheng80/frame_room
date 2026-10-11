import {useId,useRef} from 'react';
import {CircleHelp,X} from 'lucide-react';
import './property-help.css';

export function PropertyHelp({title,description}:{title:string;description:string}) {
  const id=useId(),trigger=useRef<HTMLButtonElement>(null);
  return <span className="property-help">
    <button ref={trigger} type="button" className="property-help-trigger" aria-label={`${title} 도움말`} popoverTarget={id} onClick={e=>e.stopPropagation()}><CircleHelp size={16} aria-hidden="true"/></button>
    <span id={id} popover="auto" className="property-help-popover" role="note" aria-label={`${title} 설명`} onToggle={e=>{
      // A popover's toggle must not toggle an enclosing details section.
      e.stopPropagation();
      const popup=e.currentTarget,button=trigger.current;
      if(!button||!popup.matches(':popover-open'))return;
      const anchor=button.getBoundingClientRect(),box=popup.getBoundingClientRect();
      popup.style.left=`${Math.max(8,Math.min(anchor.right-box.width,window.innerWidth-box.width-8))}px`;
      const top=anchor.bottom+6+box.height<=window.innerHeight-8?anchor.bottom+6:anchor.top-box.height-6;
      popup.style.top=`${Math.max(8,top)}px`;
    }}>
      <span className="property-help-title"><strong>{title}</strong><button type="button" aria-label={`${title} 도움말 닫기`} popoverTarget={id} popoverTargetAction="hide" onClick={e=>e.stopPropagation()}><X size={14} aria-hidden="true"/></button></span>
      <span className="property-help-description">{description}</span>
    </span>
  </span>;
}

export function PropertyHeading({title,description}:{title:string;description:string}) {
  return <div className="property-heading"><h3>{title}</h3><PropertyHelp title={title} description={description}/></div>;
}
