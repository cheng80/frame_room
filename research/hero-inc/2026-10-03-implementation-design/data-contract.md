# 프로젝트·작업·정렬·출력 데이터 계약

**새 앱용 제안 계약 v1**이다. 현재 sprite-gen이 이 형식을 이미 읽는다는 뜻이 아니다. 기존 엔진 형식은 `sprite-request.json`, `frames/frames-manifest.json`, `curation.json`, `manifest.json`이며 adapter가 명시적으로 변환한다. 외부 사용자는 이 파일을 직접 편집하지 않는다.

## 1. 데이터 소유권과 버전

| 엔터티 | 필수 필드 | 변경/참조 규칙 |
|---|---|---|
| Project | projectId, schemaVersion, headRevision, name, createdAt, characterIds, activeCharacterId | autosave에 expectedRevision 필요; 원자적 commit 성공 때만 UI saved 표시 |
| Asset | assetId, sha256, originalFilename, mediaType, width, height, storageKey, alphaStats, provenance | bytes 불변, 상대 storageKey만. 원본/변환/생성 구분. 중복 업로드는 hash로 묶되 사용자 label 유지 |
| Character | characterId, name, activeReferenceRevisionId, alignmentGroupIds, clipIds | reference 변경은 새 revision 채택이며 이전 lineage 보존 |
| ReferenceRevision | referenceRevisionId, identityAssetId, styleAssetIds, poseAssetIds, fixedTraits, allowedChanges, forbiddenTransfers, facing, bodyMeasurement, approval | 각 참조 역할을 보존. 승인 뒤 불변. pending/approved/superseded 상태와 승인시각 |
| GenerationVersion | generationVersionId, jobId, referenceRevisionId, stateId, requestSnapshot, providerId, model, inputAssetIds, promptHash, providerReceipt, rawAssetIds | 같은 state 재생성도 새 ID. requestSnapshot에 요청 숫자/실제 결과 숫자/미지원 옵션 포함. secret 제외 |
| FrameVersion | frameId, frameVersionId, generationVersionId(nullable), rawAssetId, cutoutArtifactId, sourceRect, sourceToFrameTransform, extractionVersion, nativeScaleGroupId, qa | frameId는 논리 lineage, frameVersionId는 특정 불변 픽셀 버전. index나 파일명으로 정체성을 추정하지 않음 |
| AlignmentGroup | alignmentGroupId, referenceRevisionId, frameVersionIds, bodyMeasurement, targetBodyHeight, sharedScale, cell, targetAnchor, overflowPolicy, resampler, roundingVersion | source의 같은 배율이 검수된 그룹에만 적용. common scale 변경은 group revision 전체 변경 |
| FrameAlignment | frameVersionId, groupRevisionId, sourceAnchor, method, measurementPolicy, contactMode, rootAnchor, manualApproval, residual | anchor는 원본/로컬 crop 좌표 구분. source 해시가 다르면 자동 재사용 금지 |
| ClipRevision | clipId, clipRevisionId, stateId, facing, loop, endBehavior, defaultFps, occurrences[] | 순서와 timing의 권위. 같은 frameVersion을 여러 occurrence가 참조할 수 있음 |
| Occurrence | occurrenceId, frameVersionId, durationMs, authoredOffsetPx, transform, pixelEditRevision | 재사용 pose의 개별 위치/시간. clone도 별도 occurrence ID; 원본FrameVersion은 공통 |
| EditRevision | revisionId, parentRevisionId, changeSet, createdAt, affectedIds | undo/redo는 새 head; 파괴적 rewrite 아님. UI 임시 드래그 상태는 commit 이후만 canonical |
| Job / Attempt | jobId, operation, status, inputRevision, idempotencyKey, attemptId, step, progress, events, checkpoint, engineVersion, artifacts, errors | 같은 요청의 복수 전송 방지와 외부 provider 접수 불확실성을 구분 |
| ExportSnapshot | exportId, projectRevision, clipRevisionIds, engineCommit, adapterVersion, renderRecipeHash, assetHashes, files, qaStatus | 모든 artifact가 검증된 후 한 묶음 publish. 이전 export 유지 |

sourceRect는 `(x,y,width,height)`이고 좌상단0, 우/하 경계 exclusive다. sha256은 업로드 파일 bytes와 decoded image fingerprint를 별도 구분한다. 원본 bytes hash를 export PNG hash와 동일해야 한다고 요구하지 않는다. 코드 적용 기록은 처리 전후 두 asset과 인자·버전을 연결한다.

