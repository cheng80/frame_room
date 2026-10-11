import type {Studio} from './useStudio';
import type {Reference} from './types';
import {Input} from './ui';

export function ReferenceNameInput({s,reference,label='기준 그림 이름'}:{s:Studio;reference:Reference;label?:string}) {
 const name=reference.name||'';
 return <Input key={`${reference.referenceRevisionId}:${name}`} label={label} defaultValue={name} maxLength={200} disabled={s.busy||!!s.conflict} placeholder="예: 효과 없는 오른쪽 측면" onBlur={e=>{
  const next=e.currentTarget.value.trim();e.currentTarget.value=next;
  if(!s.busy&&!s.conflict&&next!==name)s.edit({type:'renameReference',referenceRevisionId:reference.referenceRevisionId,name:next});
 }} onKeyDown={e=>{
  if(e.key==='Escape'){e.currentTarget.value=name;e.currentTarget.blur();}
  if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.blur();}
 }}/>
}
