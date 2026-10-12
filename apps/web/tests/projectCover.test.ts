import {describe,expect,it} from 'vitest';
import {projectCoverAsset} from '../src/referenceLabel';
import type {Snapshot} from '../src/types';

const assets=['sheet','hiddenFrame','frame','identity','oldIdentity'].map(assetId=>({assetId,url:`/${assetId}.png`}));
const base={assets,activeReferenceRevisionId:'legacy',
 references:[{referenceRevisionId:'old',identityAssetId:'oldIdentity'},{referenceRevisionId:'broken',identityAssetId:'missing'}],
 frames:[{imageAssetId:'missingFrame',rawAssetId:'sheet',hidden:false},{imageAssetId:'hiddenFrame',rawAssetId:'sheet',hidden:true},{imageAssetId:'frame',rawAssetId:'sheet',hidden:false}]} as unknown as Snapshot;
const cover=(p:Partial<Snapshot>)=>projectCoverAsset({...base,...p})?.assetId;

describe('project cover image',()=>{
 it('uses the active identity reference first',()=>{
  expect(cover({activeReferenceRevisionId:'active',references:[...base.references,{referenceRevisionId:'active',identityAssetId:'identity'} as any]})).toBe('identity');
 });
 it('skips a legacy active id, broken assets and hidden frames to use a visible frame image, not the sheet',()=>{
  expect(cover({})).toBe('frame');
 });
 it('falls back to a valid reference, then the first asset',()=>{
  expect(cover({frames:[]})).toBe('oldIdentity');
  expect(cover({frames:undefined,references:undefined})).toBe('sheet');
  expect(projectCoverAsset({})).toBeUndefined();
 });
});
