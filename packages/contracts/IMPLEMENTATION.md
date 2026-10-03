# 구현 통합 계약 (DATA_API_SPEC의 구체화)
Python 모듈은 repository root에서 import. API base /v1, port 8765. React dev 5173 proxy.
Project snapshot: {projectId,schemaVersion:1,revision,name,characterName,createdAt,updatedAt,assets:Asset[],references:Reference[],activeReferenceRevisionId:null|string,frames:Frame[],alignmentGroups:Group[],alignments:{[frameVersionId]:Alignment},clips:Clip[],outline:Outline,generationSettings:{},journal:[],generations:[]}
Asset: {assetId,sha256,decodedHash,originalFilename,mediaType,width,height,role,alphaStats:{transparent,partial,opaque},provenance,url:'/v1/assets/{id}/content'} (storageKey internal DB)
Frame: {frameId,frameVersionId,parentFrameVersionId?,rawAssetId,imageAssetId,sourceRect:{x,y,width,height},sourceToFrameTransform:{scaleX:1,scaleY:1,offsetX,offsetY},extractionVersion:'raw-v1',nativeScaleGroupId,review:'pending'|'approved'|'rejected',reviewReason?:string,reviewReferenceRevisionId?:string,hidden:false}
Group: {alignmentGroupId,groupRevisionId,frameVersionIds,mode:'preserve-source-scale'|'shared-scale-foot-anchor',sharedScale:1,cell:{width:512,height:512,edge:2},targetAnchor:{x:256,y:494},bodyMeasurement:null|{topY,bottomY,targetHeight,approved:true},resampler:'nearest',roundingVersion:'js-round-v1'}
Alignment: {frameVersionId,groupRevisionId,sourceAnchor:{x,y},anchorSpace:'crop',method:'automatic'|'manual',contactMode:'grounded'|'airborne',rootAnchor?:{x,y},authoredOffsetPx:{x:0,y:0},approval:'pending'|'approved'}
Clip: {clipId,clipRevisionId,name,stateId,facing:'right',referenceRevisionId,loop:true,endBehavior:'hold-last',defaultFps:10,occurrences:Occurrence[],review:'pending'|'approved'}
Occurrence: {occurrenceId,frameVersionId,durationMs:100,timingMode:'fps'|'explicit',transform:{dx:0,dy:0,scaleX:1,scaleY:1,rotationDeg:0,shearX:0,shearY:0,flipX:false,flipY:false,pivot:{x:256,y:256}},pixelEdits:[{x,y,color:[r,g,b,a]}]}
Reference: {referenceRevisionId,identityAssetId,styleAssetIds:[],poseAssetIds:[],fixedTraits,allowedChanges,forbiddenTransfers,facing,bodyMeasurement:null,approval:'draft'|'approved'}
Outline: {enabled:false,mode:'preview-only'|'bake',teamLabel,colorRGBA:[66,190,255,255],thicknessPx:2,directions:8,opacityPerCopy:0.8,rendererVersion:'outline-v1'}

