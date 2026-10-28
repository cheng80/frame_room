# 영상 제작 계약

기존 이미지 제작과 편집 계약에 추가한다. 영상은 이미지 asset과 별도인 `snapshot.videos`에 기록한다. 기존 schemaVersion 1 프로젝트의 videos 생략은 빈 목록으로 취급한다.

## API

- `GET /v1/providers`: 기존 이미지 제공자와 `providerId: grok-video`, `mediaKind: video` capability를 반환한다. 로컬 Grok 로그인만 사용하며 API key fallback은 없다. 영상 기본 모델은 `grok-imagine-video-1.5`, 선택 모델은 동일 모델과 `grok-imagine-video-1.5-lite`. 길이 2~6초, 해상도 480p/720p.
- `POST /v1/projects/{id}/videos`: multipart `file`(MP4, 최대 64MiB), `expectedRevision`으로 기존 영상 등록. 반환 `{snapshot, video}`. 생성 호출 없음.
- `GET /v1/videos/{videoId}/content`: 원본 MP4. `Video`는 `{videoId, sha256, originalFilename, mediaType, width, height, fps, frameCount, durationMs, provenance, url}`.
- `POST /v1/projects/{id}/jobs`: 기존 envelope와 idempotencyKey를 유지. operation에 `generate_video`, `process_video` 추가.
- `POST /v1/projects/{id}/video-batches`: `{inputRevision, items:[{assetId, params}], idempotencyKey}`로 1~16개 영상 제작을 원자적으로 접수한다. 각 항목은 `generate_video`와 같은 검증을 받으며 하나라도 잘못되면 전체를 접수하지 않는다. 응답은 `{batchId, jobs}`. 같은 키·같은 내용의 재전송은 같은 작업들을 반환하며 다른 내용이면 409다. 항목별 `batchId`, `batchIndex`(0부터), `batchSize`를 작업에 표시한다. 모델 호출 수는 항목 수이며 실행 버튼에서 이 수를 명시한다. 방향별 기준 그림은 항목마다 사용자가 선택하고 별도 그림을 몰래 생성하지 않는다. 작업 처리기는 저장된 항목을 순차 실행하며 탭이 닫혀도 접수된 작업은 유지된다.
- `generate_video`: assetIds는 기준 그림 하나. params는 `state`(idle/walk/run/jump/attack/dance/wave/cheer), `direction`(side/front/back/front_diagonal/back_diagonal), `facing`(right/left), `motionPrompt`, `model`, `durationSeconds`(기본 3), `resolution`(기본480p), 선택 `referenceRevisionId`, 아래 후처리 설정. 지정한 기준은 같은 프로젝트에 속해야 하며 approval 값은 실행 조건이 아니다.
- `process_video`: assetIds는 빈 배열. params `videoId`는 프로젝트 소속 영상. 선택 `spillReferenceAssetId`는 같은 프로젝트의 원본 기준 이미지이며, 영상 안쪽에 섞인 배경색과 캐릭터 본래 색을 구분하는 데 사용한다. 생략하면 영상 생성 때 보존한 기준 이미지를 사용하고, 그것도 없으면 보수적인 작은 영역 보정만 적용한다. 명시한 기준이 없거나 다른 프로젝트 소속이면 접수 전에 거부한다. `generate_video`는 자체 생성 기준을 사용하므로 이 설정을 받지 않는다. 아래 후처리 설정 적용. 외부 생성 없이 원본을 다시 처리한다.
- 공통 후처리 params: `state` 기본 walk, `key` auto/green/magenta/cyan/white 중 지원 범위, `loopMode` auto/full/manual, 수동 구간 `startFrame`(0부터), `endFrame`(미포함), `maxFrames` 4~64이며 생략 시 walk는 **8**, 나머지는 32다. 명시한 값과 기존 저장 요청은 유지한다. `bodyHeight` 16~512 기본94, `cellWidth` 32~1024 기본64, `cellHeight` 32~1024 기본128. 선택 구간을 시간 순서로 샘플링하며 한 사이클 시간을 유지한다. 구간 불합격을 자동 재생성으로 바꾸지 않는다.
- 공통 `finishMode`: `gif`(기본) 또는 `rgba`. `gif`는 검수한 3배 GIF와 같은 색상·알파 결과를 PNG 후보에 저장한다. 공통 크기 PNG를 출력 셀에 배치하고 nearest 3배 → 검정에 알파 합성 → 프레임별 최대 255색 → 알파 128 이하 제거 → 원래 크기로 복원한다. 이진 알파 PNG 자체가 편집과 bake의 입력이므로 화면만 바꾸는 필터가 아니다. `rgba`는 반투명을 유지한다. 두 모드 모두 원래 크기의 추출·배경 제거 PNG 및 마무리 전 정규화 PNG를 보존한다. 기존 저장 프로젝트의 픽셀을 조회만으로 변경하지 않는다.

