import type {Asset,Snapshot} from './types';
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

/** Single-character image for project list/preview: active identity, visible frame image, other identity, then first asset. */
export function projectCoverAsset(project:Partial<Pick<Snapshot,'assets'|'references'|'frames'|'activeReferenceRevisionId'>>):Asset|undefined {
 const assets=project.assets||[];
 const byId=(id?:string)=>id?assets.find(a=>a.assetId===id):undefined;
 const active=project.references?.find(r=>r.referenceRevisionId===project.activeReferenceRevisionId);
 const frame=project.frames?.find(f=>!f.hidden&&byId(f.imageAssetId));
 return byId(active?.identityAssetId)||byId(frame?.imageAssetId)||project.references?.map(r=>byId(r.identityAssetId)).filter(Boolean).at(-1)||assets[0];
}
