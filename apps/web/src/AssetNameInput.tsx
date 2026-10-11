import type {Studio} from './useStudio';
import type {Asset} from './types';
import {assetLabel} from './assetProvenance';
import {Input} from './ui';

export function AssetNameInput({s,asset}:{s:Studio;asset:Asset}) {
 const name=asset.name||'';
 return <Input key={`${asset.assetId}:${name}`} label="자료 이름" aria-label={`자료 이름 · ${assetLabel(asset)}`} defaultValue={name} maxLength={200} disabled={s.busy||!!s.conflict} placeholder={asset.originalFilename} onBlur={e=>{
  const next=e.currentTarget.value.trim();e.currentTarget.value=next;
  if(!s.busy&&!s.conflict&&next!==name)s.edit({type:'renameAsset',assetId:asset.assetId,name:next});
 }} onKeyDown={e=>{
  if(e.key==='Escape'){e.currentTarget.value=name;e.currentTarget.blur();}
  if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.blur();}
 }}/>
}
