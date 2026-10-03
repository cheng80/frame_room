# 화면 단계 → 엔진 → 새 API 대응표

기준: 검증된 sprite-gen 2.12.1 / `b058341f7543f3adcbea227bd4e6b7587895b1bc`. CLI는 실제 명령, Python 경로는 실제 코드, `/v1/...`는 **제안 API이며 구현되지 않았다**. 새 API·엔터티·상태 이름의 정본은 [data-contract.md](data-contract.md)와 [architecture.md](architecture.md)다. 기존 HTTP API는 “기존”으로 표시한다. 엔진 세부 근거·출력 함정은 [engine-audit.md](engine-audit.md), 기준 증거는 [baseline.json](baseline.json)에 있다. 아래 표의 상태 대응은 새 앱의 요구사항이지 현재 엔진이 모두 지원한다는 뜻이 아니다.

## 1. 전체 제작 흐름

| UI 단계 / 새 필드 | 현재 CLI·함수와 코드 위치 | 입력 → 출력 계약 | 새 API·진행/실패/취소/재시도 |
| --- | --- | --- | --- |
| 프로젝트 생성/열기: 이름, 캐릭터 ID, 방향, pixel/non-pixel 모드 | 프로젝트 목록·통합 저장 계층 없음. run별 파일만 존재 | 새 projectId → 프로젝트 revision, asset/job/run 목록 | `POST /v1/projects`, `GET /v1/projects/{p}`, `POST /v1/projects/{p}/restore-revision`. 설정은 `PATCH /v1/projects/{p}/edits`의 typed operations. 백업 복원은 `POST /v1/projects/restore`로 새 projectId에 검증 복원. 손상본 보존 |
| 이미지 등록: identity/style 역할, 파일 미리보기, 원본 비교 | `prepare --base-image`; `prepare.run()` (`gen/prepare.py:899`); 별도 업로드 API 없음 | 원본 PNG 등 → 불변 asset + metadata/hash, engine에는 작업 복사 `base-source.*` | `POST /v1/projects/{p}/assets` multipart {files,role,importMode}. 업로드/검증 진행 분리. decode/빈 알파 실패는 원인 표시. 취소한 미완료 asset은 참조하지 않음. hash 기반 업로드 재사용 |
| 승인 기준: 얼굴·의상·무기·몸 비율·팔레트·방향, 변경 허용 범위, 승인자/버전 | 별도 SSOT 승인 기능 없음. `style`은 문자열; `--ref` 다중 이미지는 role이 구분되지 않음 | identityAssetId + styleAssetIds + traits → approved referenceRevisionId | `POST /v1/projects/{p}/reference-revisions`로 draft 생성 후 `POST /v1/reference-revisions/{r}/approve`. 비어 있는 identity 승인 차단. 승인 변경은 새 reference revision. 생성 job은 시작 시 referenceRevisionId snapshot 고정 |
| provider 상태: 명시 provider, 인증준비/권한/잔여량 구분, 과금 경로 | `workflow.access.probe_access()` (`workflow/access.py:14`), `workflow --kind sprite` | credential-readiness → login 상태·billing route; quota/subscription은 unknown 가능 | `GET /v1/providers`. 실제 호출 없이 로컬 probe. API 키 자체는 응답 금지. ready를 생성 성공으로 표시하지 않음. 이번 조사에서는 생성 버튼을 실행하지 않음 |
| 동작·프레임 설정: 동작명, 키포즈 매핑, frame count, FPS, loop/one-shot, 셀/여백, prompt preview | `prepare --out-dir --character-id --base-image --request ...`; `normalize_states`, `draw_guide`, `row_prompt`, `build_generation_plan` (`prepare.py:438,608,728,753`) | UI 타입값 → `sprite-request.json`, prompts, guides, 선택형 generation-plan | `PATCH /v1/projects/{p}/edits`의 typed operations로 설정 저장. generate job의 준비 단계가 저장 revision으로 request를 생성하므로 사용자 JSON 편집 불필요. 비어 있지 않은 폴더 force 덮기 대신 새 runId. 준비 단계의 검증 실패를 해당 job에 기록 |
| 생성: provider/model·품질·해상도·참조별 역할·동작별 진행 | `gen --provider ... --prompt-file ... --ref ...`; `gen.generate_image()` (`gen/__init__.py:243`). `gen-set --states ... --concurrency ...` / `gen_set.run_set()` (`gen/gen_set.py:198`) | prompt+ref→검증 PNG + `.raw.png` + report; gen-set→상태별 raw/report/log + table/set.report | `POST /v1/projects/{p}/jobs` operation=`generate`, params.scope=`states`. `202 jobId`; SSE로 state 시작/완료, 모델 내부 진행은 indeterminate. gen-set가 expose하지 않는 quality/resolution/facing/style refs는 typed adapter에서 개별 gen request로 전달. provider 자동 전환 금지. retry는 새 attemptId |
| 기존 PNG·시트 가져오기: 실제 alpha 표시, grid/수동 영역/자동 성분 선택 | `unpack-atlas --atlas --grid/--manifest` 또는 `--pngs-dir`; `import_png_groups()` (`frames/unpack_atlas.py:268`) | atlas/PNG→engine run+frames manifest+unpack-source. PNG는 최대 캔버스 중앙배치, resize 없음 | `POST /v1/projects/{p}/assets` {files,role,importMode} 후 처리가 필요하면 operation=`extract` job. params에서 PNG/atlas/row 입력 모드를 구분. 원본 immutable. 자동 bbox/그리드 경계를 검수한 후 채택. 셀 밖 장비를 미리 잘라 없애지 않음. staging 실패 시 이전 run 유지 |
| 배경 제거: 원본/결과 split view, 검사 배경, alpha overlay, key·strength·band·erode·decontam | `cutout INPUT --out ... --key auto/white/magenta/green --white-check`; `cutout.cutout()` (`frames/cutout.py:326`) | 균일배경 PNG→RGBA PNG + stdout stats + 검사용 합성 이미지. 일반 자연배경 segmentation 아님 | `POST /v1/projects/{p}/jobs` operation=`cutout`. pixel count 단위 진행 없음→단계 표시. 불투명 체크무늬를 투명으로 오인하지 않음. 실패 결과도 검토용 artifact로 보존하되 승인 결과에 포함하지 않음. 설정 변경은 새 처리 버전 |
| 프레임 분리: 예상 수, 연결 성분 선택/병합/제외, 잘림 경고 | `extract --states --segmentation components/projection`; `extract_component_images`, `remove_chroma_background`, `connected_components` (`frames/extract.py:529,1118,2518`); 표정용 `slice-sheet` 별도 | raw+request→frames+frame_records+frames-manifest 또는 extract-failure. 기존 extract는 fit까지 수행 | `POST /v1/projects/{p}/jobs` operation=`extract`, params.segmentation으로 분리 모드 지정. 원본보존 모드는 새 adapter가 pre-fit crops/source regions를 반환. 추출 count 불일치·위성 component 제외는 needs_review. 부분 재시도는 상태/영역 범위를 명시 |
| 공통 배율·발 정렬: standing reference, body landmarks, source anchor, confidence/manual, sharedScale, targetAnchor, offset, overflow | 새 공통 배율 adapter 필요. 현 `fit_to_cell`, `row_placement`, `place_row_frame` (`extract.py:1260,2290,2318`)는 동작 전체 계약 아님 | pre-fit crop+원본 좌표+승인 body scale→동일 cell aligned frame + mapping + overflow metrics | `PATCH /v1/projects/{p}/edits`의 typed alignment operations로 저장하고 `POST /v1/projects/{p}/jobs` operation=`align`으로 처리. 자동 발 미확정은 needs_review. 웅크림 확대 금지. 긴 무기 초과 시 global resize/canvas expand 선택. 수동 보정은 frameVersionId 귀속 |
| 후보/재생 순서: 선택, 재배열, 복제, 보관, 변형·픽셀 편집, 되돌리기 | `curate.curation.state_plan`, `apply_pixel_edits`, `apply_transform`, `write_curation_atomic` (`curation.py:889,1009,1033,1082`); **기존** `GET /api/run`, `POST /api/curation` | curation.json의 selected/order/clones/pixels/transforms + run_revision/state revision | 조회는 `GET /v1/projects/{p}`, 저장은 `PATCH /v1/projects/{p}/edits` {expectedRevision,operations} → {savedRevision,engineRevision}. 409 시 기존 draft를 유지하며 reconcile UI 제공. 후보 int↔frameVersionId 매핑. `selected: []`는 엔진에서 all default가 되므로 새 UI에서 “아무 프레임 없음”을 별도 표현 |
| 부분 재생성: 한 프레임/선택 범위, 참조 버전, prompt 차이, 기존과 비교 | `reroll --state`는 **행 전체 take 추가**이며 pixel_unfake 필수 (`effects/reroll.py:69–103`); `interpolate`는 두 프레임 사이 새 후보 | 기존 primary 유지 + take raw + request takes. 단일 프레임 교체 API 아님 | `POST /v1/projects/{p}/jobs` operation=`generate`, params.scope=`frame` 및 대상 frameVersionId/occurrenceId. 새 generationVersionId/frameVersionId 후보 생성 후 비교 승인. 채택은 edits typed operation으로 기존 occurrence만 명시 치환. 이전 anchor/보정 자동 재적용 금지. 취소 시 기존 승인 frame 유지 |
| 재생 검수: 실제 크기/확대, onion skin, 배경, FPS, 단발/반복, occurrence별 durationMs | `preview`, `compose-gif`, `inspect`, `inspect-motion`; **기존** `/api/state-fps`는1..30 fps. duration은 clone+fps 방식 (`serve_curation.py:1454`, `compose_atlas.py:216`) | curation/frames/request→검사 report·GIF·baked preview | `POST /v1/projects/{p}/jobs` operation=`inspect` 또는 `bake`. 최종 preview bundle은 bake job의 검증 artifact이며 별도 preview endpoint 없음. timing은 edits로 저장. 가변시간 UI 활성화 전 composer에 occurrence별 duration_ms 지원 필요. loop→state.loop. 미확인 foot/contact는 needs_review |
| 팀 색 아웃라인: 팀/색/두께/불투명도/4·8방향, 표시용 vs bake | 기존 `extract.enforce_outline()`는 pixel-unfake 실루엣 1px outline; `recolor`는 팔레트 교환. 요구한 팀색8방향 불투명도 합성과 다름 (`extract.py:2438`) | aligned+baked source→선택형 outlined frame + output padding | `PATCH /v1/projects/{p}/edits`의 typed outline operations. 새 deterministic renderer를 bake job에 적용. 원본 alpha 보존, 확장 여백 계산. background residue를 숨기지 않도록 outline off QA 동시 제공 |
| 게임용 출력: atlas/PNG zip/Aseprite JSON, timing/loop/anchor, 저장 위치, bundle 검증 | `compose-atlas`, `export-aseprite`; `export-pngs --selected-only`는 비교 검증/특수 정적 출력에 한정. **기존** `/api/compose`, `/api/export`, `/download/atlas`, `/download/pngs`, `/download/gifs` | compose→sprite-sheet-alpha.png + manifest/report. 기존 export-pngs 기본 curated/, Aseprite 기본 exports/aseprite.json | `POST /v1/projects/{p}/exports` {savedRevision,clipRevisionIds,formats,outlineMode}. export job staging에서 bake/검증 후 publish. 최종 PNG는 같은 baked atlas rect에서 추출(승인된 호흡/outline 포함). `GET /v1/exports/{e}`로 검증 artifact URL 조회. 저장실패·stale revision·잘림은 출력 차단 |