## 작업·저장

`build_motion_prompt_parts`는 요청과 snapshot의 `motionPrompt` 원문을 보존하고 실행에 쓰는 custom 문자열에만 [공유 보기 정리 규칙](view-direction-rules.json)을 적용한다. 알려진 이전 긍정 보기·시선 표현을 정리한 뒤 선택 `direction/facing`의 기존 템플릿을 적용한다. 정리 후 custom이 비면 기존 동작 템플릿을 사용한다. 보기 방향 금지문·캐릭터 자신의 손·장비·효과·동작 지시는 보존한다. 효과 금지와 이전 보기 표현이 같은 절에 있어도 보기는 정리한다. 정리된 custom을 기준으로 충돌을 검사하므로 해소된 시선 충돌은 사라지며 장비 좌우 충돌 진단은 유지한다. 알고리즘과 좁은 언어 지원 범위는 [구현 계약](IMPLEMENTATION.md)을 따른다. 기준 이미지 원본이나 생성 provenance를 프롬프트 정리로 바꾸지 않는다.

단계: prepare → submit → poll → download → extract → select_cycle → import_candidates → complete. 접수 ID는 POST 직후 저장한다. 알려진 ID는 재시도 시 GET만 사용한다. 응답을 못 받은 POST는 접수 불명으로 남기고 재전송을 거부한다. 모델 오류·인증 오류에 자동 재생성이나 인증 경로 전환은 없다.

등록한 MP4는 SHA-256 기반 불변 파일로 보관한다. 생성 완료 후 후처리가 실패해도 영상은 프로젝트에서 다시 선택할 수 있다. PNG 후보의 provenance에는 `kind: video-frame`, `sourceVideoId`, `sourceFrameIndex`, `sourceTimeMs`, `interpolated: false`를 기록한다. 원본 프레임과 배경 제거 프레임을 구분한다.

배경 제거 후보의 provenance에는 적용된 `spill` 판정과 선택한 `spillReferenceAssetId`를 기록한다. 작업 결과의 `processing.spill`에도 기준 사용 여부와 보정 강도 판정을 포함한다. 투명 PNG 기준은 원본 알파와 본래 색을 존중하여 판정하며, 기준의 키 색상 의상을 무조건 탈색하지 않는다. 후처리 기준 이미지는 동시 이력 복원·백업 복원에서도 후보와 함께 보존한다. 원본 영상의 생성 출처는 후처리 기준 선택으로 바뀌지 않는다.

영상 후보는 디코딩 원본 → 원래 크기의 배경 제거 PNG → 편집 크기 PNG를 각각 보존한다. 편집 크기는 선택 구간 전체의 공통 영역과 첫 프레임 체고로 계산하고 Lanczos로 한 번 축소한다. 포즈마다 맞추거나 셀에 맞춰 몸 크기를 자동 변경하지 않는다. 편집 크기 PNG는 `processing: video-normalization`이며 `normalization`에 원본 영역·변환·배율을 기록한다. 발 앵커는 원본 첫 프레임 좌표를 같은 변환으로 옮긴다. 이후 기존 편집기의 nearest 샘플링을 배율 1부터 사용한다. 이는 이전 영상 미리보기의 축소 방식과 일치하며, 디코딩된 영상의 작은 색 점을 최근접 축소로 확대하는 문제를 피한다.

결과는 새 공통 배율 그룹과 새 clip에 등록하며 기존 후보·순서를 대체하지 않는다. 결과 job에는 `videoId`, `frameVersionIds`, `clipId`, `processing` 요약을 반환한다. 새 후보·앵커·clip은 검수 대기다. MP4와 영상 계보를 프로젝트 ZIP 백업에 포함하고 복원 시 영상 ID를 재매핑한다.

마무리 PNG의 provenance는 `processing: video-finish`, `parentAssetId`는 정규화 PNG다. `finish`에 모드·팔레트·알파 임계값·샘플링 배수·셀·알고리즘 버전을 기록한다. 작업 결과 `processing.finish`에도 같은 설정을 보존한다. 처리 결과의 미리보기는 최종 후보에서 만들며 원본 영상과 혼동하지 않는다.

