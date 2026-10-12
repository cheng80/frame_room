# 구현 통합 계약 (DATA_API_SPEC의 구체화)
Python 모듈은 repository root에서 import. API base /v1, port 8765. React dev 5173 proxy.
Project snapshot: {projectId,schemaVersion:1,revision,name,characterName,createdAt,updatedAt,assets:Asset[],references:Reference[],activeReferenceRevisionId:null|string,frames:Frame[],alignmentGroups:Group[],alignments:{[frameVersionId]:Alignment},clips:Clip[],outline:Outline,generationSettings:{},journal:[],generations:[]}
Asset: {assetId,name?:string,sha256,decodedHash,originalFilename,mediaType,width,height,role,alphaStats:{transparent,partial,opaque},provenance,url:'/v1/assets/{id}/content'} (storageKey internal DB)

자료 표시 이름은 프로젝트 snapshot의 optional `asset.name`으로 보관한다. 기존 `/v1/projects/{pid}/edits`의 `{type:'renameAsset',assetId,name}`으로 편집하며 문자열·최대 200자·앞뒤 공백 제거·빈 이름과 중복 이름을 허용한다. 비우거나 이전 자료에 이름이 없으면 `originalFilename`을 표시한다. 이름 변경은 기존 저장 버전 충돌 검사와 이력·복원 절차를 따르고, 원본 파일명·내용·해시·asset ID·출처·기준/후보 연결 및 승인 상태는 유지한다. 잘못된 이름, 없는 자료 ID, 다른 프로젝트의 자료 ID는 전체 edits를 원자적으로 거절한다. 실제 파일 이름과 전역 리소스 메타데이터는 변경하지 않는다.
Frame: {frameId,frameVersionId,parentFrameVersionId?,rawAssetId,imageAssetId,sourceRect:{x,y,width,height},sourceToFrameTransform:{scaleX:1,scaleY:1,offsetX,offsetY},extractionVersion:'raw-v1',nativeScaleGroupId,review:'pending'|'approved'|'rejected',reviewReason?:string,reviewReferenceRevisionId?:string,hidden:false}
Group: {alignmentGroupId,groupRevisionId,frameVersionIds,mode:'preserve-source-scale'|'shared-scale-foot-anchor',sharedScale:1,cell:{width:512,height:512,edge:2},targetAnchor:{x:256,y:494},bodyMeasurement:null|{topY,bottomY,targetHeight,approved?:boolean},resampler:'nearest',roundingVersion:'js-round-v1'}
Alignment: {frameVersionId,groupRevisionId,sourceAnchor:{x,y},anchorSpace:'crop',method:'automatic'|'manual',contactMode:'grounded'|'airborne',rootAnchor?:{x,y},authoredOffsetPx:{x:0,y:0},approval:'pending'|'approved'}
Clip: {clipId,clipRevisionId,name,stateId,facing:'right',referenceRevisionId,loop:true,endBehavior:'hold-last',defaultFps:10,occurrences:Occurrence[],review:'pending'|'approved'}
Occurrence: {occurrenceId,frameVersionId,durationMs:100,timingMode:'fps'|'explicit',transform:{dx:0,dy:0,scaleX:1,scaleY:1,rotationDeg:0,shearX:0,shearY:0,flipX:false,flipY:false,pivot:{x:256,y:256}},pixelEdits:[{x,y,color:[r,g,b,a]}]}
Reference: {referenceRevisionId,name?:string,identityAssetId,styleAssetIds:[],poseAssetIds:[],fixedTraits,allowedChanges,forbiddenTransfers,facing,bodyMeasurement:null,approval:'draft'|'approved'}

6단계 제작의 [승인 없는 실행 계약](../../docs/product/SIX_STEP_WORKFLOW.md): 기존 approval/review 필드·진단·승인 API·schemaVersion·revision 이력은 그대로 보존한다. 마이그레이션이나 일괄 자동 승인을 하지 않는다. 기준 `draft` 및 후보·앵커·동작 `pending`은 생성·검사·bake·export를 막지 않는다. 기준 연결은 계속 필요하며 `generate.params.referenceRevisionId`(생략 시 기존 activeReferenceRevisionId)와 `clip.referenceRevisionId`로 지정한다. 기준 생성은 activeReferenceRevisionId를 자동 변경하지 않는다. 명시적 `rejected` 프레임이 타임라인에 남으면 최종 출력은 `FRAME_REJECTED`로 거절하며 프레임을 제거하거나 review를 변경해야 한다. 프레임을 몰래 누락하여 재생 시간을 바꾸지 않는다.