[project.example.json](project.example.json)은 실제 공개 PNG의 hash와 측정 anchor를 사용한 설계 예시다. reference 승인은 pending, bodyMeasurement는 null이며 인체 체고를 확인했다고 가장하지 않는다. 이 예시의 `preserve-source-scale`은 이미 정렬된 입력을 s=1로 가져오는 초기 모드다. 몸 체고에 따른 목표 크기 변경은 bodyMeasurement 승인 후 `shared-scale-foot-anchor`로 전환해야 한다. 예시의 가변 duration은 제안 계약이고 현 엔진 지원을 뜻하지 않는다.

## 2. 정렬 수식과 의미

기준 원본 좌표 `a_raw`와 추출 영역의 원점 `c=(cropX,cropY)`가 있으면 local anchor는 `a_local=a_raw-c`다. 사전 resize가 있었다면 `sourceToFrameTransform`을 적용해야 하며 값을 모르면 `nativeScaleUnverified`로 표시한다. 이미 `slice-sheet`로 정규화한 결과만 있고 원본이 없으면 본래 크기를 복구했다고 주장하지 않는다.

```text
sharedScale = targetBodyHeight / approvedBodyHeight
placement   = targetAnchor - sharedScale * sourceAnchor + authoredOffsetPx
```

approvedBodyHeight는 승인 서기 이미지의 **몸 기준 두 점** 차이다. 거너471/320은 전체 alpha bbox 측정이며 그대로 해부학적 기준 체고라고 저장하지 않는다. 장비가 가장 긴 pose에 맞춰 body scale을 바꾸지 않는다. 생성 batch마다 원래 그린 배율이 달라졌다면 같은 그룹에 자동 혼합하지 않고 기준 포즈와 비교·승인 후 그룹을 교정하거나 재생성한다.

기본 재샘플은 nearest. 제품의 배치 round는 `floor(v+0.5)`로 명시하고 별도 연산 버전으로 고정한다(JS Math.round의 수치값에 맞춤). sprite pixel은 정수, sourceAnchor와 residual은 소수 허용. y=494는 셀의 경계 좌표이며 pixel493까지 내용이 있으면 바닥18px다. round 뒤 anchored point와 목표의 오차를 기록한다.

자동 발 후보 policy: `alphaThreshold=16, bandRatio=0.12, minBand=4, center=extreme-midpoint`. 이 규칙은 거너 preset이다. 엔진 기존20% alpha 가중중심과 이름/버전을 구분한다. 저장된 method는 `manual`, `lower-band-candidate`, `root-trajectory` 중 하나이며 추정값을 confidence 숫자만으로 approved로 바꾸지 않는다.

접지 frame은 targetAnchor를 쓴다. 공중 frame은 발을 매번 바닥에 붙이지 않고 승인 root anchor/trajectory와 authoredOffset을 쓴다. 반동·점프의 의도된 offset과 원치 않는 흔들림을 QA에서 구분한다. body marker·foot ROI·장비 제외 영역을 UI에 남긴다.

변환 순서는 원본 crop/mask → 공통 scale/anchor 배치 → curation pixel edits와 occurrence transform(정의된 canvas 좌표) → optional breathing/기타 승인 effect → outline → 최종 bbox/overflow QA → pack이다. 실제 engine가 지원하는 변환 순서에 맞추어 adapter version을 고정한다. 사용자에게 적용 순서를 숨긴 채 중복 scale/flip하지 않는다. 두 번 정렬되지 않도록 materialized run에는 이미 완료된 alignment version을 명시한다.

overflow 판정은 모든 최종 alpha 픽셀과 outline/effect 포함 영역이 safeRect에 들어가는지 검사한다. `review`가 기본; `expand-cell` 또는 `shrink-entire-group`는 새 group revision. 호환 `per-pose-fit`은 명시 opt-in과 경고이며 P0 애니메이션 수용 경로는 사용하지 않는다.

## 3. 엔진 계약으로 내리는 방법

