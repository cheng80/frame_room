# 프레임룸 개선 백로그 — sprite-gen v2.34.0 선별 반영

> 2026-10-06 자료 정리: 아래 조사·실험의 원본, 비교 결과와 전용 스크립트는 사용자 요청으로 삭제했다. 제품 결정·구현 기록은 보존하며 과거 경로를 현재 실행 가능한 자료로 해석하지 않는다.

2026-10-06 KST. **우선순위는 기존 결과·과금·저장 계약 보호(P0), 영상 품질과 생성 명세 연결(P1), 선택 확장(P2) 순서다.** 공용 스킬 교체나 최신 CLI 전체 연결 대신 프로젝트 전용 엔진과 앱 adapter의 실제 호출 경로에 선별 반영한다.

이 문서는 실제 비교 결과를 반영해 작성했던 구현 계획이다. 이후 사용자 지시에 따라 제품 코드에 반영했으며, **현재 구현·검증 결과는 [v2.34 반영 기록](LATEST_SKILL_UPGRADE_2026-10-06.md)**을 따른다. 아래의 당시 수용 조건 전체를 통과했다는 뜻은 아니다.

| 현재 범위 | 상태 |
| --- | --- |
| P0 보존·단일 제출·계보·보간·WebP | 코드 반영 및 자동 회귀·보존 영상 검증 완료. 기존 GIF 마무리 유지 |
| P1-01~04 크기/주기/위상/stream | 앱 연결 완료. 실제 세 영상은 크기 보정 기준 미만이므로 보정 효과 자체는 합성 시험 범위 |
| P1-05 체형·장비 명세 | 기준 그림 설명/영상 요청/묶음에 연결. 실제 모델 순응은 신규 생성으로 검증하지 않음. marker QA도 동작 보완·검사에 연결 완료 |
| P1-06 부위별 색 복원 | 사용자 결정으로 제품 기능 범위에서 제외. 필요 시 GPT 개별 작업으로 처리 |
| P2-01 구도/알파/resampler | 단일 이미지 구도 가이드·원본 알파 판정·엔진 변환 반영. 기존 GIF/nearest 유지 |
| P2-02 부위 흔들림 | 영역 지정·전후 미리보기·새 검수 대기 동작 저장을 앱에 연결 완료. [후속 기록](CLIP_TOOLS_2026-10-06.md) |
| P2-03 외부 영상 도구 | 프롬프트 도우미는 엔진/CLI 반영. 유료 extend/edit 앱 연결은 별도 범위 |

**다른 캐릭터 재검토 완료:** 하늘 해적 추가 비교 (리서치 정리로 삭제). 기준 그림 재사용·Grok 3초 1회로 확인했다. WebP 수정 우선, 기존 GIF·원본 시간·기본 보간 OFF 유지. 최신 보호는 보간을 사용할 때 적용한다. 24→32 통제 시험에서 불량 13장 원본 대체와 같은 그림의 인접 쌍 4개가 함께 발생했으므로 자동 32장 변환을 기본값으로 가져오지 않는다.

**사용자 지정 출력 기준:** 게임용 걷기는 왼발·오른발을 포함한 한 사이클 **8장 기본**, 선택 12장으로 반영했다. 영상의 24/32장은 분석·보간 비교 자료이며 게임용 기본 출력 수가 아니다. 원본과 한 사이클 시간을 유지하면서 `maxFrames` 샘플링을 사용하고, 줄이는 작업에 RIFE를 자동 적용하지 않는다. 하늘 해적 동일 구간을 실제 앱 경로로 8장/12장 추출해 1,000ms와 선택 픽셀 일치·PNG/GIF/WebP 출력을 검증했다. 생성/재처리 UI·서버의 걷기 기본값을 함께 변경했고 기존 명시 요청은 유지한다. 시작/끝 중복 프레임을 추가하지 않고 접지·다리 교차·이음새를 검수한 뒤 채택한다.

## 근거와 검증 상태

| 근거 | 확인 범위와 한계 |
| --- | --- |
| 기존 코드 비교 (리서치 정리로 삭제) | 앱 연결 유무, 로컬 패치, 기존 채택 결과의 기준. 실제 영상 품질 우열을 증명하지 않음 |
| inventory (리서치 정리로 삭제) | 비교 당시 프레임룸 `e63ad6645f8bf93f915dabc1a130c1874e8e190c`, upstream v2.34.0 `1fc35090fa9c359bc96d1287fbc32f733acaa7e4`. 현재 HEAD 또는 향후 최신 버전이라는 뜻은 아님 |
| engine.diff (리서치 정리로 삭제) | 프레임룸 → v2.34.0 방향. 함수 차이의 근거이며 일괄 적용할 patch가 아님 |
| 기존 probes (리서치 정리로 삭제) | 합성 픽셀에서 RGBA 축소 해시 동일, cyan 지원 차이, 주입한 불량 보간 거절을 확인한 기록. 실제 RIFE 실행·Grok 품질 실측이 아님 |
| 이번 문서의 코드 확인 | `adapters/spritegen/`, `services/api/`, `services/worker/`, `apps/web/src/`, `alignment/`의 호출·저장·출처·출력 계약 정적 확인. 앱/브라우저 테스트 미실행 |

**실제 비교 결과보고서: SKILL_AB_RESULTS_2026-10-06.md (리서치 정리로 삭제).** 동일 입력의 처리·진단 실측을 기록했으며, 앱 통합 완료 또는 모든 영상의 시각적 품질 개선을 뜻하지 않는다.