## 2. 공통 작업 상태 계약

```json
{
  "jobId": "job-...",
  "operation": "extract",
  "status": "running",
  "attemptId": "attempt-...",
  "inputRevision": 12,
  "engineVersion": {
    "commit": "b058341f7543f3adcbea227bd4e6b7587895b1bc",
    "adapterVersion": "proposed-v1"
  },
  "step": "components",
  "progress": { "step": "components", "completed": 1, "total": 6, "unit": "states" },
  "eventSeq": 7,
  "checkpoint": { "checkpointId": "checkpoint-...", "step": "cutout" },
  "artifacts": [],
  "errors": [],
  "published": false
}
```

- status는 `queued/running/succeeded/needs_review/failed/cancel_requested/canceled/interrupted/provider_outcome_unknown`만 사용한다. `operation`은 `generate/cutout/extract/align/inspect/bake/export` 허용목록이며 분리 전략·가져오기 모드·프레임 재생성 범위는 `params`에서 구분한다.
- `POST /v1/jobs/{j}/cancel` {expectedStatus}: `cancel_requested`를 먼저 영구 저장, 이후 worker가 단계 중단/프로세스 종료와 결과 격리를 확인하면 canceled. 재시작 후 종료 여부를 확인할 수 없으면 interrupted, provider 접수/결과가 불명확하면 provider_outcome_unknown으로 둔다. 취소를 “환불/호출 없었음”으로 표현하지 않는다.
- `POST /v1/jobs/{j}/retry` {failedStep,reuseCheckpoint,idempotencyKey}: 같은 job 출력을 덮지 않고 새 attemptId. 성공 stage의 입력 hash/revision이 같으면 재사용한다. 미확인 provider 호출은 자동 재시도하지 않는다. 생성 재접수는 새 generationVersionId다.
- `GET /v1/jobs/{j}` + `GET /v1/jobs/{j}/events` SSE: 영구 저장한 monotonic eventSeq와 `Last-Event-ID`로 재접속/중복 제거. 모델 내부 %를 만들지 않는다. 기존 extract progress 파일은 완료 단위만 그대로 매핑한다.
- 실패 응답은 `{code,stage,message,retryable,affectedIds,retainedArtifactIds,nextActions}`. 엔진 SystemExit/returncode/stdout/stderr를 보존하되 UI에는 원인과 복구 행동을 보여 준다. 한 상태 실패가 이미 승인된 다른 상태를 삭제하면 안 된다.
- run 단일 writer는 job scheduler와 엔진 lock 모두로 보장한다. 취소·재시작은 pending staging 검증 후 재개하거나 폐기하며 완료 bundle은 불변이다. 사용자 JSON/CLI 조작을 복구 방법으로 요구하지 않는다.

