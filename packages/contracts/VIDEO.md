# 영상 제작 계약

기존 이미지 제작과 편집 계약에 추가한다. 영상은 이미지 asset과 별도인 `snapshot.videos`에 기록한다. 기존 schemaVersion 1 프로젝트의 videos 생략은 빈 목록으로 취급한다.

## API

- `GET /v1/providers`: 기존 이미지 제공자와 `providerId: grok-video`, `mediaKind: video` capability를 반환한다. 로컬 Grok 로그인만 사용하며 API key fallback은 없다. 영상 기본 모델은 `grok-imagine-video-1.5`, 선택 모델은 동일 모델과 `grok-imagine-video-1.5-lite`. 길이 2~6초, 해상도 480p/720p.
- `POST /v1/projects/{id}/videos`: multipart `file`(MP4, 최대 64MiB), `expectedRevision`으로 기존 영상 등록. 반환 `{snapshot, video}`. 생성 호출 없음.
- `GET /v1/videos/{videoId}/content`: 원본 MP4. `Video`는 `{videoId, sha256, originalFilename, mediaType, width, height, fps, frameCount, durationMs, provenance, url}`.
- `POST /v1/projects/{id}/jobs`: 기존 envelope와 idempotencyKey를 유지. operation에 `generate_video`, `process_video` 추가.
- `POST /v1/projects/{id}/video-batches`: `{inputRevision, items:[{assetId, params}], idempotencyKey}`로 1~16개 영상 제작을 원자적으로 접수한다. 각 항목은 `generate_video`와 같은 검증을 받으며 하나라도 잘못되면 전체를 접수하지 않는다. 응답은 `{batchId, jobs}`. 같은 키·같은 내용의 재전송은 같은 작업들을 반환하며 다른 내용이면 409다. 항목별 `batchId`, `batchIndex`(0부터), `batchSize`를 작업에 표시한다. 모델 호출 수는 항목 수이며 실행 버튼에서 이 수를 명시한다. 방향별 기준 그림은 항목마다 사용자가 선택하고 별도 그림을 몰래 생성하지 않는다. 작업 처리기는 저장된 항목을 순차 실행하며 탭이 닫혀도 접수된 작업은 유지된다.
- `generate_video`: assetIds는 기준 그림 하나. params는 `state`(idle/walk/run/jump/attack), `direction`(side/front/back), `facing`(right/left), `motionPrompt`, `model`, `durationSeconds`(기본 3), `resolution`(기본480p), 선택 `referenceRevisionId`, 아래 후처리 설정. `referenceRevisionId`를 지정하면 승인된 참조여야 한다.
- `process_video`: assetIds는 빈 배열. params `videoId`는 프로젝트 소속 영상. 선택 `spillReferenceAssetId`는 같은 프로젝트의 원본 기준 이미지이며, 영상 안쪽에 섞인 배경색과 캐릭터 본래 색을 구분하는 데 사용한다. 생략하면 영상 생성 때 보존한 기준 이미지를 사용하고, 그것도 없으면 보수적인 작은 영역 보정만 적용한다. 명시한 기준이 없거나 다른 프로젝트 소속이면 접수 전에 거부한다. `generate_video`는 자체 생성 기준을 사용하므로 이 설정을 받지 않는다. 아래 후처리 설정 적용. 외부 생성 없이 원본을 다시 처리한다.
- 공통 후처리 params: `state` 기본 walk, `key` auto/green/magenta/cyan/white 중 지원 범위, `loopMode` auto/full/manual, 수동 구간 `startFrame`(0부터), `endFrame`(미포함), `maxFrames` 4~64이며 생략 시 walk는 **8**, 나머지는 32다. 명시한 값과 기존 저장 요청은 유지한다. `bodyHeight` 16~512 기본94, `cellWidth` 32~1024 기본64, `cellHeight` 32~1024 기본128. 선택 구간을 시간 순서로 샘플링하며 한 사이클 시간을 유지한다. 구간 불합격을 자동 재생성으로 바꾸지 않는다.
- 공통 `finishMode`: `gif`(기본) 또는 `rgba`. `gif`는 검수한 3배 GIF와 같은 색상·알파 결과를 PNG 후보에 저장한다. 공통 크기 PNG를 출력 셀에 배치하고 nearest 3배 → 검정에 알파 합성 → 프레임별 최대 255색 → 알파 128 이하 제거 → 원래 크기로 복원한다. 이진 알파 PNG 자체가 편집과 bake의 입력이므로 화면만 바꾸는 필터가 아니다. `rgba`는 반투명을 유지한다. 두 모드 모두 원래 크기의 추출·배경 제거 PNG 및 마무리 전 정규화 PNG를 보존한다. 기존 저장 프로젝트의 픽셀을 조회만으로 변경하지 않는다.

