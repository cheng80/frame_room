import {describe,it,expect} from 'vitest';
import {assetProvenanceLabel} from '../src/assetProvenance';
import type {Asset} from '../src/types';
const asset=(assetId:string,provenance:unknown,role='source',originalFilename='same.png')=>({assetId,provenance,role,originalFilename}) as Asset;
const labels=(target:Asset,assets:Asset[]=[target])=>assetProvenanceLabel(target,new Map(assets.map(a=>[a.assetId,a])));

describe('asset provenance labels',()=>{
  it('identifies a real Codex image from provider provenance',()=>{
    expect(labels(asset('ai',{kind:'real-provider',providerId:'codex'}))).toEqual({label:'AI 생성 원본 · Codex',roleLabel:'편집 원본',originLabel:undefined});
  });
  it.each(['imported','upload','uploaded'])('labels %s as an imported original without guessing synthesis',kind=>{
    for(const name of ['robot-idle.png','robot-sheet.png','generated.png'])expect(labels(asset('upload',{kind},'identity',name))).toEqual({label:'가져온 원본',roleLabel:'외형 기준',originLabel:undefined});
  });
  it('follows multiple ID-based generations despite identical filenames',()=>{
    const source=asset('source',{kind:'real-provider',providerId:'codex'});
    const cutout=asset('cutout',{kind:'cutout',parentAssetId:'source'},'derived');
    const frame=asset('frame',{kind:'raw-crop',parentAssetId:'cutout'},'derived');
    const sameNameUpload=asset('upload',{kind:'imported'});
    const assets=[sameNameUpload,source,cutout,frame];
    expect(labels(cutout,assets)).toMatchObject({label:'배경 제거 결과',originLabel:'AI 생성에서 파생'});
    expect(labels(frame,assets)).toMatchObject({label:'추출 프레임',originLabel:'AI 생성에서 파생'});
    expect(labels(sameNameUpload,assets).originLabel).toBeUndefined();
  });
  it('does not turn a crop of uploaded material into AI output',()=>{
    const upload=asset('upload',{kind:'imported'}),frame=asset('frame',{kind:'raw-crop',parentAssetId:'upload'},'derived');
    expect(labels(frame,[upload,frame])).toEqual({label:'추출 프레임',roleLabel:'파생 자료',originLabel:undefined});
  });
  it('handles missing parents and cycles without inventing ancestry',()=>{
    const missing=asset('missing',{kind:'cutout',parentAssetId:'absent'},'derived');
    const first=asset('a',{kind:'raw-crop',parentAssetId:'b'},'derived'),second=asset('b',{kind:'cutout',parentAssetId:'a'},'derived');
    expect(labels(missing).originLabel).toBeUndefined();expect(labels(first,[first,second]).originLabel).toBeUndefined();
  });
  it('handles unknown or malformed provenance without filename-based attribution',()=>{
    for(const value of [null,[],42,{kind:42,parentAssetId:{}},{kind:'future-kind'}])expect(labels(asset('unknown',value,'source','robot-idle.png')).label).toBe('출처 확인 필요');
  });
});