### 전달받은 실제 실험 중간 결과

신규 Grok 생성은 **Pro, 3초, 480p로 1회 성공**했으며 이번 실험의 `max1` 제한을 지켰다. 아래 ‘기존’과 ‘신규’는 입력 영상 구분이며, 두 열 모두 최신 sprite-gen 처리 결과다. 프레임룸 대 최신 버전의 승패나 개선율로 해석하지 않는다.

| 측정 항목 | 기존 영상 | 신규 Grok 영상 | 백로그 반영 |
| --- | --- | --- | --- |
| 최신 auto 주기 선택 | 28프레임 주기, `start=26` | 24프레임 주기, `start=17` | 구간/길이 차이를 기록하고 원본 index·시간을 보존 |
| RIFE repair | 3장 | 2장 | 아래 cycle align의 `made` 수와 별개 단계로 기록 |
| 최신 align, 목표 32프레임 | `made=21`, `nearest=7` | `made=18`, `nearest=6` | P0-02에서 실제 보간/원본 대체 계보 구분. 두 수의 합을 총 32프레임으로 오인하지 않음 |
| retake 진단 | 없음 | `held-drawings`; source hold 2, 촬영 12 drawings/s, align32 시 9 drawings/s | P1-02의 진단 전달 사례. FPS와 drawings/s를 구분 |
| 시작 발 판정 | 이번 전달값 없음 | `unknown`, 수동 후보 제시 | P1-03의 불확실성·수동 선택 경로 필요 |

`held-drawings`는 **자동 재촬영 허용이 아니다.** 이번 실험은 추가 생성 없이 `max1`을 유지하며 원본 재처리와 검수로 이어간다. 보간 채택/거절 및 경고 발생은 실측됐지만 검은 번짐·다리 형태의 개선이나 실제 앱 UI 연결까지 검증된 것은 아니다.

**출력 통합 확정:** 실제 `render_occurrence()` → `write_animation_formats()` 경로에서 기존·신규 영상 모두 `rgba`/`repaired`의 WebP parity 실패가 재현됐다. 기본 `gif`는 성공하고 PNG/strip/GIF는 보존됐다. 출력 계약 문제로 **P0-05 확정**, 제품 코드 수정은 미완료다.

**픽셀 원인 확인:** 실제 앱 canonical PNG 네 사례 모두 보이는 RGB·alpha·프레임 시간 차이가 0이며 완전 투명 RGB만 달랐다. 두 venv는 Python 3.12.13/Pillow 12.3.0/NumPy 2.5.3/libwebp 1.6.0으로 동일하고 WebP가 설치돼 있다. 같은 PNG·시간을 `img2webp -lossless -exact`로 저장하면 네 사례 모두 엄격 RGBA·시간 검증을 통과했다. 설치 누락·화질 저하와 구별한다.

**셀 여백 관측:** 신규 `rgba` 셀의 source frame 28·39·40은 오른쪽 safe edge 2px 기준을 1px 초과했다. 실제 canvas clipping은 없었다. P1-01에서 안전 여백 위반과 실제 잘림을 분리해 다룬다.

최종 보고서 확정 시 다음 증거를 함께 확인한다.

- 동일 베이스의 원본/영상용 준비 이미지 SHA-256, 실제 Grok MP4 SHA-256, 모델·설정·요청 ID·영수증. 후처리 비교는 양쪽에 같은 MP4 바이트를 사용했는지 확인한다. 별도 생성 결과라면 모델 변동이 섞인 비교로 명시한다.
- 두 실행의 엔진 revision·recipe·키색·선택 구간·RIFE 모드·셀/체고·프레임 수·시간. 기본값이 다르면 차이를 기록하고 품질 효과와 구분한다.
- MP4 → raw → keyed → 정합/보간 → 정규화 RGBA → GIF 마무리 → 최종 PNG/GIF를 구분한 산출물. 마무리 전 RGBA와 최종 GIF를 모두 비교한다.
- 원본 해시 불변, 유료 제출 횟수, 보간 거절/반복 프레임 수, 이음새·체고 추세·잘림·장비 위치·수동 검수 결과. 합성 fixture와 실제 생성 원본의 출처를 섞지 않는다.
- 기존 채택 GIF, 28프레임 PNG, 64×128 셀, 총 1,167ms는 기존 비교 문서가 제시한 회귀 기준이다. 이번 실험의 결과값으로 재사용하지 말고 해당 원본과 해시를 확보해 대조한다.

## 실제 연결 지점과 공통 보존 계약

현재 경로는 `VideoStep.tsx` / `VideoBasePreset.tsx` / `VideoBatchPlan.tsx` → `videoWorkflow.ts` → `POST /v1/projects/{pid}/jobs` 또는 `/video-batches` → `services/api/main.py:enqueue()` → `services/worker/video_task.py:execute_video()` → adapter 처리 → 새 후보/동작의 검수 대기 → `alignment/pipeline.py:build_bundle()`이다.

앱은 upstream `run_loop()`·`align_set()` 전체를 실행하지 않는다. `video_processing.py:_select()`, `_gait_fallback()`, `_repair_selection()`, `_align_selected_cycle()`에 새 정책을 명시적으로 연결해야 한다. `video_provider.py:validate_params()`의 allowlist는 현재 새 옵션을 거절하므로 UI 필드만 추가해서는 동작하지 않는다.