몸 기준 공통 배율은 승인 체크박스 없이 유한한 topY/bottomY, 양수 체고와 `sharedScale = targetHeight / (bottomY - topY)`로 검증한다. API 편집에서는 좌표 범위·목표 체고·배율 범위도 검사한다. 픽셀·알파·범위·변형·시간·파일 존재/해시·기준 연결·계보·오래된 그룹/프레임 앵커 검증은 유지한다. 승인 메타데이터와 기술 QA 결과는 독립적이며, 출력 성공이 프로젝트 승인 값이나 revision을 변경하지 않는다. 기존 편집의 review 무효화 이력 및 명시적 재승인 동작은 유지한다.

기준 그림 이름은 표시용 메타데이터다. 기준 생성의 optional `reference.name`과 기존 `/v1/projects/{pid}/edits`의 `{type:'renameReference',referenceRevisionId,name}`으로 지정한다. 이름은 문자열·최대 200자이며 앞뒤 공백을 제거한다. 빈 이름은 자동 표시 이름으로 돌아간다. 이전 snapshot의 이름 누락을 지원하고 중복 이름도 허용한다. 이름 변경은 기존 revision 충돌 검사·저장 이력을 따르며 기준/동작 승인·연결 ID·그림·원본 파일명과 clipRevisionId를 변경하지 않는다. 잘못된 이름과 없는 기준 ID는 전체 edits를 원자적으로 거절한다.
Outline: {enabled:false,mode:'preview-only'|'bake',teamLabel,colorRGBA:[66,190,255,255],thicknessPx:2,directions:8,opacityPerCopy:0.8,rendererVersion:'outline-v1'}

GET /projects -> {projects:[snapshot summaries]}; POST /projects {name,characterName,cell?:{width,height}} -> snapshot. GET /projects/{id} -> snapshot. Assets multipart files,role,importMode -> {assets,savedRevision}. Reference POST {expectedRevision,reference:{...}} -> {referenceRevisionId,savedRevision}; approve POST {expectedRevision,reviewChecks:{identity:true}} -> ACK.
PATCH edits {expectedRevision,operations:[{type,...}]} -> {savedRevision,snapshot}. Allowed concrete operations:
- setGenerationSettings {settings}
- renameReference {referenceRevisionId,name}: 표시 이름만 변경하며 기준·동작 승인과 원본은 보존
- createClip {clip:{name,...}}; deleteClip {clipId} removes that clip and its current occurrences from the snapshot while retaining source data and saved history; updateClip {clipId,changes:{name,loop,defaultFps,facing,referenceRevisionId,review}}
- addOccurrence {clipId,frameVersionId,index?}; removeOccurrence {clipId,occurrenceId}; reorderOccurrences {clipId,occurrenceIds}; duplicateOccurrence {clipId,occurrenceId}
- setTiming {clipId,occurrenceId,durationMs,timingMode}; setTransform {clipId,occurrenceId,transform}; setPixelEdits {clipId,occurrenceId,pixelEdits}
- replaceFrameVersion {clipId,occurrenceId,frameVersionId}; setFrameReview {frameVersionId,review,reason?,hidden?} (rejected requires a reason)
- setAlignmentGroup {alignmentGroupId,changes:{sharedScale,cell,targetAnchor,mode,bodyMeasurement}}
- setAlignment {frameVersionId,alignment:{...}}; setOutline {outline}; updateCharacter {name}
UI holds edits draft + explicit save, undo/redo local draft. After ACK refresh snapshot. 409 keep draft and explicit reapply using refreshed revision.
POST jobs {operation,inputRevision,assetIds:[],params:{...},idempotencyKey} -> {jobId,status,eventUrl}; GET /projects/{p}/jobs -> {jobs:[]}; GET /jobs/{j} -> job including createdAt, updatedAt and attemptId; events SSE; cancel {expectedStatus}; retry {failedStep,reuseCheckpoint,idempotencyKey} creates a new attemptId and preserves prior attempt/output records. Published artifacts live under project `outputs/{jobId}/{attemptId}/`.
preview_follow/check_handed are local, non-mutating clip analysis jobs; apply_follow publishes the exact successful preview as a new pending-review clip. Full parameters, source/revision checks and publication contract: [CLIP_TOOLS.md](CLIP_TOOLS.md).
extract params: {mode:'whole'|'grid'|'components'|'regions',rows:1,columns:1,regions:[{x,y,width,height}],groupId?,minArea:4}. Results append frames + group, do NOT auto add timeline. cutout params {key:'white'|'magenta'|'green'|'auto',tolerance:24}. Result asset only, user then extract.
align/inspect/bake params {clipIds?:[],clipRevisionIds?:[]}; job.artifacts [{artifactId,name,url,mediaType}], job.result includes {qa,manifest?}. bake emits bundle for preview; export requires technical integrity gates, never approval flags. Non-strict preview retains `needs_review` QA status; it is not a request for manual approval.
POST exports {savedRevision,clipRevisionIds,formats:['atlas','pngs','runtime','aseprite'],outlineMode:'bake'|'preview-only',idempotencyKey} -> {exportId,jobId}; GET exports/{id} -> {status,manifest,files:[{artifactId,name,url,sha256}]}. Bundle names atlas.png, pngs.zip,runtime.json,aseprite.json,bundle.zip. Additional GET projects/{p}/exports.
POST backup {savedRevision} -> job; POST projects/restore multipart backupZip,idempotencyKey -> job. POST restore-revision {expectedRevision,targetRevision}; POST duplicate {expectedRevision,name}. GET projects/{p}/revisions -> {revisions:[{revision,createdAt,reason}]}.
Errors top-level {code,message,stage,details,...}; health {api:'ready',worker:'ready'|'offline',engine:{version,commit},sessionToken}; mutations X-Session-Token header from health, same origin checks.

