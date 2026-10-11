import type {Studio} from './useStudio';
import type {Reference} from './types';
import {EditableNameInput} from './EditableNameInput';

export function ReferenceNameInput({s,reference,label='기준 그림 이름'}:{s:Studio;reference:Reference;label?:string}) {
 const name=reference.name||'';
 return <EditableNameInput s={s} name={name} inputKey={reference.referenceRevisionId} label={label} placeholder="예: 효과 없는 오른쪽 측면" onRename={name=>({type:'renameReference',referenceRevisionId:reference.referenceRevisionId,name})}/>;
}