| 보존 계약 | 실제 소유 코드 | 모든 관련 항목의 완료 조건 |
| --- | --- | --- |
| 채택 GIF와 편집 PNG의 색/알파 | `video_finish.py:finish_frames()`, `video_normalization.py:normalize_frames()`, `video_task.py:execute_video()`, `videoWorkflow.ts:videoClipColorLabel()/videoBeforeFinishSnapshot()` | 기존 `finishMode=gif`의 legacy 축소·최대 255색·binary alpha 및 최종 미리보기 경로 유지. RGBA 경로와 별도 비교. 기존 승인 동작을 덮어쓰지 않음 |
| cyan·정합 캔버스 로컬 패치 | `engine/sprite-gen/sprite_gen/frames/cutout.py`, `frames/extract.py:conform_registered_row()` | cyan 선택/추출 유지, 정합 후 row cap 유지. 후자는 엔진 CLI 패치이며 앱 raw-crop에 이미 적용됐다고 주장하지 않음 |
| 유료 요청 1회 | `video_provider.py:generate()/checkpoint_state()`, `main.py:enqueue()/retry()`, `video_task.py:execute_video()` | 한 승인 생성 작업당 POST 최대 1회. 재처리 POST 0회. 접수 ID 이후 조회/다운로드 재개, 접수 여부 불명확하면 자동 재전송 금지. 여러 승인 작업이 있는 batch 전체를 1회로 해석하지 않음 |
| 원본과 계보 | `services/api/videos.py:register()/attach_dependencies()`, worker의 raw/keyed/normalized/finished 자산 등록, `assetProvenance.ts:assetProvenanceLabel()` | 받은 MP4·준비 이미지·영수증 선보존, raw 불변. 실제 선택한 원본 index/시각/부모·보간 여부가 출력 픽셀과 일치. 새 결과는 새 자산/버전 |
| 폴더·SQLite·복구 | `project_folders.py:_sync()/flush()/open_project()/detach_project()/cleanup_missing()`, `store.py` | `project.json`/`project.sqlite3`와 리소스·전체 이력·outbox 보존. 폴더 이동/재등록·백업 복원 후 새 메타데이터와 원본을 조회 가능. 폴더 열기로 생성 자동 재개 금지 |
| 사용자 편집·출력 | `useStudio.ts`, `services/api/edits.py`, `pipeline.py:render_occurrence()/_clip_gates()/build_bundle()`, `verify_artifacts.py:verify_artifacts()` | occurrence별 시간/픽셀 편집, revision 충돌, nearest bake, 앵커·수동 승인 gate 유지. PNG/atlas/타임라인을 동일 bake 기준으로 검증 |

## P0 — 이식 전 보호 조건과 출처 정확성

### P0-01. 기존 결과를 재현할 recipe와 회귀 기준 고정

- **현재 근거:** GIF 경로는 `resize_mode='legacy'`, RGBA 경로는 `color-alpha`로 분기한다. 기존 RGBA `loop.resize_cell()`과 upstream `util.resample.resize_cell()`은 AST가 같고 합성 축소 해시도 같다. 전체 업그레이드를 새로운 축소 개선으로 설명할 근거가 없다.
- **대상/실행:** `video_processing.py:VERSION/process_clip()`, `video_normalization.py:normalize_frames()`, `video_finish.py:finish_frames()`, `pipeline.py:_engine_fingerprint()/build_bundle()`에서 변경된 처리 정책을 recipe/cache 식별자에 포함하도록 설계한다. 기존 채택 결과의 원본·출력·시간·앵커·편집 snapshot과 해시를 회귀 입력으로 고정한다. 오래된 작업의 재개에 새 recipe가 조용히 섞이지 않게 구분한다.
- **앱/API/UI:** `/jobs`의 `process_video`가 새 후보를 만들고 `Job.result.processing`에 recipe를 남긴다. `VideoStep.tsx`의 결과 비교는 저장된 `finish` 기록과 기존 `videoBeforeFinishSnapshot()`을 사용한다. 원본/채택 결과/새 결과를 별도 선택 가능하게 한다.
- **비용/보존:** 기존 MP4 로컬 재처리만 사용. GIF 기본값, nearest 편집, 기존 후보/승인 상태를 보존한다.
- **후속 시각 검수:** 사용자가 최신 RGBA의 흐릿함을 지적했다. 현재 기본은 반투명 픽셀 0개, 현재/최신 RGBA는 약 550~585개/프레임이며 두 RGBA의 전경은 98% 이상 일치했다. 기본 마무리를 RGBA로 일괄 변경하지 않는다. RIFE 불량 거절과 출력 선명도는 별도 선택·검증 대상으로 둔다.
- **다른 캐릭터:** 하늘 해적에서도 현재/최신 RGBA 반투명은 약 793개, 현재 기본은 0개다. 최신 점 제거가 crop을 2 source px 이동시키므로 픽셀 비교에는 같은 bounds를 사용하는 통제 결과를 별도로 둔다. 동일 bounds의 RGBA 전경 일치는 98.30%. 전체 crop/점 제거 이식으로 기존 팔레트·샘플 위치가 조용히 달라지지 않게 한다.
- **수용:** 기존 recipe로 채택 PNG RGBA·셀·occurrence 시간·앵커가 동일하게 재현되고 `verify_artifacts()`를 통과한다. GIF 인코더의 프레임 병합/시간 양자화는 기존 계약에 따라 비교한다. 새 recipe는 캐시가 분리되고 새 후보만 `pending`이다. `test_video_finish.py`, `test_video_normalization.py`, `test_animation_artifact_verifier.py`, `test_review_invalidation.py`에 관련 회귀를 연결한다.