## 공개 v2.19 영상 품질 보완

- 방향은 `side/front/back/front_diagonal/back_diagonal`, 동작은 `idle/walk/run/jump/attack/dance/wave/cheer`를 지원한다. 방향별 기준 그림을 재사용하며 시작 자세를 별도 생성할 때는 기존 이미지 생성 화면에서 명시적으로 실행한다. 방향·장비 유지, 대각선 보행의 첫/끝 그림 고정, Lite 보행 지시를 적용한다.
- `finishMode: rgba`는 v2.19의 Hamming 색상·Lanczos 알파 분리 축소로 경계 색 과장을 줄인다. `gif`는 검수한 기존 GIF의 축소·팔레트 조합을 유지한다.
- `repairMode: off/auto/on`(기본 off): 보행·달리기 반복의 튀는 프레임을 로컬 RIFE로 선택 보정한다. `auto`의 도구 부재는 원본 유지와 진단으로 표시하고, `on`에서 필요한 보간 도구가 없으면 실패한다. 원본을 재생성하지 않는다. `/v1/providers`의 `capabilities.rife`는 설치 상태·release·model을 제공한다.
- 선택 `matchClipId`는 같은 프로젝트의 반복 동작이며 4~64프레임, 총 60,000ms 이하여야 한다. 선택한 동작의 슬롯 수와 총 시간에 맞춰 원본 영상 구간을 다시 샘플링하고 접지 시점으로 회전한다. 중간 프레임이 필요하면 로컬 RIFE를 사용하며 없는 도구로 근사 성공을 가장하지 않는다. 전체/단발 구간과 함께 사용할 수 없다. 원래 시간과 변경 시간을 처리 보고서에 함께 남긴다.
- 자동 루프의 느린 보행·크기 흔들림 재탐색은 공개 엔진의 제한된 로컬 재탐색만 사용한다. 원격 재촬영을 자동 실행하지 않는다.
- 보간 프레임은 `interpolated: true`, 입력 프레임 번호·보간 비율·도구를 `interpolation`으로 기록한다. 원본 추출·배경 제거 프레임을 따로 보존하며 bake와 백업에서도 이 계보를 유지한다. 품질 지표는 진단이며 approval/review 메타데이터를 자동 변경하지 않는다.

게임용 출력에는 기존 atlas/runtime/PNG/Aseprite에 더해 동작별 strip PNG·grid PNG·GIF·lossless animated WebP를 별도 ZIP으로 제공한다. 모두 같은 bake의 실제 최종 셀을 사용하며 PNG 픽셀·순서·앵커·밀리초 시간은 runtime이 기준이다. GIF의 10ms 시간 단위 반올림 및 색상/알파 제약은 출력 메타데이터에 기록하고, GIF로 정확히 표현할 수 없는 짧은 프레임은 오류/누락 이유를 명시한다. WebP와 GIF의 반복/단발 여부를 원래 동작과 일치시킨다.

이번 구현 검증은 이미 생성한 실제 MP4를 재사용한다. 실제 원격 생성은 앞선 1회 실측과 주입형 transport 회귀 검사로 구분한다. 브라우저 검증은 허가된 기존 ego TaskSpace에서만 수행한다.

## 공개 v2.34 품질 보완 (2026-10-06)