## 3. 재사용 경계와 구현 우선순위

| 판정 | 유지/변경 대상 | 이유와 수용 기준 |
| --- | --- | --- |
| 그대로 감싸서 재사용 | 명시 provider별 gen, 균일배경 cutout, 연결 성분/크로마 함수, curation schema/matrix, atlas absolute rect, Aseprite 변환 | 엔진 전체 재작성 비용 감소. 함수가 실제로 쓴 결과와 report로 완료 판정 |
| 포크 내 명시 adapter | pre-fit source component 출력, 스타일 참조 role 전달, 특정 frame 후보 생성, occurrence duration, shared-scale/foot transform, 팀 아웃라인 | 현재 동작에 없는 계약. 모의 생성 성공과 실제 provider E2E를 별도 capability/test로 표시 |
| 새 앱 계층 | 불변 원본 asset, 승인 버전, generation/frameVersion/occurrence ID, job DB·취소·재개, 프로젝트 snapshot·복구, 타입 검증 API | 기존 run/후보 index만으로 프로젝트 수명과 부분 재생성 이력을 표현할 수 없음 |
| 교체/우회해야 할 동작 | base-source 직접 편집, slice-sheet 높이 정규화 기본 사용, 실패해도 계속되는 save→download, export-pngs의 선택·breathe 차이, 개별 PNG/manifest publication | 원본 불변·체형·미리보기=출력 수용 기준에 직접 영향 |