### P0-02. 보간 거절 정책과 실제 부모 계보를 하나의 변경으로 연결

- **현재 근거:** upstream `video/rife.py:bleed()/between()/smear()`와 `video/align.py:resample()`은 `made_at`/`nearest_at`을 구분한다. 앱 `_align_selected_cycle()`은 현재 `fraction != 0`이면 보간으로 기록한다. 최신 `resample()`만 교체하면 원본 대체 픽셀을 보간 결과로 잘못 표기할 수 있다.
- **대상/실행:** 위 엔진 함수와 `video_processing.py:_align_selected_cycle()/_describe_source_processing()`를 함께 수정한다. auto 거절 시 `(i + (fraction >= 0.5)) % length`에 해당하는 실제 원본의 raw/keyed 경로·index·시각·부모를 선택한다. 회전 전후 `made_at`/`nearest_at`/`smear.at`의 index 공간을 명시한다. 이미 jump repair된 입력을 택했으면 그 계보도 유지한다.
- **앱/API/UI:** `video_provider.py:validate_params()`, `videoWorkflow.ts:videoProcessingParams()`, `types.ts`, worker 자산/프레임 기록, `assetProvenance.ts`, `VideoStep.tsx`를 연결한다. 보간 채택/원본 대체 수와 사유를 표시한다. 옵션명은 설계 단계에서 확정하되 jump `repairMode`와 cycle `between` 정책은 서로 구분한다.
- **비용/보존:** 추가 생성 없이 로컬 RIFE 처리. RIFE 설치/실행 실패를 외부 생성으로 대체하지 않는다. `repair.py`는 양쪽 동일하며 `repair_jumps()`까지 자동으로 smear 정책이 적용된다고 주장하지 않는다.
- **추가 실측과 기본값:** 하늘 해적 동일 24→32에서 현재 24장 채택/0대체, 최신 11장 채택/13대체, 출력 자체 진단 경고 12→0, 완전 동일한 인접 쌍 0→4였다. 보간을 쓸 때 보호를 적용하되 기존 OFF 기본과 원본 1,000ms를 유지한다. 최신 CLI의 32장/1,333ms를 그대로 적용하지 않는다. UI에서 원래 24장 결과와 비교할 수 있게 하고 대체가 많다는 이유로 유료 재생성을 자동 실행하지 않는다.
- **수용:** exact sample, 정상 보간, 불량 거절, 0.5 경계, 주기 wrap, 위상 회전, 기존 jump repair 입력별 픽셀과 index/시각/`interpolated`/부모가 일치한다. 거절 결과는 반복 원본임을 UI에 표시한다. `test_video_processing.py`, `test_video_jobs.py`, upstream `test_rife.py`·`test_cycle_align.py`를 함께 검증한다. 이번 실측의 기존 `made=21/nearest=7`, 신규 `made=18/nearest=6`을 최종 보고서와 대조해 실제 입력 회귀 사례로 추가한다. 동일 28→32장 RIFE 입력에서는 현재 28장 전부 채택, 최신 20장 채택/8장 원본 대체를 확인했다. 같은 진단기로 출력 경고가 10→0이지만 독립 시각 평가나 모든 다리 형태 개선의 증명은 아니다.

### P0-03. 재시도·새 진단을 유료 재생성과 분리

- **현재 근거:** `generate()`의 `postCount`, `requestId`, `submitting` checkpoint가 중복 제출을 막고 worker는 처리 전에 MP4를 등록한다. upstream `retake()` 안내나 batch의 mid-step 생성을 그대로 상위 흐름에 연결하면 이 계약을 우회할 수 있다.
- **대상/실행:** `video_provider.py:generate()/checkpoint_state()`, `video_task.py:execute_video()`, `main.py:enqueue()/retry()/video_batches_create()`의 단일 제출 경계를 모든 새 처리/경고 경로에 유지한다. `held-drawings`/주기 의심은 로컬 검수 상태로 전달하고 새 유료 job을 만들지 않는다.
- **앱/API/UI:** `videoWorkflow.ts:videoRetryLabel()`, `VideoStep.tsx`, `VideoBatchPlan.tsx`에서 기존 조회 재개·원본 재처리·명시적 새 생성 동작을 구별한다. 추가 기준 이미지 생성이 필요한 기능은 별도 요청 건수와 비용 경로를 실행 전에 드러낸다.
- **비용/보존:** API 키 fallback, 인증/429 시 자동 재생성 금지. 준비 이미지·영수증·request hash·MP4를 재사용한다. 현재 저장된 계보를 새 provider 성공 기록으로 꾸미지 않는다.
- **수용:** 모의 transport로 제출 직후 응답 유실, 다운로드 후 중단, 추출 실패, 취소/재시도, 경고 발생, batch 일부 실패를 주입한다. 생성 job별 POST ≤1, `process_video` POST=0, 접수 불명확 재시도 POST=0을 확인한다. `test_video_jobs.py`, `test_video_batches.py`, `test_worker_recovery.py` 회귀와 원본 해시 보존을 확인한다.

### P0-04. 키 제거 묶음 이식 시 로컬 패치와 저장 왕복 보호

