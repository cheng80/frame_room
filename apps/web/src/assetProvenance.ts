import type {Asset} from './types';

type Provenance={kind?:string;providerId?:string;parentAssetId?:string};
function readProvenance(value:unknown):Provenance {
  if(!value||typeof value!=='object'||Array.isArray(value))return {};
  const record=value as Record<string,unknown>;
  return {
    kind:typeof record.kind==='string'?record.kind:undefined,
    providerId:typeof record.providerId==='string'?record.providerId:undefined,
    parentAssetId:typeof record.parentAssetId==='string'?record.parentAssetId:undefined,
  };
}

/** Source identity is provenance + asset ID, never the filename or image appearance. */
export function assetProvenanceLabel(asset:Asset,assets:ReadonlyMap<string,Asset>) {
  const provenance=readProvenance(asset.provenance);
  const roleLabel:Record<string,string>={source:'편집 원본',identity:'외형 기준',style:'스타일 참조',pose:'자세 참고',derived:'파생 자료'};
  const providerLabel:Record<string,string>={codex:'Codex',openai:'OpenAI',grok:'Grok'};
  let label:string;
  switch(provenance.kind){
    case 'real-provider':label=`AI 생성 원본 · ${providerLabel[provenance.providerId||'']||provenance.providerId||'제공자 미기록'}`;break;
    case 'cutout':label='배경 제거 결과';break;
    case 'raw-crop':label='추출 프레임';break;
    case 'imported':case 'upload':case 'uploaded':label='가져온 원본';break;
    default:label=asset.role==='derived'?'파생 이미지':'출처 확인 필요';
  }
  let originLabel:string|undefined;
  if(provenance.kind!=='real-provider'){
    const seen=new Set([asset.assetId]);
    let parentId=provenance.parentAssetId;
    while(parentId&&!seen.has(parentId)){
      seen.add(parentId);
      const parent=assets.get(parentId);
      if(!parent)break;
      const origin=readProvenance(parent.provenance);
      if(origin.kind==='real-provider'){originLabel='AI 생성에서 파생';break;}
      parentId=origin.parentAssetId;
    }
  }
  return {label,roleLabel:roleLabel[asset.role]||'기타 자료',originLabel};
}