프로젝트 폴더·SQLite 계약:
- [PROJECT_FOLDERS.md](PROJECT_FOLDERS.md)를 따른다. 기본 `SPRITE_DATA_DIR/projects/<이름>--<ID>` 또는 지정 부모 폴더에 `project.json`, `project.sqlite3`, `assets/`, `videos/`, `jobs/`, `outputs/`를 보관한다.
- `POST /v1/projects/{pid}/reveal`은 해당 프로젝트 폴더를 Finder/탐색기로 열며 `storageLayout: 'project-folder'`를 반환한다. 건강 상태의 `projectStorage.defaultParent`가 기본 부모 경로다.
- `DELETE /v1/projects/{pid}`는 프로젝트 삭제다. `{expectedRevision: integer >= 1}`을 검증하고 진행 작업이 있으면 409로 거부한다. 인덱스와 함께 등록된 프로젝트 폴더를 실제로 삭제하고 `{deletedProjectId, folderDeleted}`를 반환한다. 폴더가 없으면 인덱스만 지우며 다시 만들지 않는다. 안전 검증·실패 복구 순서는 [PROJECT_FOLDERS.md](PROJECT_FOLDERS.md)를 따른다. 폴더 이동은 삭제가 아니라 이동 후 새 위치 열기다.
- `GET /v1/project-folders/missing`과 `POST /v1/project-folders/cleanup`은 루트 폴더가 사라진 등록을 정리한다. 실행 직전 ID·경로·버전·폴더 부재·진행 작업을 다시 확인하며 변경이 있으면 전체 요청을 거부한다.
- 폴더 저장 실패는 503 `PROJECT_FOLDER_SYNC_FAILED`이며 인덱스의 보류 데이터는 유지한다. `storage.syncPending`은 폴더 반영이 끝나지 않았음을 표시한다. 앱 재시작 또는 같은 폴더 재열기로 복구한다.
- 이전 공용 원본은 자동으로 삭제하지 않는다. 없는 폴더 정리는 파일 삭제·디스크 공간 회수 기능이 아니다. 세션 토큰·Origin 보호를 유지한다.

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
- build_bundle(snapshot,clip_ids:list,asset_path,output_dir:Path,export_id:str,strict:bool=True,outline_mode='bake')->dict {manifest,qa,files:list[str]}. strict validates alignment/frame/clip/reference technical integrity and overflow/empty, independent of approval flags; explicit rejected frames block export. Raise PipelineError with .code,.details,.message. Single fixed render, alpha0 RGB normalized, PNG recrop atlas. Preview same artifacts.
Provider module (agent owns adapters/spritegen/provider.py + engine fork): providers()->list dictionaries; generate(params:dict,reference:dict,asset_path:callable,out_dir:Path,regeneration_target?:{frameVersionId,imageAssetId,sha256})->dict {paths:list[str],receipt:dict,requestSnapshot:dict,providerId,model}; params providerId/model/prompt/frameCount/resolution/quality/scope. Caller runs separate subprocess and controls cancellation. No retries. Exceptions ProviderError .code/.message/.outcome_unknown. Readiness no generation; explicit codex only available subscription, disabled alternatives explanation.

