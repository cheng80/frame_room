# 선택 동작 도구 계약

2026-10-06. 부위 흔들림과 색 표식 기반 장비 좌우 검사를 기존 `/v1/projects/{id}/jobs`에 연결한다. 외부 생성 호출은 없으며 원본·수동 승인·기존 동작은 변경하지 않는다. 별도 색 복원 기능은 범위에서 제외한다.

## 요청

기존 envelope의 `inputRevision`, `idempotencyKey`, 빈 `assetIds`를 사용한다.

- `preview_follow`: `params = {clipId, clipRevisionId, region:[cx,cy,rx,ry], gain?:2.5, freq?:2.4, damping?:0.6, onFold?:'lower'}`. 타원 좌표는 첫 슬롯의 출력 셀 픽셀이다. `gain` 0~8, `freq` 0.2~12Hz, `damping` 0.05~4, `onFold` lower/refuse. 반복 동작 4~64슬롯, 총 60초 이내만 지원한다. 유한 수·양수 반지름·셀 내부 타원을 검사한다. 셀은 최대 1024×1024, 전체 셀 픽셀은 16,777,216 이하이다.
- `apply_follow`: `params = {previewJobId}`. 같은 프로젝트에서 성공한 `preview_follow` 결과만 사용한다. 미리보기 당시 프로젝트 revision과 현재 `inputRevision`이 같아야 한다. 미리보기 산출물 해시를 확인하고 그 결과를 새 동작으로 등록한다. 처리 도중 revision이 바뀌어도 저장을 거부한다. 동일 제출 키의 중복 저장은 기존 작업을 반환한다.
- `check_handed`: `params = {clipId, clipRevisionId, item, side, part, direction, facing, marker, referenceAssetId?}`. `side` left/right, `part` wrist/hand/head/ankle/body, `direction` side/front/back/front_diagonal/back_diagonal, `facing` left/right, `marker` #RRGGBB. 표식은 해당 장비에만 있는 채도 있는 색이어야 한다. `referenceAssetId`는 같은 프로젝트의 장비가 온전히 보이는 투명 기준 그림이다. 1~64슬롯을 검사하며 위 셀·총시간 한도를 유지한다.

`clipRevisionId` 불일치, 다른 프로젝트 자료, 잘못된 입력은 접수 전에 거부한다. 서버는 저장된 슬롯의 변형·픽셀 편집·공통 배율·앵커를 적용한 최종 셀을 사용하되 팀 테두리는 제외한다. 두 도구 모두 재생 시간과 슬롯 순서를 보존한다. 미승인 후보는 처리할 수 있지만 해시 손상·잘림 등 실제 렌더 오류는 거부한다.

## 결과와 산출물

- 공통 `result.tool`: follow/handed, `version: clip-tools-v1`, `source:{projectId,projectRevision,clipId,clipRevisionId,occurrenceIds}`, `settings`, `report`, `preview`.
- 미리보기 `preview:{width,height,frameCount,durationsMs,before,beforeStrip,firstFrame,after?,afterStrip?,board?}`. 파일명은 job.artifacts의 name과 연결하며 URL은 기존 artifact endpoint를 사용한다. before/after는 애니메이션 WebP, beforeStrip/afterStrip은 PNG, firstFrame과 board는 PNG다. 각 슬롯 PNG도 보존한다.
- 흔들림 `report:{gainRequested,gainApplied,foldLimited,reachPx,unchanged,timingMethod,...}`. 최신 엔진의 몸 움직임·감쇠 응답·타원 변형을 사용한다. 가변 시간은 시간축에서 주기 신호를 계산하고 원래 슬롯 시점으로 되돌린다. 과도한 접힘은 거부하거나 명시적으로 강도를 낮추며 강도를 낮출 수 없으면 실패한다. 이동하는 타원 밖의 RGBA는 유지한다.
- 좌우 검사 `report:{verdict:'clear'|'suspect'|'inconclusive',framesShown,frameCount,suspectFrames:[{index,occurrenceId,reasons:string[]}],unchecked:string[],engineReport}`. 표식을 찾지 못하면 inconclusive다. 표식 색 기준의 의심을 표시할 뿐 의미 기반 장비 인식·자동 수정·수동 승인으로 처리하지 않는다.
- `apply_follow` 결과에는 새 `clipId`와 `previewJobId`를 포함한다. 새 프레임·앵커·동작은 검수 대기이며 원본 clip/occurrence/asset과 설정·미리보기 식별자를 계보에 기록한다. 원본에 효과를 자동 누적하지 않는다. 현재 선택한 동작에서 새 결과를 만드는 명시적 작업이다.

미리보기/검사는 프로젝트의 편집 revision을 올리지 않는다. 원본 비교·프레임 이동·결과 경고·새 동작 저장은 기존 동작 속성의 접힌 도구 패널에서 제공한다. 초안/저장 충돌 상태는 먼저 해결해야 하며 선택 동작이나 설정이 바뀐 미리보기는 저장할 수 없다.


## M3 원본 복원·최종 셀 비교 (2026-10-22)