- **현재 근거:** upstream `cutout`은 cyan을 거절하고 `conform_registered_row()`가 없다. `decide_spill()`은 동일하지만 `edge_band`의 위치가 `video/frames.py`에서 `frames/decontam.py`로 이동했다. 이번 두 영상의 keyed 총 146장은 RGBA 동일했다. 모든 키색·입력의 동등성까지 검증한 것은 아니다.
- **대상/실행:** `frames/cutout.py`, `frames/extract.py`, `frames/decontam.py`, `video/frames.py`는 의존 관계 단위로 선별 병합한다. cyan과 row cap을 명시적 로컬 patch로 남기고 `video_processing.py:_spill_decision()/_run_extraction()/process_clip()`의 캐시 버전과 기준 이미지 해시를 함께 점검한다.
- **앱/API/UI:** `validate_params()`와 `videoWorkflow.ts`의 cyan 선택을 유지한다. 추출 결과·spill 기준·새 진단은 worker 계보로 전달하고 `videos.attach_dependencies()`를 통해 복구 대상에 포함한다. `project_folders.py` 저장 구조를 upstream run 폴더로 대체하지 않는다.
- **비용/보존:** 외부 호출 없이 복사한 입력으로 검증. raw·원본 MP4·기존 SQLite와 outbox는 변경 실험 대상으로 사용하지 않는다.
- **수용:** `test_cutout_cyan.py`, `test_registered_row_cap.py`, `test_backport_edges.py`, `test_video_processing.py`의 spill/cyan 및 기준 내용 변경 캐시 검증을 통과한다. 새 결과를 가진 격리 프로젝트로 폴더 이동→재등록→이력 복원→백업 복원 후 원본/자산 해시와 계보를 확인한다. 저장 실패 시 outbox와 이전 portable revision 유지, 목록 제거 시 실제 폴더 유지까지 `test_project_folders.py`·`test_project_folder_cleanup.py`·`test_video_jobs.py`로 검증한다.

### P0-05. 실제 앱 RGBA/repaired의 WebP 픽셀 계약 실패 수정 — 확정

- **관측/상태:** 기존·신규 영상 `rgba`/`repaired` 네 사례에서 실패, 기본 `gif` 성공. 실패는 완전 투명 RGB 차이뿐이며 보이는 RGB·alpha·시간은 동일하다. Pillow 애니메이션 `_save_all()`은 `exact`를 전달하지 않는다. `img2webp -exact`로 동일 입력의 엄격 검증 통과를 확인했다. PNG 품질 비교에는 이 실패를 점수로 넣지 않는다.
- **대상/실행:** `alignment/animation_exports.py:_webp()/_verify_animation()`의 인코딩을 실제 exact RGBA를 보존하는 경로로 바꾼다. 설치된 `img2webp -lossless -exact`의 가변 시간·반복 슬롯 경로를 우선 검토하고, 바이너리가 없는 환경의 지원 범위와 명시적 실패를 설계한다. 현재 검사를 느슨하게 해 통과시키지 않는다. `services/worker/video_task.py`의 final-preview 및 `pipeline.py:build_bundle()`까지 연결 검증한다.
- **앱/API/UI:** `process_video` job의 final-preview와 `/v1/projects/{pid}/exports` 결과를 각각 확인하고 오류 전달·결과 표시를 수정 범위에 포함한다. UI의 출력 성공 표시는 실제 파일/검증 결과와 일치해야 한다. 기본 `gif` 성공을 RGBA 출력 성공으로 표시하지 않는다.
- **비용/보존:** 신규 생성 없이 저장된 strip/MP4 복사본으로 확인한다. raw·채택 GIF·PNG/atlas 원본 해시는 유지한다. 검증을 통과시키려고 모든 RGBA 차이를 무시하거나 원본 투명 RGB를 덮어쓰지 않는다. 정규화가 필요하면 파생 출력 경계와 recipe에 명시한다.
- **수용:** 신규 upstream strip 24슬롯과 실제 앱 최종 셀을 별도 입력으로 두고 프레임/시간/loop, alpha, alpha>0인 RGB, alpha=0인 RGB 차이를 각각 집계한다. 기존·신규 영상의 `rgba`/`repaired` WebP가 exporter 내부 검사와 독립 artifact 검증기의 동일한 canonical 픽셀 계약을 통과해야 한다. 기본 `gif` 성공과 PNG/strip/GIF 보존을 유지하고 alpha·반투명·visible RGB·시간 변화는 계속 검출한다. `test_animation_exports.py`·`test_animation_artifact_verifier.py`에 실제 차이 유형의 회귀를 연결한다. 직접 exporter/실제 렌더/미리보기/최종 export의 검증 범위를 분리하고 최종 수치·원인·수정 후 결과를 기록한 뒤 종료한다.

## P1 — 영상 품질과 생성 명세의 앱 연결

### P1-01. 대응 포즈 기반 scale drift와 여백 보존