Image adapter 1.3.0 adds optional `layoutGuide: boolean` (default false, only `frameCount: 1`). It builds a local composition guide and appends it after user references with role `derived-guide`; requestSnapshot records its hash/path/cell and exact dispatched enginePrompt. The original params.prompt is preserved. The guide is a derived control image, not a generated original; it consumes no extra generation request. Raw output alpha is inspected without replacing the original PNG. Video extensions are specified in [VIDEO.md](VIDEO.md).

자료 이미지 생성은 기존 `generate` 작업의 `scope: asset`, `frameCount: 1`, `providerId: codex`로 요청한다. 기준·참조 이미지·선택 프레임·구도 가이드 없이 GPT ImageGen으로 이미지 한 장을 생성하며, `referenceRevisionId`와 `frameVersionId`, 별도 `assetIds` 및 `layoutGuide: true`는 접수 전에 거부한다. `prompt`는 공백이 아닌 문자열이며 20,000자 이하이다. 생성 원본과 정확한 요청·영수증을 기존 자료/생성 이력에 보존하고 기준을 자동 생성하거나 승인하지 않는다. states/sheet/frame 작업에는 기존 기준 연결이 필요하지만 승인 여부는 요구하지 않는다. 자료 가져오기 화면의 **AI로 이미지 생성**은 이 모드로 열고 버튼 클릭이나 모드 진입만으로 생성 요청을 보내지 않는다. 자료 모드 설정은 기존 동작 생성 설정을 덮어쓰지 않는다.

Image preparation settings also persist `imageUse: "frames" | "grok-video"` (default `frames`) and optional `videoBase: {direction, facing, pose, bodyPlan, equipment}`. Direction is `side/front/back/front_diagonal/back_diagonal`, facing is `right/left`, and pose is `walk/idle`; bodyPlan/equipment are strings up to 2,000 characters. `imageUse` and `videoBase` are editor settings, not provider job parameters. The editor keeps the original prompt/frame count/scope, and for `grok-video` submits one image with `scope: states`, appending the chosen view/pose and instructions excluding glow/particles/magic effects/shadows. Choosing the mode or saving settings never requests a Grok video; the separate video generation action remains explicit.

이미지 `generate.params`는 optional `viewDirection: side/front/back/front_diagonal/back_diagonal`, `viewFacing: right/left`를 받는다. 방향 지정 시 좌우 생략은 `right`이며 원본 params에 기본값을 덧쓰지 않는다. 정면·뒷면의 보기 지시에는 좌우를 적용하지 않는다. 방향 없이 좌우만 지정하거나 잘못된 타입·값을 보내면 공유 `provider.validate_view_params`가 `ProviderError`로 거절하고 API는 enqueue 전에 같은 code/details를 가진 422를 반환한다. optional `bodyPlan`, `equipment`는 각각 2,000자 이하 문자열만 검사하며 원문을 요청·snapshot에 보존한다. 구조 문법 검사는 영상 요청 시 기존 검증을 따른다. 이 필드는 이미지의 장비 파싱이나 구도 가이드 생성 방식을 변경하지 않는다.

명시적 방향이 있으면 실행용 prompt 및 참조의 `fixedTraits`·`allowedChanges`에만 [공유 규칙](view-direction-rules.json)을 적용한다. 참조의 이전 `facing`은 실행용 prompt에서 생략하며 `forbiddenTransfers`는 그대로 전달한다. identity 첨부는 외형·의상·색·비율의 기준이고 보기 각도는 선택값을 따름을 본문에 명시한다. 선택 방향 지시는 구도 가이드까지 결합한 최종 `enginePrompt` 맨 끝에 추가한다. 정면은 몸 전체가 관찰자를 향하고 대각선은 몸·머리가 함께 45도 방향을 따른다. 승인 참조, 원본 prompt/params와 snapshot 원문은 수정하지 않는다. `viewDirection` 없는 기존 생성의 prompt는 기존과 같다.

