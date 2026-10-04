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

프로젝트 폴더·SQLite 계약:
- [PROJECT_FOLDERS.md](PROJECT_FOLDERS.md)를 따른다. 기본 `SPRITE_DATA_DIR/projects/<이름>--<ID>` 또는 지정 부모 폴더에 `project.json`, `project.sqlite3`, `assets/`, `videos/`, `jobs/`, `outputs/`를 보관한다.
- `POST /v1/projects/{pid}/reveal`은 해당 프로젝트 폴더를 Finder/탐색기로 열며 `storageLayout: 'project-folder'`를 반환한다. 건강 상태의 `projectStorage.defaultParent`가 기본 부모 경로다.
- `DELETE /v1/projects/{pid}`는 목록에서 제거다. `{expectedRevision: integer >= 1}`을 검증하고 진행 작업이 있으면 409로 거부한다. 공용 인덱스의 관련 기록만 정리하며 폴더를 다시 열면 동일 ID·이력·작업·출력을 복원한다.
- `GET /v1/project-folders/missing`과 `POST /v1/project-folders/cleanup`은 루트 폴더가 사라진 등록을 정리한다. 실행 직전 ID·경로·버전·폴더 부재·진행 작업을 다시 확인하며 변경이 있으면 전체 요청을 거부한다.
- 폴더 저장 실패는 503 `PROJECT_FOLDER_SYNC_FAILED`이며 인덱스의 보류 데이터는 유지한다. `storage.syncPending`은 폴더 반영이 끝나지 않았음을 표시한다. 앱 재시작 또는 같은 폴더 재열기로 복구한다.
- 이전 공용 원본은 자동으로 삭제하지 않는다. 인덱스 정리는 파일 삭제·디스크 공간 회수 기능이 아니다. 세션 토큰·Origin 보호를 유지한다.

OpenAPI는 FastAPI `services.api.main.app.openapi()`에서 생성한다. 저장소 루트에서 다음 명령으로 갱신하며 서버/lifespan/DB 초기화는 실행하지 않는다:
```sh
PYTHONDONTWRITEBYTECODE=1 engine/sprite-gen/.venv/bin/python - <<'PY'
import json
from pathlib import Path
from services.api.main import app
Path('packages/contracts/openapi.json').write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + '\n')
PY
```

Rendering module contract (agent owns alignment/pipeline.py):
- inspect_image(path)-> dict width,height,alphaStats,decodedHash
- extract_regions(path,params)-> list[dict rect:{x,y,width,height}, image:PIL.Image, sourceToFrameTransform:dict] no fit. components reuse engine.
- suggest_anchor(PIL.Image)->{x,y}
- cutout_image(input_path,output_path,params)->dict
- render_occurrence(snapshot,clip,occurrence,asset_path:callable(assetId)->Path,include_outline=True)->(PIL.Image,qa:dict) qa errors array incl overflow, residual
- build_bundle(snapshot,clip_ids:list,asset_path,output_dir:Path,export_id:str,strict:bool=True,outline_mode='bake')->dict {manifest,qa,files:list[str]}. strict validates alignment/frame/clip/reference and overflow/empty; raise PipelineError with .code,.details,.message. Single fixed render, alpha0 RGB normalized, PNG recrop atlas. Preview same artifacts.
Provider module (agent owns adapters/spritegen/provider.py + engine fork): providers()->list dictionaries; generate(params:dict,reference:dict,asset_path:callable,out_dir:Path,regeneration_target?:{frameVersionId,imageAssetId,sha256})->dict {paths:list[str],receipt:dict,requestSnapshot:dict,providerId,model}; params providerId/model/prompt/frameCount/resolution/quality/scope. Caller runs separate subprocess and controls cancellation. No retries. Exceptions ProviderError .code/.message/.outcome_unknown. Readiness no generation; explicit codex only available subscription, disabled alternatives explanation.

Runtime manifests include frameSources (raw asset/crop/generation/parent versions) and sourceAssets with complete parent ancestry and provenance. Asset cards label real-provider originals and descendants by recorded provenance, never by appearance or filename.

Additional bake/export deliverables: `animations.zip` and `animation-manifest.json` are returned as downloadable artifacts and included in `bundle.zip`. The animation ZIP contains its own identical `manifest.json` and per-clip `strip.png`, `grid.png`, `animation.gif`, `animation.webp`. Names combine safe clip IDs, an ID hash, and sanitized display names; original names remain metadata only. Existing atlas/runtime/PNG/Aseprite semantics and approval gates are unchanged.

All additional files consume the same canonical atlas-recrops as `pngs.zip`; they never re-render candidates. Strips are horizontal, grids use `ceil(sqrt(frameCount))` columns. Differing cell sizes receive transparent top-left padding without resizing; occurrence metadata keeps each original cell size, anchor, order, duration and sheet rectangle. PNG sheets and decoded lossless WebP are verified against every canonical cell. WebP uses loop 0 for repeat and 1 for one-shot, records decoded duration/count/slot mapping, and permits merged identical neighboring frames only when pixels and total timing remain exact. Constant/single-frame clips retain an animation container with the original duration. Missing Pillow WebP support omits that format with `WEBP_UNAVAILABLE`, not a lossy fallback.

GIF output preserves binary-alpha cells with at most 255 visible colors exactly; otherwise it composites partial alpha on black and quantizes each frame to 255 colors without dithering, with alpha <=128 transparent. Metadata explicitly reports format lossiness, changed pixel counts, threshold, rounded durations and total timing error. Durations use integer centisecond cumulative-boundary rounding, avoiding per-frame drift. Any source frame shorter than 10ms omits the clip's GIF with `GIF_TIMING_UNREPRESENTABLE`; other formats keep the original millisecond timing. One-shot GIFs omit the looping extension. Sheet size limits and unavailable codecs appear as per-format omissions in both the animation manifest and runtime/QA warnings; they never approve or mutate a clip.

Shared helper: `alignment.animation_exports.write_animation_formats(cells, durations, loop, out_dir)` accepts final `PIL.Image` cells and integer millisecond durations and returns `{files, formats, warnings, cell, frameCount, version}`. Files are relative filenames under a private output directory and cannot overwrite existing files. Callers publish only after all round-trip checks succeed. `build_animation_exports` provides the equivalent per-clip ZIP entries and manifest for the canonical bake.

영상 제작 확장: [VIDEO.md](VIDEO.md). `snapshot.videos`는 MP4 리소스이며 이미지 `assets`와 별개다. `generate_video`와 `process_video`는 새 후보·공통 배율 그룹·검수 대기 clip을 함께 등록한다. 기존 `extract`의 타임라인 동작은 유지한다. Grok 로그인 경로만 사용하며, durable 요청 ID 조회 재개 및 원본 MP4 기반 로컬 재처리를 지원한다. 프로젝트 ZIP에는 MP4와 영상 계보도 포함한다.