## 작업·저장

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
- 보간 프레임은 `interpolated: true`, 입력 프레임 번호·보간 비율·도구를 `interpolation`으로 기록한다. 원본 추출·배경 제거 프레임을 따로 보존하며 bake와 백업에서도 이 계보를 유지한다. 품질 지표는 진단이고 수동 검수를 대신하지 않는다.

게임용 출력에는 기존 atlas/runtime/PNG/Aseprite에 더해 동작별 strip PNG·grid PNG·GIF·lossless animated WebP를 별도 ZIP으로 제공한다. 모두 같은 bake의 실제 최종 셀을 사용하며 PNG 픽셀·순서·앵커·밀리초 시간은 runtime이 기준이다. GIF의 10ms 시간 단위 반올림 및 색상/알파 제약은 출력 메타데이터에 기록하고, GIF로 정확히 표현할 수 없는 짧은 프레임은 오류/누락 이유를 명시한다. WebP와 GIF의 반복/단발 여부를 원래 동작과 일치시킨다.

이번 구현 검증은 이미 생성한 실제 MP4를 재사용한다. 실제 원격 생성은 앞선 1회 실측과 주입형 transport 회귀 검사로 구분한다. 브라우저 검증은 허가된 기존 ego TaskSpace에서만 수행한다.

## 공개 v2.34 품질 보완 (2026-10-06)

- `between: auto/on/off`(기본 auto)는 주기 맞춤에서 중간 그림이 필요할 때 적용한다. auto는 최신 보간 품질 검사로 번짐·검은 경계가 감지된 중간 그림을 가까운 원본으로 대체한다. on은 RIFE 강제 사용, off는 가까운 원본 사용이다. `repairMode`와 별도 설정이며, 기본 8장 축소 샘플링에는 중간 그림을 생성하지 않는다.
- `startFoot: auto/left/right`(기본 auto)는 시작 발 분석/주기 정렬에 사용한다. `process_video`의 선택 `startIndex`는 새 출력의 시작을 0부터 지정하며 0~63 및 실제 출력 수 범위를 모두 검사한다. 프레임과 표시 시간을 함께 회전한다. 판정 근거가 부족하거나 신체 구조가 이족이 아니면 발 정체를 확정하지 않는다. 원본 동작/비교 기준 clip의 시작 위치는 변경하지 않는다.
- 생성 명세 `bodyPlan`, `equipment`는 선택 문자열이다. 예: `quadruped`, `the rider=biped; the horse=quadruped`, `sword:right; shield:left`. 장비 좌우는 캐릭터 자신의 좌우이며 빈 필드는 기존 프롬프트와 호환된다. 구문을 접수 전에 검사하며 영상 요청·묶음 snapshot에 포함한다. 명세 전달은 실제 모델 순응의 보장이 아니다.
- `process_video`에 `direction/facing/bodyPlan/equipment`를 명시하지 않으면 영상에 저장된 생성 설정을 재사용한다. 설정도 없으면 기존 기본값을 사용한다. UI의 원본 방향 선택은 명시적 override다.
- 업로드 검사·시간 탐색·디코딩은 같은 영상 stream을 사용한다. 표지 그림 stream과 오디오 길이는 제외한다. 영상 메타데이터의 `streamIndex`와 작업 `processing.source.timesMs`(마지막 종료 경계를 포함한 n+1개)를 기록한다. 평균 FPS로 제안한 구간은 UI에 추정값이라고 표시하고, 처리 후 실제 timestamp를 사용한다.
- `processing.version`은 `video-processing-v4-sprite-gen-2.34`. `selection`에 대응 포즈 크기 변화(`sizeHold`), 주기 혼입(`period`), 그림 갱신 빈도(`held`), 발 판정(`footStrike`), 수동 위상(`outputPhase`), 재검토 권고(`retake`)를 기록한다. 과거 결과의 필드 생략을 허용한다. 재검토 권고는 유료 생성 호출로 이어지지 않는다.
- 크기 보정은 원본 대신 파생 이미지에 적용하며 여백을 확보한 후 색/알파를 분리해 변환한다. 계보에는 padding을 포함한 원본→출력 변환과 실제 보간/원본 대체 여부를 기록한다. 원본 PNG의 `sourceTimeMs`는 반드시 실제 원본 timestamp다.
- WebP는 각 셀을 lossless/exact로 인코딩하고 애니메이션으로 묶는다. 투명 픽셀 RGB·가변 시간·반복 슬롯을 유지하며 기존 전체 RGBA 검사를 그대로 적용한다. 앱 WebP 출력에는 별도 `img2webp` 설치가 필요 없다.

실행 결과와 한계: [최신 공개 스킬 반영 기록](../../docs/product/LATEST_SKILL_UPGRADE_2026-10-06.md).
