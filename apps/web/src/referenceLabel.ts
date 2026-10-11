import type {Snapshot} from './types';
import {assetLabel} from './assetProvenance';

export function referenceLabel(project:Snapshot,id:string|null|undefined):string {
 const index=project.references.findIndex(r=>r.referenceRevisionId===id);
 if(index<0)return '기준 연결 필요';
 const reference=project.references[index];
 if(reference.name?.trim())return `기준 ${index+1} · ${reference.name.trim()}`;
 const asset=project.assets.find(a=>a.assetId===reference.identityAssetId);
 const filename=asset?assetLabel(asset):undefined;
 const trait=reference.fixedTraits?.trim().split(/[,\n]/)[0].trim();
 return [`기준 ${index+1}`,trait,filename].filter(Boolean).join(' · ');
}
