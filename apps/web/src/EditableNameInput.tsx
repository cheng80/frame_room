import {Input} from './ui';
import type {Studio} from './useStudio';
import type {Operation} from './types';

export function EditableNameInput({s,name,inputKey,label,placeholder,onRename,ariaLabel}:{s:Studio;name:string;inputKey:string;label:string;placeholder:string;onRename:(name:string)=>Operation;ariaLabel?:string}) {
 return <Input key={`${inputKey}:${name}`} label={label} aria-label={ariaLabel} defaultValue={name} maxLength={200} disabled={s.busy||!!s.conflict} placeholder={placeholder} onBlur={e=>{
  const next=e.currentTarget.value.trim();e.currentTarget.value=next;
  if(!s.busy&&!s.conflict&&next!==name)s.edit(onRename(next));
 }} onKeyDown={e=>{
  if(e.key==='Escape'){e.currentTarget.value=name;e.currentTarget.blur();}
  if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.blur();}
 }}/>
}