- `between: auto/on/off`(기본 auto)는 주기 맞춤에서 중간 그림이 필요할 때 적용한다. auto는 최신 보간 품질 검사로 번짐·검은 경계가 감지된 중간 그림을 가까운 원본으로 대체한다. on은 RIFE 강제 사용, off는 가까운 원본 사용이다. `repairMode`와 별도 설정이며, 기본 8장 축소 샘플링에는 중간 그림을 생성하지 않는다.
- `startFoot: auto/left/right`(기본 auto)는 시작 발 분석/주기 정렬에 사용한다. `process_video`의 선택 `startIndex`는 새 출력의 시작을 0부터 지정하며 0~63 및 실제 출력 수 범위를 모두 검사한다. 프레임과 표시 시간을 함께 회전한다. 판정 근거가 부족하거나 신체 구조가 이족이 아니면 발 정체를 확정하지 않는다. 원본 동작/비교 기준 clip의 시작 위치는 변경하지 않는다.
- 생성 명세 `bodyPlan`, `equipment`는 선택 문자열이다. 예: `quadruped`, `the rider=biped; the horse=quadruped`, `sword:right; shield:left`. 장비 좌우는 캐릭터 자신의 좌우이며 빈 필드는 기존 프롬프트와 호환된다. 구문을 접수 전에 검사하며 영상 요청·묶음 snapshot에 포함한다. 명세 전달은 실제 모델 순응의 보장이 아니다.
- 신체 구조 UI는 직접 입력 없이 한글 선택지로 제한한다. `biped`(두 발형), `quadruped`(네 발형), `legless`(다리 없는 형태), `arachnid`(여덟 다리형), `winged_biped`(두 발·날개형), `winged_quadruped`(네 발·날개형)를 지원한다. 추가 형태는 프로젝트 어댑터에서 검증하며 기준 그림과 영상 모두 다리·날개 수와 역할을 명시한다. 날개형의 걷기·달리기는 지상 이동이고 날개를 다리나 사람의 팔로 바꾸지 않는다. 비행 동작은 추가하지 않는다. 기존 복합 명세는 API에서 계속 지원하고 UI에서는 유지 전용으로 표시한다. 새 형태에도 이족 인간 전용 발 정체 판정을 적용하지 않는다.
- `reference`는 목록에 없는 형태도 **기준 그림의 구조 그대로 유지**로 선택할 수 있게 한다. 다리·팔·날개·촉수 등의 수와 부착 위치를 원본 기준에서 유지하도록 지시하며 특정 수나 인간형 자세를 강제하지 않는다. 판별된 골격 데이터가 아니라 프롬프트 지시이며 생성 순응을 보장하지 않는다. 기존 빈 값의 이족 기본 동작은 유지한다.
- `process_video`에 `direction/facing/bodyPlan/equipment`를 명시하지 않으면 영상에 저장된 생성 설정을 재사용한다. 설정도 없으면 기존 기본값을 사용한다. UI의 원본 방향 선택은 명시적 override다.
- 업로드 검사·시간 탐색·디코딩은 같은 영상 stream을 사용한다. 표지 그림 stream과 오디오 길이는 제외한다. 영상 메타데이터의 `streamIndex`와 작업 `processing.source.timesMs`(마지막 종료 경계를 포함한 n+1개)를 기록한다. 평균 FPS로 제안한 구간은 UI에 추정값이라고 표시하고, 처리 후 실제 timestamp를 사용한다.
- `processing.version`은 `video-processing-v4-sprite-gen-2.34`. `selection`에 대응 포즈 크기 변화(`sizeHold`), 주기 혼입(`period`), 그림 갱신 빈도(`held`), 발 판정(`footStrike`), 수동 위상(`outputPhase`), 재검토 권고(`retake`)를 기록한다. 과거 결과의 필드 생략을 허용한다. 재검토 권고는 유료 생성 호출로 이어지지 않는다.
- 크기 보정은 원본 대신 파생 이미지에 적용하며 여백을 확보한 후 색/알파를 분리해 변환한다. 계보에는 padding을 포함한 원본→출력 변환과 실제 보간/원본 대체 여부를 기록한다. 원본 PNG의 `sourceTimeMs`는 반드시 실제 원본 timestamp다.
- WebP는 각 셀을 lossless/exact로 인코딩하고 애니메이션으로 묶는다. 투명 픽셀 RGB·가변 시간·반복 슬롯을 유지하며 기존 전체 RGBA 검사를 그대로 적용한다. 앱 WebP 출력에는 별도 `img2webp` 설치가 필요 없다.

실행 결과와 한계: [최신 공개 스킬 반영 기록](../../docs/product/LATEST_SKILL_UPGRADE_2026-10-06.md).

## 후보 프레임 선별 (2026-10-12 도입, 2026-10-13 Luna+규칙 기본·Laya/Jev 제거)

