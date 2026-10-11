import type {Studio} from './useStudio';
import type {Asset} from './types';
import {assetLabel} from './assetProvenance';
import {EditableNameInput} from './EditableNameInput';

export function AssetNameInput({s,asset}:{s:Studio;asset:Asset}) {
 const name=asset.name||'';
 return <EditableNameInput s={s} name={name} inputKey={asset.assetId} label="자료 이름" ariaLabel={`자료 이름 · ${assetLabel(asset)}`} placeholder={asset.originalFilename} onRename={name=>({type:'renameAsset',assetId:asset.assetId,name})}/>;
}
