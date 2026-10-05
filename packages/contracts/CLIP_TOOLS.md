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