- 판정은 FrameRoom 코드 정책과 규칙(`frame-rules-v1`)만 쓴다. Laya MLX와 Jev(TypeSafe) 판정은 2026-10-13에 제거했다. 앱은 `laya_mlx`·MLX·TypeSafe HTTP를 import·감지·설치·호출하지 않고 `.env`의 `TYPESAFE_*`도 읽지 않는다.
- params `frameSelection`: `uniform`(기존 균등 샘플링과 동일) 또는 `vision`. `frameJudge`: `rules`. 이전 값 `auto`는 받아서 `rules`로 정규화한다(Laya가 없던 환경의 기존 `auto`와 같은 결과). `laya`·`jev`는 `VIDEO_SETTING`(API·worker 재검증) 또는 `VIDEO_INVALID_PARAMS`(직접 `process_clip`)로 관찰 모델 호출 전에 거절한다. 그 밖의 값도 같은 오류다. `vision`과 `matchClipId`(주기 맞춤)는 함께 쓸 수 없다. 내부 `targetFrameCount` 경로는 관찰하지 않고 `selection.frameSelection.status=skipped`를 남긴다.
- 기본값 경계(신규 vs 기존):
  - 신규 요청: `POST /v1/projects/{pid}/jobs`(`generate_video`/`process_video`)와 `POST /v1/projects/{pid}/video-batches`의 각 항목은 `frameSelection`을 생략하고 `matchClipId`도 없으면 해시 계산 전에 `{frameSelection: "vision", frameJudge: "rules"}`를 요청에 명시해 저장한다. 같은 제출 키로 같은 본문을 다시 보내면 같은 해시다. `matchClipId`가 있으면 생략은 기존처럼 균등이다.
  - 웹 UI 새 설정 기본값은 `vision`+`rules`이며, 클라이언트는 `frameSelection`을 항상 명시한다(`uniform`도 명시 전송). 선택 필드가 없는 예전 설정 객체는 `uniform`으로 보낸다. 주기 맞춤을 고르면 `uniform`으로 보낸다.
  - 기존 데이터: 이미 저장된 작업 요청의 worker 재검증과 직접 `process_clip`(스크립트)은 생략을 계속 `uniform`으로 읽는다. 저장된 요청·설정·작업 기록은 다시 쓰지 않으며 기존 작업에 관찰 모델 호출을 추가하지 않는다. 멱등성: 같은 제출 키의 기존 작업은 저장된 해시가 원본 요청 해시나 기본값을 넣은 요청 해시 중 하나와 같으면 그 작업을 그대로 돌려준다(새 작업·관찰·기본값 기록 없음). 그래서 기본값 도입 전에 생략 형태로 저장된 작업도 같은 원본 요청으로 재전송할 수 있다. 내용이 다르면 `IDEMPOTENCY_CONFLICT`(409)다. 묶음 제출은 원본 본문 해시로 묶음을 찾으므로 그대로 호환된다.