| 앱의 정보 | 현 엔진 매핑 | 신규 adapter/포크 처리 |
|---|---|---|
| 승인 참조 | `base-source.png`, `refs/`, prepare/gen 참조 입력 | immutable 원본에서 working copy 생성, role manifest+prompt 구성 |
| projectId / generationVersion | run-dir 밖에는 기존 전역 project 없음 | job별 고유 run, app sidecar에서 소유 |
| 동일 캔버스 PNG | `unpack-atlas --pngs-dir` → `frames/frames-manifest.json` | import 전에 공통 배율·발 정렬; 이미 정렬된 pixels 보존 |
| raw row 분리 | `extract` component pipeline | 원시 crop/metadata를 fit 전에 반환하도록 포크 확장; cell별 정규화 적용 여부 기록 |
| frameVersion/occurrence | state+candidate integer index, clone index | `engine-map.json`: materializationId/state/index→frameVersionId/occurrenceId/sha. 새 generation으로 mapping 갱신 |
| 후보 제외·순서·복제 | curation selected/order/clones/transforms/pixels | 같은 selected index 중복은 제거되므로 occurrence마다 clone index 또는 별도 계획 사용. 빈 occurrences는 export 차단하며 engine `selected:[]`(전체로 해석)로 보내지 않음 |
| 저장·불러오기 | curation run/state revision, atomic writer, stale 백업 | app expectedRevision과 engine revision 둘 다 검사. 저장 실패면 bake 시작 금지 |
| 기본fps와 loop | request `states.<state>.fps`, `.loop` → runtime manifest | 클립 revision에서 materialize. UI playback과 export 동일 snapshot |
| occurrence durationMs | 현 compose는 `round(1000/fps)` 균등 durations | 알 수 없는 request field를 조용히 덧붙이지 않음. 새 schema + composer/preview/exporter 동시 지원 후만 활성화 |
| 게임 프레임 | `sprite-sheet-alpha.png`, `manifest.json.frame_layout`, curated PNG | intermediate frames를 export로 표시하지 않음. 최종 bake 또는 그 결과를 단일 입력으로 사용 |
| Aseprite 호환 JSON | frame rect/order/duration, tags | loop/endBehavior/anchor는 companion runtime manifest로 유지. 지원 범위 UI 표시 |

현재 `export-pngs --selected-only`와 `compose-atlas`의 단순 선택·이동·pixel edit 경로는 로컬 검증했다. `export-pngs` 기본은 전체 물리 후보이며 breathe phase를 굽지 않는다. 따라서 제품 최종 PNG는 **compose된 동일 atlas rect에서 추출**하여 preview와 같은 bitmap을 쓴다. 기존 export-pngs는 검증된 정적 편집/호환용 경로로만 구분한다. breathing, rig, 모든 advanced effect의 제품 지원은 회귀 검증 전 활성화하지 않는다. compose의 자동 heal이 frames를 바꿀 수 있으므로 고정된 export run 사본에서만 수행하고 source generation hashes를 검사한다.

가변 duration 구현 전 중간 시제품은 **균등 FPS+명시적 hold 복제**를 제공하고 제한을 표시한다. P0 최종 수용에는 가변 duration 저장·재생·출력 구현이 필요하다. 가변 duration UI가 활성화되는 버전은 preview/atlas/PNG manifest/Aseprite JSON 소비자 모두 같은 occurrence timing을 읽어야 한다. 작은 GCD로 frame을 수백 번 복제해 가변시간을 조용히 근사하지 않는다.

## 4. API 계약

모든 `/v1` 경로는 **새로 만들 API**다. 기존 curation `/api/*`와 같다고 오해하지 않는다. 구체 CLI 대응과 단계별 처리/취소는 [cli-api-matrix.md](cli-api-matrix.md).