- **근거/대상:** 현재 `_gait_fallback()`은 첫 탐색 실패 후 선형 추세를 보정한다. upstream `video/gait_fallback.py:cycle_drift()/undo_padding()/undo_scale()`와 `video/loop.py`의 호출 순서를 참고해 `video_processing.py:_select()/_gait_fallback()/_describe_source_processing()`에 첫 탐색 전 진단을 연결한다. 1% 기준은 포즈마다 높이를 강제하는 기능이 아니다.
- **앱/API/UI:** worker의 `sourceRect`/`sourceToFrameTransform`/앵커와 `video_normalization.py:normalize_frames()`에 padding·scale·translation을 합성한다. `Job.result.processing`과 `VideoStep.tsx`에 원본/보정 비교 및 적용 사유를 표시한다. 옵션 노출 시 validator와 request snapshot까지 전달한다.
- **비용/보존:** 로컬 전용, P0-01/02/04 이후. 비보간 affine과 보간의 non-affine 계보를 구분하고 사용자 앵커·기존 동작은 보존한다.
- **실측 연결:** 신규 `rgba` source frame 28·39·40의 오른쪽 safe edge 2px 기준 1px 초과를 회귀 사례로 추가한다. 실제 canvas clipping은 없었으므로 잘린 픽셀 복구 사례로 설명하지 않는다. 앵커·셀 경계·요구 여백을 함께 비교하고 기존 채택 결과의 위치를 자동 변경하지 않는다.
- **수용:** 실제 일정 크기 반복, 줌 변화, 웅크림/점프, 무기 경계 입력에서 자연스러운 자세 변화가 평탄화되지 않는지 검수한다. padding 후 경계 잘림과 좌표/앵커 오차를 확인하고 legacy recipe는 재현한다. 기존 `test_first_successful_loop_never_runs_gait_fallback`의 전제를 새 opt-in/recipe 정책에 맞게 분리한다. 실제 개선은 미검증이다.

### P1-02. 주기 혼입·그림 갱신 빈도를 검수 가능한 진단으로 전달

- **근거/대상:** upstream `video/period.py:screen()`, `video/held.py:measure()/measure_cycle()`, `video/align.py:retake()/CycleSuspects`는 앱의 직접 `resample()` 경로에 자동 적용되지 않는다. `_select()`와 `_align_selected_cycle()`에서 검사하고 `VideoProcessingError` 또는 결과 진단으로 변환한다. CLI `SystemExit`를 worker까지 그대로 전파하지 않는다.
- **앱/API/UI:** `/jobs` 요청에 명시적 주기 수/수동 구간 보완을 연결하고 `validate_params()`·`videoWorkflow.ts`·worker·`types.ts`에 사유/후보/측정값을 전달한다. `VideoStep.tsx`에서 의심 구간 비교, 수정 후 로컬 재처리, 검수 보류를 제공한다. 경고와 처리 불가능 오류를 구별한다.
- **비용/보존:** P0-03 적용. `retake`는 자동 유료 재촬영 명령이 아니다. 이번 신규 영상에서 실제 `held-drawings`가 발생했어도 실험 `max1`을 유지한다. 원본과 실패 시 추출물을 남기고 수동 구간으로 복구한다.
- **수용:** 1/2/3주기 fixture, 대칭 걷기의 오탐, 정지 hold와 빠른 동작을 포함한다. `held-drawings`의 13 drawings/s 미만과 생성하지 못한 중간 프레임 조건을 함께 검증하고 FPS와 그림 갱신 빈도를 다르게 표시한다. upstream에만 있는 `test_cycle_suspects.py`·`test_held_drawings.py`를 선별 이식하고 앱 통합을 확인한다. 자동 걸음 수 확정이나 모든 보간 문제 해결로 설명하지 않는다.

### P1-03. 방향별 시작 발·위상과 수동 지정

- **근거/대상:** 앱은 `align.foot_strike_start(aligned)`만 호출한다. upstream `foot_strike(..., view, foot, given)`의 후보/사유/불확실성을 `_align_selected_cycle()`에 전달한다. `process_clip()` options에는 현재 `facing`만 있으므로 `direction`의 내부 전달도 추가한다.
- **앱/API/UI:** `videoWorkflow.ts`와 API validator에 시작 발/수동 시작 index를 연결하고 기준 clip revision을 snapshot으로 고정한다. `VideoStep.tsx`에서 후보 프레임을 보고 새 동작의 시작을 지정한다. 이번 신규 영상의 `unknown`과 수동 후보 제시를 실제 사례로 연결하며 자동 판정 성공으로 표시하지 않는다. 기존 기준 동작과 사용자 타임라인의 자동 회전은 하지 않는다.
- **비용/보존:** 로컬 회전만 수행. P0-02의 출력 index/계보 변환을 재사용한다. 세트 전체 재위상은 별도 사용자 작업으로 분리한다.
- **수용:** 정면/후면/측면/대각선 및 좌우 facing, 명암이 비슷한 발, 비대칭/사족을 확인한다. 확신 부족 시 수동 선택을 요구하고 총시간·occurrence 편집·기준 clip이 불변인지 확인한다. upstream에만 있는 `test_cycle_align_foot.py`·`test_cycle_align_foot_margin.py`를 선별 이식하고 앱 회귀를 연결한다. 반 주기 뒤의 다른 발 가정은 사족 정확성의 근거가 아니다.

### P1-04. validation·decode·timestamp의 영상 stream 선택 통일