- `vision`은 기존 구간 선택·크기 안정화·RIFE 보정을 거친 뒤, 각 출력 슬롯의 균등 위치와 인접 슬롯 사이의 이웃(슬롯당 최대 ±2, 전체 최대 32장)만 후보로 둔다. 출력 장수(`maxFrames` 의미), 슬롯 순서, 루프 여부, 총 재생 시간을 유지한다. 각 프레임은 자기 원본 시각부터 다음 선택 시각까지 표시하며, 루프에서 첫 슬롯이 앞당겨지지 않은 구간은 마지막 프레임 뒤로 이어 붙인다(단발은 첫 프레임이 구간 시작부터 표시).
- 관찰(v2, `frame-selection-v2`/`frame-observation-v2`): 크기 보정·보간 후 키잉 이미지를 같은 크롭으로 그린 전체 개요 시트 1장과 슬롯별 확대 이미지(행마다 1장, 기준 그림 `REF` 셀을 왼쪽에 두고 셀 높이 최대 720px)를 한 번의 호출로 보낸다. Codex는 2048px를 넘는 이미지를 줄여 보내므로(v1의 448px 셀 시트는 503×2048, 셀 약 234px로 전송됨) 모든 이미지를 긴 변 2048px, 짧은 변 768px(고해상도 비전 입력 한도) 이하로 맞춘다. 셀 크기로 맞출 수 없는 극단 입력은 최종 합성 이미지를 줄여 저장하고 `sheet.size`/`downscaledToFit`에 기록한다. 이때 해상도가 떨어지며, 관찰이 `unknown`이면 review로 처리된다. 항목에 `colour_contamination`(같은 신체 부위가 기준 그림에 없는 색 얼룩·변색, 기준에 있는 색은 제외)을 더했다. 자동 기본 관찰 모델은 아래 '관찰 모델 선택'의 최신 Luna·medium이다. 수동 비교만 선택 params `frameObserver`(`vision`에서만, 고정 허용 목록 `gpt-6-luna-medium`/`gpt-6.1-sol-medium`, 문자열이 아니거나 목록 밖이면 `VIDEO_SETTING`, 직접 `process_clip`은 `VIDEO_INVALID_PARAMS`)로 요청별로 지정한다. 이 고정 목록은 명시한 비교 요청에만 쓰며 자동 기본값이 실패할 때의 대체 모델이 아니다. 생략한 요청은 기존 형태 그대로다. 이 값은 캐시 키·receipt·`frameSelection.observer`에 기록된다. 이전 설명: 관찰 이미지를(Codex ChatGPT 구독 경로, `--ignore-user-config`, `model_provider=openai`, `forced_login_method=chatgpt`, 구조화 JSON schema, 다른 모델 fallback·자동 재시도 없음). 실제 실행 모델은 세션 rollout에서 확인해 요청 모델과 다르면 실패로 처리한다. 결과는 `SPRITE_DATA_DIR/cache/frame-selection/observations/<key>.json`에 전송한 모든 이미지의 순서별 해시·기준 이미지 해시, 후보 ID 순서, 프롬프트·스키마 버전, 모델, effort를 키로 저장하며 판정만 바뀌면 재관찰하지 않는다. 실패한 관찰은 캐시하지 않는다.
- 관찰 모델 선택: `frameObserver`를 생략하면 worker가 요청마다 먼저 `codex` CLI가 PATH에 있는지 확인하고(조회만, 실행 없음) 로컬 Codex 모델 catalog(`$CODEX_HOME/models_cache.json`, 기본 `~/.codex`, 네트워크 없음)를 다시 읽는다. `gpt-<숫자 버전>-luna` 중 `visibility`가 정확히 `"list"`이고 `input_modalities`가 `image`를 포함한 배열이며 `supported_reasoning_levels`가 `{"effort": "medium"}` 객체를 포함한 배열인 행만 인정하고(문자열 `"image"`, `{image: true}` 같은 형식은 거절), 버전 숫자 순으로 가장 최신 하나 고른다. effort는 항상 medium이다. 관찰 id는 `<model>-medium`이므로 `gpt-6-luna`가 선택되면 기존 `gpt-6-luna-medium` 관찰 캐시 키가 그대로 맞고, 더 새 Luna가 선택되면 캐시가 분리된다. 버전은 ASCII 숫자 1~4자리 부분 최대 4개(`6`, `6.10`, `6.1.2.3`)만 인정하고, 너무 길거나 형식이 틀린 버전 행은 오류 없이 제외한다. 내부 관찰 경로(`select`·`observe`·`codex_observe`)도 같은 기준으로 확인한다. 고정 비교 목록 밖의 `gpt-<버전>-luna-medium`은 그 시점 catalog가 고른 최신 Luna와 같을 때만 받고, 다른 값은 관찰 모델 호출 전에 거절한다(공개 API·`process_clip`은 원래 고정 목록만 받는다). catalog가 없거나 읽을 수 없거나 조건에 맞는 Luna가 없으면 관찰 모델을 호출하지 않고(다른 모델 대체 없음) 코드 측정과 정책만 적용한다. 빈 프레임 후보는 `CODE_EMPTY_FRAME` reject, 나머지 후보는 `OBSERVATION_MISSING` review가 되고, 모든 슬롯은 균등 프레임을 유지하며 `observer.available=false`·`reason`(`CODEX_CLI_MISSING`/`LUNA_CATALOG_UNREADABLE`/`LUNA_NOT_IN_CATALOG`)·`observation.skipped`·`calls: 0`을 남긴다. 이때 `observationCacheOnly`는 `VIDEO_FRAME_OBSERVATION_CACHE_MISS`다. catalog는 Codex가 저장한 로컬 목록이며 이 앱이 갱신하지 않는다(갱신 시점은 catalog의 `fetched_at` 기준). 사전 확인 뒤 실행 시점에 CLI가 사라지거나 실행이 실패하면(경합) 기존처럼 `OBSERVATION_FAILED` review이고 재시도·다른 모델 대체는 없다.
- 판정: 코드 정책이 먼저 적용된다. 빈 프레임은 reject, 관찰 누락·필드 누락·`unknown`·가장자리 접촉과 "잘림 없음"의 충돌은 review. 나머지는 규칙(결함 관찰 → reject, 모두 정상 → keep)으로 판정한다.
- `observationCacheOnly: true`(vision 전용, 비교 재실행용): 관찰 모델을 호출하지 않는다. 같은 관찰 캐시가 없으면 판정 전에 `VIDEO_FRAME_OBSERVATION_CACHE_MISS`로 중단한다. 다른 값은 `VIDEO_SETTING`.
- 선택: 균등 프레임이 reject이거나 규칙도 review로 본 경우에만 같은 슬롯의 keep 이웃으로 바꾼다. keep 이웃이 없으면 균등 프레임을 유지하고 슬롯을 review로 표시한다. 선택 결과의 최대 간격이 균등 간격의 1.75배를 넘거나 루프 이음이 나빠지면 전체를 균등 경로로 되돌리고 이유를 기록한다.
- 기록: 작업 `processing.selection.frameSelection`에 후보 풀, 프레임별 측정·관찰·규칙 판정·이유 코드, 슬롯별 선택, 시퀀스 검사, 관찰 receipt(모델, 사용량, 시간, 캐시 hit), `observer`(id·model·effort·선택 근거), `judge: {requested, backend: "rules"}`를 남긴다. 새 프레임의 `selectionDecision`은 자동 추천이며 `review`·`reviewReason`·`hidden`·기존 clip을 바꾸지 않는다. 교체된 균등 프레임은 슬롯 없이 후보(`role: uniform-alternative`)로 함께 등록해 사용자가 되돌릴 수 있다.
- 과거 기록 호환: 2026-10-12~13에 저장된 기록의 `judge.backend: "laya-mlx"|"jev"`, `decision.source: "laya-mlx"|"jev"`, `laya`/`jev` 필드, `LAYA_*`/`JEV_*`/`CONFLICT_LAYA_VS_RULES`/`CONFLICT_JEV_VS_RULES` 이유 코드와 `.data/cache/frame-selection/jev/`는 지우거나 다시 쓰지 않으며 UI는 이 값을 계속 읽어 표시한다.
- `GET /v1/providers`의 `grok-video.capabilities.frameSelection`은 `{modes: ["uniform","vision"], judges: ["rules"], defaultMode: "vision", defaultJudge: "rules", observer}`이며 `observer`는 위 CLI 사전 확인과 catalog 선택 결과(`model`, `effort`, `available`, `reason`)다. 감지는 설치·다운로드·추론·네트워크 호출을 하지 않는다.