우선 기존 실제 PNG로 import→pre-fit components→shared scale/manual foot→curation→baked preview→atlas/PNG/timing 출력을 검증한다. 그다음 provider를 mock으로 연결해 실패·취소·재시작을 검증하고, 명시 허용이 있는 별도 실행에서 실제 provider 성공/실패를 검증한다. **이번 연구는 유료 생성 호출 및 앱 구현을 수행하지 않았다.**

## 4. API 연결 시 빠뜨리기 쉬운 수용 항목

1. 원본 identity/style/upload/raw의 hash는 처리·정렬·큐레이션·출력 후에도 그대로다. base edit는 새 reference version을 만든다.
2. 서기471/웅크림320의 원본 높이 비율과 머리/무기 비율을 유지하며, 긴 무기 때문에 특정 포즈 몸만 작아지지 않는다.
3. 바닥 망토·아래로 향한 무기·공중 자세는 자동 anchor를 verified로 만들지 않는다. 수동 수정 좌표와 method/confidence를 저장한다.
4. 반투명 경계 RGB 오염·불투명 체크무늬·밝은 테두리·작은 분리 장비를 실제 여러 배경과 component overlay에서 검수한다. 완전 투명 픽셀의 숨은 RGB와 보이는 오염을 구분한다.
5. candidate 선택·순서·clone·프레임 시간·loop·offset을 저장하고 재시작하면 동일하다. 비어 있는 timeline을 all-default로 몰래 바꾸지 않는다.
6. 단일 프레임 재생성은 새 frameVersion 후보가 되고 기존 동작과 원본을 유지한다. 기존 foot/landmark가 새 후보에 자동으로 붙지 않는다.
7. 취소/강제 종료 후 검증 완료 checkpoint만 재사용한다. provider_outcome_unknown과 로컬 canceled를 구별한다.
8. 저장 acknowledgement 실패 또는 stale revision이면 export하지 않는다. 프리뷰와 출력은 같은 editRevision/baked frames/timing을 사용한다.
9. 최종 PNG/atlas/Aseprite·manifest를 별도 뷰어에서 읽었을 때 clone 순서·duration·단발/반복·호흡·outline이 일치한다. Aseprite JSON만으로 loop 정책이 전달된다고 가정하지 않는다.
10. mock provider가 통과한 테스트는 mock으로 표기하고, Codex login-ready 상태를 provider integration 완료로 표시하지 않는다.