공유 JSON은 `{patterns: string[], negativePattern: string}`이며 Python `re.IGNORECASE`와 JavaScript `RegExp(..., 'gi')`에서 같은 순서로 적용한다. `strip_view_instructions(text)`는 `([.!?。\n,;，；])`로 구분자를 포함해 나누고, 보기 방향을 금지하는 `negativePattern`에 해당하는 절은 보존한다. 나머지 절에 patterns를 순서대로 빈 문자열 치환하고 공백을 한 칸으로 정리한다. 빈 절과 그 뒤 구분자는 버리고, 남은 절에 원래 뒤 구분자를 붙여 공백으로 연결한다. 대각선은 일반 정면/측면보다 먼저 처리한다. 효과 금지(`without glow`, `효과 없는`, `효과 제외`)만으로 방향 정리를 막지 않는다. 알려진 한국어·영어 긍정 보기 표현만 지원하는 좁은 정리이며 임의의 자연어를 해석하지 않는다. 손·장비·자세·효과 자체는 제거 대상이 아니다.

Runtime manifests include frameSources (raw asset/crop/generation/parent versions) and sourceAssets with complete parent ancestry and provenance. Asset cards label real-provider originals and descendants by recorded provenance, never by appearance or filename.

Additional bake/export deliverables: `animations.zip` and `animation-manifest.json` are returned as downloadable artifacts and included in `bundle.zip`. The animation ZIP contains its own identical `manifest.json` and per-clip `strip.png`, `grid.png`, `animation.gif`, `animation.webp`. Names combine safe clip IDs, an ID hash, and sanitized display names; original names remain metadata only. Existing atlas/runtime/PNG/Aseprite semantics and technical integrity gates are unchanged; approval flags are not output prerequisites.

All additional files consume the same canonical atlas-recrops as `pngs.zip`; they never re-render candidates. Strips are horizontal, grids use `ceil(sqrt(frameCount))` columns. Differing cell sizes receive transparent top-left padding without resizing; occurrence metadata keeps each original cell size, anchor, order, duration and sheet rectangle. PNG sheets and decoded lossless WebP are verified against every canonical cell. WebP uses loop 0 for repeat and 1 for one-shot, records decoded duration/count/slot mapping, and permits merged identical neighboring frames only when pixels and total timing remain exact. Constant/single-frame clips retain an animation container with the original duration. Missing Pillow WebP support omits that format with `WEBP_UNAVAILABLE`, not a lossy fallback.

GIF output preserves binary-alpha cells with at most 255 visible colors exactly; otherwise it composites partial alpha on black and quantizes each frame to 255 colors without dithering, with alpha <=128 transparent. Metadata explicitly reports format lossiness, changed pixel counts, threshold, rounded durations and total timing error. Durations use integer centisecond cumulative-boundary rounding, avoiding per-frame drift. Any source frame shorter than 10ms omits the clip's GIF with `GIF_TIMING_UNREPRESENTABLE`; other formats keep the original millisecond timing. One-shot GIFs omit the looping extension. Sheet size limits and unavailable codecs appear as per-format omissions in both the animation manifest and runtime/QA warnings; they never approve or mutate a clip.

Shared helper: `alignment.animation_exports.write_animation_formats(cells, durations, loop, out_dir)` accepts final `PIL.Image` cells and integer millisecond durations and returns `{files, formats, warnings, cell, frameCount, version}`. Files are relative filenames under a private output directory and cannot overwrite existing files. Callers publish only after all round-trip checks succeed. `build_animation_exports` provides the equivalent per-clip ZIP entries and manifest for the canonical bake.

영상 제작 확장: [VIDEO.md](VIDEO.md). `snapshot.videos`는 MP4 리소스이며 이미지 `assets`와 별개다. `generate_video`와 `process_video`는 새 후보·공통 배율 그룹·검수 대기 clip을 함께 등록한다. 기존 `extract`의 타임라인 동작은 유지한다. Grok 로그인 경로만 사용하며, durable 요청 ID 조회 재개 및 원본 MP4 기반 로컬 재처리를 지원한다. 프로젝트 ZIP에는 MP4와 영상 계보도 포함한다.