## M1 제출·회수·저장 복구 (2026-10-22)

- 한 job의 외부 생성 POST는 최대 1회다. 거절·전송 실패·응답 유실·유효한 ID가 없는 접수 불명 상태에서는 재전송하지 않는다. 새로운 생성은 사용자가 별도 요청으로 명시한다.
- ID가 있으면 같은 `/videos/{id}` GET만 사용한다. 429/5xx·연결/잘린 body·비JSON·read timeout은 연속 최대 4회(최대 3회 재시도, 1/2/4초 backoff) 조회하며 각 수동 재개의 네트워크 예산은 600초다. 각 HTTP timeout·socket 수신·대기는 남은 예산으로 제한하며 느리게 분할된 header/body도 예산을 연장하지 않는다. GET 401/403은 즉시 중단하며 로그인 복구 후 같은 ID로 수동 재개한다.
- 완료 URL 누락·다운로드 오류·MP4 검사 실패는 원본/완료 등록을 만들지 않는다. `/jobs/{jid}/retry`는 같은 ID로 조회·회수를 재개한다. 다운로드의 429/5xx·연결/잘린 body/read timeout은 최대 4회(1/2/4초 backoff) 시도하며 MP4 검사 실패는 수동 회수로 남긴다. 기존 동일 Grok credential을 붙이는 다운로드 재요청은 같은 잔여 예산을 공유하고 실제 HTTP마다 downloadCount를 증가시킨다. token/provider/authSource 자동 전환은 없다.
- 다운로드 바이트는 앱 MP4 검사와 SHA-256 확인을 거쳐 엔진의 독점 임시 `.part` 파일·fsync·원자 replace로 확정한다. 고정 `.part` symlink는 따라가지 않고 최종 출력/부모 symlink를 거절해 원본을 보존하며 게시 실패 시 새 임시 파일만 정리한다. 원자 게시 직후 중단도 로컬 파일부터 검사하므로 인증·조회·다운로드 없이 재사용한다.
- 완성 `result.json`이 있으면 별도 출력과 파일 해시를 재사용하여 저장만 재시도한다. DB 게시 후 프로젝트 폴더 flush 실패는 `interrupted`로 표시하고 outbox·동작·프레임·개별 시간을 보존한다. 이 경우 재시도는 같은 attemptId를 유지하고 폴더 동기화/상태 저장만 한다. 재시도 키는 기존 멱등성 계약을 따른다.
- 공개 `Job.recovery`는 선택 필드 `requestId`, `postCount`, `pollCount`, `downloadCount`, `stopReason`만 제공한다. 최종 `receipt`에도 안전한 시도 정보만 포함한다. provider 응답 원문·서명 URL·token·인증 경로는 포함하지 않는다. ID는 현재 credential token을 포함하지 않는 제한 ASCII 식별자를 신규 응답 수용 시 검증한 경우만 공개하고, 검증 표식 없는 과거 ID는 내부에 보존하되 공개 영수증에서 생략한다. 재사용 receipt의 임의 키·서명 URL은 필드 allowlist와 타입 검사로 제거하고, model은 요청 허용 목록 또는 unknown만 공개한다. 과거 checkpoint의 원래 receipt와 ID는 유지한다. `completedResult`/`published`가 있으면 JobCard는 완성 결과 저장 재시도로 표시한다.
- 출력 검증·job/export 등록과 삭제는 기존 SQLite writer transaction으로 직렬화한다. 존재 검사 뒤 실제 읽기 전에 삭제가 끼어드는 강제 실행 순서 회귀를 둔다. M0 최초 통합 실패 원인이 이 경합이었다고 확정하지 않는다.