| API | 요청 | 응답과 중요 규칙 |
|---|---|---|
| `POST /v1/projects` | name, storageLocationToken, characterName | 201 projectId/revision. 임의 절대 경로 대신 UI 선택 토큰 |
| `GET /v1/projects/{p}` | — | 200 canonical snapshot+ETag |
| `POST /v1/projects/{p}/assets` | multipart files, role, importMode | 201 assetIds+alpha/size summaries; processing 필요하면202 job |
| `POST /v1/projects/{p}/reference-revisions` | identity/style/pose asset IDs, traits, facing, measurement | 201 draft revision |
| `POST /v1/reference-revisions/{r}/approve` | expectedProjectRevision, reviewChecks | 200 immutable approved revision |
| `GET /v1/providers` | — | capability list와 installed/auth/lastProbe/lastGenerationSuccess; secret 없음 |
| `POST /v1/projects/{p}/jobs` | operation, inputRevision, assetIds, params, idempotencyKey | 202 jobId; operation은 generate/cutout/extract/align/inspect/bake/export 허용목록. prepare는 generate 선행 stage, import는 extract의 입력 모드. 부분 재생성은 generate+params.scope/frameVersionIds |
| `GET /v1/jobs/{j}` | — | status/step/progress/artifacts/errors/currentAttempt |
| `GET /v1/jobs/{j}/events` | Last-Event-ID | SSE 저장된 seq부터 재전송; 완료 뒤도 GET 복원 가능 |
| `POST /v1/jobs/{j}/cancel` | expectedStatus | 202 cancel_requested 또는200 already_terminal; 실제 종료 후 이벤트 |
| `POST /v1/jobs/{j}/retry` | failedStep, reuseCheckpoint, idempotencyKey | 새 attempt, 생성 재접수는 불명 상태 해결 뒤만 |
| `PATCH /v1/projects/{p}/edits` | expectedRevision, typed operations[] | 200 savedRevision+engineRevision. 409 conflict면 현 snapshot과 충돌 ID 반환 |
| `POST /v1/projects/{p}/restore-revision` | targetRevision, expectedRevision | 200 새 head revision; 과거 artifact 보존 |
| `POST /v1/projects/{p}/exports` | savedRevision, clipRevisionIds, formats, outlineMode | 202 export job. 저장 acknowledgement revision과 일치 필요 |
| `GET /v1/exports/{e}` | — | status, manifest, verified artifact URLs, hash, capabilities |
| `POST /v1/projects/{p}/backup` / `POST /v1/projects/restore` | snapshot / 업로드zip | 검증후 고유 projectId에 복원; overwrite 묵시 허용 안 함 |

공통 422는 fieldErrors, 409는 stale revision/run busy, 413은 업로드한도, 424는 선행 artifact 필요. network error 시 mutation을 임의 반복하지 않고 idempotency key로 결과 조회. artifact URL은 project 범위와 asset ID로 접근하며 임의 filesystem path는 받지 않는다.

작업 결과 예:

```json
{
  "jobId": "job-example-1",
  "status": "needs_review",
  "operation": "align",
  "inputRevision": 12,
  "attemptId": "attempt-example-1",
  "progress": {"step": "overflow-check", "completed": 3, "total": 3, "unit": "frame"},
  "errors": [{"code": "FOOT_ANCHOR_UNVERIFIED", "affectedIds": ["fv-crouch-1"], "retryable": false,
    "nextActions": ["set-manual-anchor", "mark-airborne"]}],
  "published": false
}
```

## 5. 출력 계약

runtime manifest에는 version, exportId, source project/clip revisions, atlas image+SHA+size, coordinate convention, frames의 immutable ID/rect/anchor, animations의 **occurrence 순서**, durationMs, loop, endBehavior, alignment/outline recipe hash를 기록한다. atlas packer가 동일 pixels를 deduplicate해도 occurrence timing과 order는 유지한다.

PNG 파일명 정렬을 재생 순서로 사용하지 않는다. 개별 PNG 출력도 sequence manifest를 포함한다. PNG atlas와 runtime JSON은 서로 hash를 참조하고 staging에서 함께 검증한 뒤 export 디렉터리를 원자적으로 publish한다. zip과 다른 게임용 serializer는 이 확정 snapshot만 읽는다.

픽셀 parity의 기본 oracle은 alpha와 alpha>0의 RGBA다. 완전 투명 픽셀의 숨은 RGB는 정규화 가능하나 보이는 반투명 RGB는 허용 없이 달라지면 실패다. 독립 뷰어가 exported manifest만으로 순서·loop·시간·offset을 재생할 수 있어야 한다. preview-only outline은 이 contract에 bake되지 않고 화면 상태로 저장한다.

## 6. 저장·백업·복구

SQLite transaction에 edit journal/headRevision/job/event를 기록하고 파일은 content-addressed asset store에 저장한다. file write→fsync/rename→DB reference commit 순서를 정하며 orphan 임시파일은 복구 검사 후 정리한다. 파일이 없는데 saved로 표시하는 상태를 만들지 않는다.

프로젝트 백업은 schemaVersion, DB 또는 portable snapshot, 참조 asset과 hashes, frame lineage/mapping, curation edits, timing/alignment/outline, source licenses를 포함한다. provider credential/환경 secret은 포함하지 않는다. 복원은 hash와 schema migration을 검증하고 missing asset을 UI로 재연결한다. 새 engine 버전에서 이전 프로젝트를 열 때는 복사본 migration과 bake 재검증을 수행한다.