GET /projects -> {projects:[snapshot summaries]}; POST /projects {name,characterName,cell?:{width,height}} -> snapshot. GET /projects/{id} -> snapshot. Assets multipart files,role,importMode -> {assets,savedRevision}. Reference POST {expectedRevision,reference:{...}} -> {referenceRevisionId,savedRevision}; approve POST {expectedRevision,reviewChecks:{identity:true}} -> ACK.
PATCH edits {expectedRevision,operations:[{type,...}]} -> {savedRevision,snapshot}. Allowed concrete operations:
- setGenerationSettings {settings}
- createClip {clip:{name,...}}; updateClip {clipId,changes:{name,loop,defaultFps,facing,referenceRevisionId,review}}
- addOccurrence {clipId,frameVersionId,index?}; removeOccurrence {clipId,occurrenceId}; reorderOccurrences {clipId,occurrenceIds}; duplicateOccurrence {clipId,occurrenceId}
- setTiming {clipId,occurrenceId,durationMs,timingMode}; setTransform {clipId,occurrenceId,transform}; setPixelEdits {clipId,occurrenceId,pixelEdits}
- replaceFrameVersion {clipId,occurrenceId,frameVersionId}; setFrameReview {frameVersionId,review,reason?,hidden?} (rejected requires a reason)
- setAlignmentGroup {alignmentGroupId,changes:{sharedScale,cell,targetAnchor,mode,bodyMeasurement}}
- setAlignment {frameVersionId,alignment:{...}}; setOutline {outline}; updateCharacter {name}
UI holds edits draft + explicit save, undo/redo local draft. After ACK refresh snapshot. 409 keep draft and explicit reapply using refreshed revision.
POST jobs {operation,inputRevision,assetIds:[],params:{...},idempotencyKey} -> {jobId,status,eventUrl}; GET /projects/{p}/jobs -> {jobs:[]}; GET /jobs/{j} -> job; events SSE; cancel {expectedStatus}; retry {failedStep,reuseCheckpoint,idempotencyKey}.
extract params: {mode:'whole'|'grid'|'components'|'regions',rows:1,columns:1,regions:[{x,y,width,height}],groupId?,minArea:4}. Results append frames + group, do NOT auto add timeline. cutout params {key:'white'|'magenta'|'green'|'auto',tolerance:24}. Result asset only, user then extract.
align/inspect/bake params {clipIds?:[],clipRevisionIds?:[]}; job.artifacts [{artifactId,name,url,mediaType}], job.result includes {qa,manifest?}. bake emits bundle for preview; export requires all gates.
POST exports {savedRevision,clipRevisionIds,formats:['atlas','pngs','runtime','aseprite'],outlineMode:'bake'|'preview-only',idempotencyKey} -> {exportId,jobId}; GET exports/{id} -> {status,manifest,files:[{artifactId,name,url,sha256}]}. Bundle names atlas.png, pngs.zip,runtime.json,aseprite.json,bundle.zip. Additional GET projects/{p}/exports.
POST backup {savedRevision} -> job; POST projects/restore multipart backupZip,idempotencyKey -> job. POST restore-revision {expectedRevision,targetRevision}; POST duplicate {expectedRevision,name}. GET projects/{p}/revisions -> {revisions:[{revision,createdAt,reason}]}.
Errors top-level {code,message,stage,details,...}; health {api:'ready',worker:'ready'|'offline',engine:{version,commit},sessionToken}; mutations X-Session-Token header from health, same origin checks.

Rendering module contract (agent owns alignment/pipeline.py):
- inspect_image(path)-> dict width,height,alphaStats,decodedHash
- extract_regions(path,params)-> list[dict rect:{x,y,width,height}, image:PIL.Image, sourceToFrameTransform:dict] no fit. components reuse engine.
- suggest_anchor(PIL.Image)->{x,y}
- cutout_image(input_path,output_path,params)->dict
- render_occurrence(snapshot,clip,occurrence,asset_path:callable(assetId)->Path,include_outline=True)->(PIL.Image,qa:dict) qa errors array incl overflow, residual
- build_bundle(snapshot,clip_ids:list,asset_path,output_dir:Path,export_id:str,strict:bool=True,outline_mode='bake')->dict {manifest,qa,files:list[str]}. strict validates alignment/frame/clip/reference and overflow/empty; raise PipelineError with .code,.details,.message. Single fixed render, alpha0 RGB normalized, PNG recrop atlas. Preview same artifacts.
Provider module (agent owns adapters/spritegen/provider.py + engine fork): providers()->list dictionaries; generate(params:dict,reference:dict,asset_path:callable,out_dir:Path,regeneration_target?:{frameVersionId,imageAssetId,sha256})->dict {paths:list[str],receipt:dict,requestSnapshot:dict,providerId,model}; params providerId/model/prompt/frameCount/resolution/quality/scope. Caller runs separate subprocess and controls cancellation. No retries. Exceptions ProviderError .code/.message/.outcome_unknown. Readiness no generation; explicit codex only available subscription, disabled alternatives explanation.

Runtime manifests include frameSources (raw asset/crop/generation/parent versions) and sourceAssets with complete parent ancestry and provenance. Asset cards label real-provider originals and descendants by recorded provenance, never by appearance or filename.