- **근거/대상:** `services/api/videos.py:validate()`와 `video_processing.py:_timing()`은 `v:0`, `_run_extraction()`은 CFR/VFR에 따라 다른 decode 경로를 사용한다. upstream `video/frames.py:probe()/extract(stream_index=...)`의 cover 제외 선택을 이 경로 전체에 공유한다.
- **앱/API/UI:** 업로드 `/videos`부터 `process_video`까지 선택한 stream index·크기·시간 기준을 일관되게 저장한다. `videoWorkflow.ts:videoRangeBoundary()`의 평균 FPS 기반 제안이 VFR의 정확한 경계인 것처럼 표시되지 않게 하고 실제 timestamp 기반 구간 선택을 연결한다.
- **비용/보존:** 로컬 probe/decode만 사용하고 MP4를 재인코딩·덮어쓰지 않는다. 기존 파일 크기/시간/프레임 한도와 원본 해시 검증을 유지한다.
- **수용:** cover+실영상+오디오, 오디오가 더 긴 MP4, CFR/VFR 및 15초 경계에서 raw 수·timestamp 수·선택 stream이 일치한다. exclusive endFrame과 마지막 duration이 정확하고 기존 VFR passthrough 회귀가 유지된다. stream 변경은 extraction cache 식별자에도 반영한다.

### P1-05. 장비 좌우·체형·프롬프트를 하나의 생성 명세로 전달

- **근거/대상:** upstream `gen/handedness.py:placement()/text()`, `gen/prompt_parts.py:Prompt.add()/note()`, `video/body_plan.py:parse_all()`, `qa/handed.py:check()/board()`를 선별한다. 앱 `VideoBasePreset.tsx`, `video_processing.py:prepare_still()/build_motion_prompt()`, 이미지 adapter `provider.py`와 기준 revision에 캐릭터 자신의 좌우·시점·체형을 일관되게 전달한다.
- **앱/API/UI:** `VideoBatchPlan.tsx`/`videoWorkflow.ts` → API validator/request snapshot → worker/provider의 경로를 완성한다. 기준 그림과 영상에 동일 명세를 사용하고 추가 prompt와 충돌하면 생성 전에 문구를 보여준다. 장비 QA는 marker/region 설정과 검수판으로 연결한다. 새 필드는 기존 프로젝트에 선택적으로 추가한다.
- **비용/보존:** 기존 원본을 미러링하거나 승인 기준을 교체하지 않는다. mid-step 기준 재생성은 별도 명시적 이미지 요청으로 분리한다. 엔진에 provider가 있다는 이유로 현재 비활성 이미지 provider를 켜지 않는다.
- **수용:** 앞/뒤/측면 좌우 해석, batch snapshot의 불변성, 빈 필드의 기존 prompt 호환성을 먼저 fixture로 확인한다. 모델 순응은 별도 실제 생성 검증으로 남긴다. 색 marker QA를 모든 장비의 의미 인식으로, prompt 조립기를 한국어 충돌 자동 수정으로 소개하지 않는다. 폴더 왕복 후 명세/참조 연결을 확인한다.

### P1-06. 부위별 기준색 유지와 시간축 색상 검수

**취소된 제품 기능 제안이다.** 사용자는 항상 발생하지 않는 색 문제를 GPT 개별 작업으로 처리하기로 결정했다. 아래는 원인과 당시 제안을 보존한 기록이며 다음 구현 목록으로 사용하지 않는다.

- **실측 근거:** 기존 장갑 원본 41번 `(360,295)` RGB `(193,173,87)`, 새 장갑 17번 `(374,278)` RGB `(94,82,15)`는 raw/keyed 동일하다. 기준 그림의 갈색 장갑이 원본 영상에서 노랑/올리브로 달라졌고 최신 RGBA에도 남았다. 새 화면 왼쪽 소매 내부 682픽셀은 raw/keyed 불변이며 기준 그림부터 크림색이다. 모든 누런색을 키색 번짐으로 취급하면 정상 소매·피부를 손상한다.
- **대상/연결:** 기존 raw/keyed/normalized/finished 계보를 이용해 같은 원본 index의 부위 확대·기준색 비교를 제공한다. `video_finish.py`의 GIF 마무리는 그대로 보존한다. 별도 색상 유지 단계는 사용자가 지정한 장갑·무기 영역과 기준 팔레트로 제한하는 방식을 먼저 로컬 실험하며, 보정 전후를 새 파생 자산과 recipe로 기록한다. 단순 전역 노랑/초록 제거를 적용하지 않는다.
- **검수/UI:** 생성 원본에서 바뀐 색과 후처리에서 바뀐 색을 구별해 보여준다. 프레임별로 다른 팔레트가 선택돼 색이 깜빡이는지 전체 주기를 확인하고, 프롬프트의 갈색 장갑 지정만으로 성공 처리하지 않는다. 의미 기반 영역 추적·재질 복원은 현재 구현된 기능이 아니다.
- **비용/보존:** 현재 저장된 두 MP4로 먼저 검증하며 추가 유료 생성은 하지 않는다. 보정은 선택적이고 되돌릴 수 있어야 하며 소매·피부·금속·알파·윤곽·수동 픽셀 편집을 보존한다.
- **수용:** 동일 부위의 raw/keyed/normalized/finished 비교와 전체 주기 재생으로 변색 및 깜빡임이 줄었음을 확인한다. 지정 영역 밖 RGB/alpha 불변, 자연스러운 명암 유지, 경계 누출·프레임 간 영역 추적 실패·정상 노랑/초록 재질 훼손 여부를 검증한다. 기존 GIF의 부분적 완화와 새 장갑의 남은 변색을 둘 다 회귀 사례로 둔다. 이번 원인 진단은 완료했지만 보정 구현·효과 검증은 미완료다.

## P2 — 품질 경로 안정화 후 선택 확장

### P2-01. 이미지 layout guide·실제 alpha 판정·공용 resampler 적용 범위