기존 envelope에 `preview_restore:{clipId,clipRevisionId}`, `compare_clips:{clipId,clipRevisionId,candidateClipId,candidateClipRevisionId}`를 추가한다. `apply_follow:{previewJobId}`는 성공한 follow/restore/compare의 검증된 후보를 같은 게시 트랜잭션에서 새 동작으로 저장한다. 불확실한 대응·회귀·복원 제안 없음은 `canApply:false`이며 저장을 거절한다. 원본·이전 출력·승인은 보존한다. 최종 셀·순서·개별 정수 ms를 별도 PNG/WebP/GIF 및 library/폴더 DB에 함께 저장한다. 완성 결과 저장 실패는 기존 retry의 `reuseResultAttemptId`로 저장만 재시도한다.

- 일반 비교는 `same-sample-defects-v1`/comparison schema1이다. 복원은 `source-restoration-v5`/`key-protected-source-copy-one-step-cap-jump-ghost-guard-v1`, repair schema4와 내장 `comparison.schema_version:6`이다. `bridge_policy`는 `frame-room-canonical-source-v1`·실제 구현 SHA·cap 범위를 별도로 기록한다. 다른 schema/정책을 같은 의미로 읽지 않는다.
- `improved/non_regressing/regressed/unknown`은 같은 샘플·좌표·개별 시간의 최종 픽셀 결함 판정이며 미술 점수가 아니다. 시간/crop/sample mapping/origin/policy/출처를 증명하지 못하면 unknown이다. 일반 비교는 실루엣과 결함 없는 그림 보존의 upstream gate를 사용한다. 사용자 편집을 source로 승격하지 않는다.
- 신규 영상 처리의 `Clip.comparisonEvidence`는 MP4 SHA·준비 이미지(있는 경우)·선택 raw/keyed SHA·추출 receipt·고정 source 투영 셀·최초 origin 셀·최종 좌표/sample mapping/ms를 기록한다. 이미지는 프로젝트 assets에, source/origin PNG와 `source-projection/source-manifest.json`은 별도 출력에도 저장한다. source/origin ID는 콘텐츠 SHA이며 baseline은 현재 최종 셀이다. 후속 저장은 source/origin을 교체하지 않는다. keyed 재투영과 origin부터의 복원 chain을 실제 픽셀로 다시 검증한다.
- padding/팔레트/배치가 raw resample 좌표와 다르면 cap을 추정하지 않고 key hue 증가 픽셀을 보호한다. RGBA raw resample과 최종 셀이 정확히 일치하는 경우만 raw crop 기반 upstream one-step cap을 허용한다. jump/ghost gate는 최종 셀에서 재측정하며 filmed ghost는 복원 대상이 아니다. 보간된 source 투영은 unknown이다. 실제 follow warp의 source 복원은 대응 불명으로 unknown을 유지한다.
- 일반 비교는 follow warp의 복원 제약과 구분한다. `comparisonEvidence.followProof` schema1의 부모 렌더 입력·설정·선택 read-on 입력을 프로젝트 assets와 함께 보존하고, 부모 source/origin·policy·좌표/sample/ms를 검증한 뒤 follow를 재현해 실제 최종 RGBA를 대조한다. 검증된 warp만 upstream 일반 비교 판정을 제공하며 source/origin은 불변이다. 무효 부모·proof 누락·정책/구간/보간 불명은 비교도 unknown이다. 새 follow 저장은 승인된 미리보기 바이트를 재사용하며 일반 비교의 계보 검증에서만 효과를 재현한다. 선택 저장과 ZIP/ID remap 뒤에도 같은 proof를 검증한다.
- 역사 M0 full extraction proof는 2동작뿐이며 나머지21은 unknown, origin23개는 unsupported-legacy다. 과거 origin을 만들어 채우지 않는다. 앱은 현재 프로젝트의 완전한 raw/keyed manifest·원본 영상 SHA를 다시 대조해 확인된 legacy source와 미기록 origin을 별도 상태로 표시한다. 증거 부족은 일반 편집·출력을 막지 않는다.
- `preview_follow`에 `stretchFloor?:0..0.99`, `readOn?:sha256`를 추가한다. 기존 가변시간 응답과 upstream 공통윤곽 carry·stretch floor/Jacobian을 사용하고 슬롯별 최소면적·불투명/변경px·소유관계 unknown을 기록한다. 현재 before strip SHA와 같은 readOn만 same이다. `readOnClipId/readOnClipRevisionId`를 지정하면 같은 영상·구간·crop·배율·마무리·원본 샘플의 픽셀을 대조하고 upstream `cut_origin/transported_motion`으로 정확한 셀의 reading을 운반한다. 이때 SHA는 선택한 읽기 동작의 strip을 가리키며 생략하면 서버가 계산한다. 보간·다른 구간·잘못된 SHA·일치하지 않는 셀은 uncertain이며 영역을 추정 이동하거나 저장하지 않는다.
- project/clip revision·설정·policy가 달라지면 다시 미리보기한다. 저장 시 원본 픽셀·source/origin·후보·산출물 해시와 정책/schema를 재검증한다. ZIP 복원은 asset/video ID를 remap하며 콘텐츠 ID·좌표·시간을 유지한다. 증거는 cache/jobs 경로 없이 검증된다.