검증 fixture는 localhost HTTP 서버와 ffmpeg 합성 MP4다. 실제 provider 장애·로그인·유료 생성 실측은 아니다. Postman CLI 1.69.0은 1.70+ simulation을 지원하지 않아 로컬 transport 회귀를 사용하며 CLI 전역 갱신·workspace 생성·외부 게시는 하지 않는다.

## M2 루프·보간 정책 (2026-10-22)

새 영상 작업은 `processingPolicy`에 `video-processing-v6-sprite-gen-2.45.3-m3`, 실제 엔진·앱 의존 소스 `engineDigest`, 색/알파·보간 정책을 고정합니다. 같은 identity는 extraction key와 `result.processing.policy`에도 저장합니다. VERSION/digest가 없거나 다른 작업은 API retry와 worker 실행에서 `VIDEO_RECIPE_INCOMPATIBLE`(409)로 거절합니다. 모르는 설정도 거절합니다. 보존 영상을 선택한 새 처리 요청은 허용합니다. 이미 완성된 결과의 저장만 재시도는 구 recipe도 허용하며 생성·다운로드·재처리를 실행하지 않습니다.

추가 설정은 `rifeTta: off|on`(기본 off, on은 `-x -z`)과 `overlapWrap: off|auto`(기본 off)입니다. 이전 저장 설정을 덮어쓰지 않습니다. overlap은 명시 보정이 켜져 있고 두 걸음이 관측된 구간에서만 검토하며 공유 시간·픽셀 예산을 넘기면 적용 성공으로 기록하지 않습니다. 기본 8장·선택 12장·4–64장 축소는 보간하지 않습니다. 명시 수동 구간은 그대로 유지합니다.

원본의 `stepCount`, `ghostScreen`, `leadIn`, 장비 픽셀 주기와 최종 `renderedSeam`의 측정 대상을 구분합니다. 숨은 발·비이족/기준 구조 불명은 두 걸음을 확정하지 않습니다. `repairMode=off`는 보정 픽셀을 만들지 않으며 `filmed-ghost`는 재촬영 권고만 남깁니다. ghost 원본 대체·flow·급가속 보정은 실제 입력 프레임과 비율을 기록합니다.

RIFE 캐시는 서버가 정한 프로젝트 폴더의 `.cache/rife-m2`입니다. 요청으로 경로를 받지 않습니다. RGBA·순서·비율·전처리 코드·binary/model 내용·TTA·host identity가 다르면 miss입니다. hit도 현재 손상/ghost/outline gate를 통과해야 채택하며 완성 셀과 계보는 캐시 밖의 출력/라이브러리에 저장합니다. 삭제·손상·쓰기 실패는 로컬 재계산 또는 캐시 없이 계속할 수 있고, symlink 이탈은 거절합니다. 같은 키의 게시에는 독점 임시 PNG와 원자 replace를 씁니다.

로컬 보간은 작업 전체 60초, 프레임당 2,000,000픽셀 예산입니다. 캐시 재사용·flow/overlap 검색·binary pass는 취소/잔여 예산을 확인합니다. 실행 불능·예산 중단은 원본을 보존하고 실패 이유를 남깁니다. TTA/overlap의 합성 실측을 실제 영상 품질 향상이나 다른 장치의 성능으로 해석하지 않습니다.