- **대상/연결:** upstream `gen/__init__.py`의 layout guide와 `gen/chroma.py:classify_raw_alpha()`, `util/resample.py:resize_cell()/transform_cell()`를 검토한다. 앱 이미지는 `adapters/spritegen/provider.py`의 경로를 쓰므로 엔진 생성 함수 복사만으로 반영되지 않는다. `VideoBasePreset.tsx`/`SourceSteps.tsx` → 이미지 job/API → `services/worker/task.py` → provider → raw/derived 등록에 연결한다.
- **보존/비용:** 원본 반환 alpha를 검사한 뒤 파생 이미지의 키 제거 여부를 결정한다. 참조 순서와 identity/style/pose/guide 역할을 기록한다. 현재 영상 RGBA 축소와 nearest 편집은 유지하고 이미지 추출 등 아직 적용되지 않은 경로만 별도 recipe로 확장한다. guide 작성·alpha 검사는 로컬, 실제 생성 호출은 명시된 이미지 작업만 수행한다.
- **수용:** 참조 유무·불투명/부분 alpha·키 배경 출력에서 원본 해시가 같고 guide가 사용자 원본으로 표시되지 않는다. 적용 전후 픽셀 회귀와 guide 요청 snapshot을 확인한다. 기존 영상 축소를 신규 개선으로 중복 집계하지 않는다.

### P2-02. follow-through를 원본 복구와 구별된 파생 편집으로 제공

- **대상/연결:** upstream `video/follow.py:follow_offsets()/follow_loop()`를 별도 로컬 처리로 감싼다. `EditSteps.tsx` 또는 영상 결과 편집 UI의 타원 영역/강도/미리보기 → 검증 가능한 API params → worker → 새 파생 자산/clip으로 연결한다. 저장 형태는 구현 전 확정하고 기존 occurrence pixel edit와 중복 적용되지 않게 한다.
- **보존/비용:** 추가 생성 없이 처리하되 새로운 픽셀 변형임을 계보에 기록한다. 원본·기존 채택·수동 승인 상태는 그대로 보존한다.
- **수용:** 영역 밖 픽셀, 가장자리 잘림, wrap 이음새, 취소/되돌리기, 폴더 복구 후 동일 재현을 확인한다. 움직임 복구 또는 AI 재생성으로 표시하지 않는다.

### P2-03. 외부 영상 도구·끝 프레임·extend/edit는 별도 제품 범위로 설계

- **대상/연결:** upstream `video/clip_prompt.py:plan_prompt()`는 외부 도구용 안내이며 MCP 실행기가 아니다. `gen/video.py`의 `VideoRequest` 및 extend/edit는 양쪽에 이미 있는 기능이다. 먼저 기존 `/videos` 가져오기와 `VideoStep.tsx` 재처리로 수용하고, 직접 실행이 필요할 때 provider capability → 별도 API 검증 → `video_provider.py`의 단일 제출 wrapper → worker 계보로 연결한다.
- **보존/비용:** first/last/reference 자산별 ID·해시·역할, 입력 영상과 출력 영상의 관계를 기록한다. API 허용 범위·모델·길이를 UI만 늘려 우회하지 않는다. 외부 입력은 영수증이 없으면 가져온 원본으로 표시한다. extend/edit와 추가 기준 이미지는 별도 유료 요청 단위로 표시한다.
- **수용:** capability에 맞지 않는 요청은 접수 전에 거절, 재개 시 추가 POST 없음, 입력/출력 원본 독립 보존, 가져오기만으로 provider 호출 없음. 실제 외부 연동은 별도 승인된 검증 범위로 남긴다. 팔레트/레이어/씬/호흡의 UI 노출은 이번 v2.34 신규 이식으로 묶지 않는다.

## 실행 순서와 완료 판정

1. 실제 비교 보고서의 입력/버전/산출물을 회귀 자료로 고정한다. P0-05의 WebP exact 인코딩 문제를 먼저 수정하고 단일 제출·원본·폴더·계보 보존 조건을 함께 검증한다. 품질 효과가 없는 항목은 근거를 남겨 보류하되 P0 보존 계약은 해제하지 않는다.
2. P0-01과 P0-03의 회귀 기준을 마련한 뒤 P0-02를 엔진·adapter·계보·UI 단위로 구현한다. 키 제거 파일을 변경한다면 P0-04를 같은 변경 묶음의 수용 조건으로 적용한다.
3. 최신으로 처리됐다는 사실만으로 화질을 승인하지 않는다. P1-05는 생성 전 명세 전달을 먼저 검증하고 모델 품질은 별도 실제 결과로 판단한다. P2는 각각 독립 기능으로 채택 여부를 결정한다. P1-06은 사용자 결정으로 제품 개발에서 제외했다.
4. 각 변경은 관련 엔진 시험 + 앱 통합 시험 + 최종 artifact 검증을 통과해야 완료다. UI 변경은 `apps/web/README.md`에 따라 이미 승인된 ego TaskSpace에서 확인한다. 기존 ego smoke는 연결 검사에 한정되므로 새 기능의 조작/검수 결과를 별도로 기록한다.
5. 결과보고에는 코드 확인, 합성 fixture, 실제 MP4 로컬 재처리, 실제 유료 생성, 브라우저 확인을 구분하고 미실행 항목을 남긴다. 현재 문서 작성만으로 위 수용 조건이나 실제 품질 개선이 검증된 것은 아니다.
