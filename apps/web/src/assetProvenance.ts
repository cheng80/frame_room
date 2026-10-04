import type {Asset, Video} from './types';

type Provenance={kind?:string;providerId?:string;parentAssetId?:string;sourceVideoId?:string;processing?:string;interpolated?:boolean;interpolationMethod?:string};
function readProvenance(value:unknown):Provenance {
  if(!value||typeof value!=='object'||Array.isArray(value))return {};
  const record=value as Record<string,unknown>;
  return {
    kind:typeof record.kind==='string'?record.kind:undefined,
    providerId:typeof record.providerId==='string'?record.providerId:undefined,
    parentAssetId:typeof record.parentAssetId==='string'?record.parentAssetId:undefined,
    sourceVideoId:typeof record.sourceVideoId==='string'?record.sourceVideoId:undefined,
    processing:typeof record.processing==='string'?record.processing:undefined,
    interpolated:typeof record.interpolated==='boolean'?record.interpolated:undefined,
    interpolationMethod:record.interpolation&&typeof record.interpolation==='object'&&'method' in record.interpolation&&typeof record.interpolation.method==='string'?record.interpolation.method:undefined,
  };
}

/** Source identity is provenance + asset ID, never the filename or image appearance. */
export function assetProvenanceLabel(asset:Asset,assets:ReadonlyMap<string,Asset>,videos?:ReadonlyMap<string,Video>) {
  const provenance=readProvenance(asset.provenance);
  const roleLabel:Record<string,string>={source:'편집 원본',identity:'외형 기준',style:'스타일 참조',pose:'자세 참고',derived:'파생 자료'};
  const providerLabel:Record<string,string>={codex:'Codex',openai:'OpenAI',grok:'Grok'};
  const interpolatedLabel=provenance.interpolationMethod==='rife-ncnn-vulkan'?'RIFE 보간':'영상 보간';
  let label:string;
  switch(provenance.kind){
    case 'real-provider':label=`AI 생성 원본 · ${providerLabel[provenance.providerId||'']||provenance.providerId||'제공자 미기록'}`;break;
    case 'cutout':label='배경 제거 결과';break;
    case 'raw-crop':label='추출 프레임';break;
    case 'video-frame-raw':label='영상 원본 프레임';break;
    case 'video-frame':label=provenance.processing==='video-finish'?(provenance.interpolated?`${interpolatedLabel}·색상 마무리 프레임`:'영상 색상 마무리 프레임'):provenance.interpolated?`${interpolatedLabel} 프레임`:provenance.processing==='video-normalization'?'영상 크기 정규화 프레임':provenance.processing==='chroma-key'||readProvenance(assets.get(provenance.parentAssetId||'')?.provenance).kind==='video-frame-raw'?'영상 배경 제거 프레임':'영상 추출 프레임';break;
    case 'imported':case 'upload':case 'uploaded':label='가져온 원본';break;
    default:label=asset.role==='derived'?'파생 이미지':'출처 확인 필요';
  }
  let originLabel:string|undefined;
  const videoOrigin=(origin:Provenance)=>{
    const video=origin.sourceVideoId?videos?.get(origin.sourceVideoId):undefined;
    const kind=readProvenance(video?.provenance).kind;
    return kind==='real-provider-video'||kind==='real-provider'?'AI 생성 영상에서 파생':kind==='imported-video'||kind==='imported'?'가져온 영상에서 파생':'원본 영상에서 파생';
  };
  if(provenance.sourceVideoId)originLabel=videoOrigin(provenance);
  if(provenance.kind!=='real-provider'){
    const seen=new Set([asset.assetId]);
    let parentId=provenance.parentAssetId;
    while(parentId&&!seen.has(parentId)){
      seen.add(parentId);
      const parent=assets.get(parentId);
      if(!parent)break;
      const origin=readProvenance(parent.provenance);
      if(origin.kind==='real-provider'){originLabel='AI 생성에서 파생';break;}
      if(origin.sourceVideoId){originLabel=videoOrigin(origin);break;}
      parentId=origin.parentAssetId;
    }
  }
  return {label,roleLabel:roleLabel[asset.role]||'기타 자료',originLabel};
}
