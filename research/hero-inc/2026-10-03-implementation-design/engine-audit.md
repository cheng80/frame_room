# sprite-gen 엔진 역분석

조사일: 2026-10-03 UTC. 이번 문서는 조사·설계 산출물이다. 공용 설치본과 기존 연구 문서는 수정하지 않았으며 생성 provider를 호출하지 않았다. 코드 위치는 별도 표기가 없으면 `/Users/cheng80/.codex/skills/sprite-gen` 아래 경로다. **관찰**은 실제 읽은 파일·명령 결과, **추론**은 그 코드로부터 예상되는 동작, **제안**은 새 앱의 설계, **미확인**은 실행하지 않은 품질·통합 동작을 뜻한다.

## 먼저 알아야 할 결론

- **관찰:** 설치본의 버전은 2.12.1이며 공개 태그 `v2.12.1`이 가리키는 `b058341f7543f3adcbea227bd4e6b7587895b1bc`의 360개 파일과 SHA256이 모두 일치한다. `.git`은 없지만 릴리스 소스의 로컬 변경은 발견되지 않았다. 런타임 폴더와 설치 이력은 이 비교로 증명하지 않는다. [태그](https://github.com/aldegad/sprite-gen/tree/v2.12.1), [비교 증거](sources/engine-upstream/file-comparison.json), [기준 기록](baseline.json).
- **관찰:** 조사 시점 공개 `main`은 `8529230acc6eaf868e1df93521bf2cf448026633`이며 커밋 메시지는 2.18.0 릴리스 병합이다. 설치본보다 새롭다. 본 역분석은 **2.12.1 고정 커밋**을 대상으로 하며 새 main 기능을 검증한 것으로 취급하지 않는다. [main 관측 원문](sources/engine-upstream/main-head.json), [관측 커밋](https://github.com/aldegad/sprite-gen/commit/8529230acc6eaf868e1df93521bf2cf448026633).
- **관찰/추론:** `slice-sheet`는 셀별 본체 높이를 목표 높이로 맞춰 웅크림을 확대한다. 기존 `extract` 역시 경로에 따라 개별 프레임 또는 스트립 단위 축소·픽셀 격자 재해석을 수행한다. 어느 것도 새 앱의 캐릭터/방향 전체 **원본 공통 배율** 계약과 자동으로 같아지지 않는다. [slice_sheet.py:213–240](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/frames/slice_sheet.py#L213-L240), [extract.py:1260](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/frames/extract.py#L1260).
- **관찰:** 후보 선택·순서·복제·픽셀 수정·변형과 세대 검증은 재사용할 수 있다. 그러나 원본 참조 승인, 스타일 참조의 독립 역할, 불변 프레임 ID, 프로젝트 저장/복원, 작업 취소, 임의 프레임 시간, 팀 색 아웃라인은 새 계약이 필요하다. [curation.py](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/curate/curation.py), [단계 대응표](cli-api-matrix.md).

## 1. 기준·라이선스·환경

**관찰:** `SKILL.md:1–5`, `pyproject.toml:12–20`의 버전은 2.12.1, 라이선스는 Apache-2.0이다. `LICENSE` 전문과 `NOTICE`가 포함되어 있다. `NOTICE:1–29`에는 Alex Kim 저작권, hatch-pet 워크플로 영감, perfectpixel-studio의 MIT 기반 정렬·분리·크로마·픽셀 피치 관련 출처가 적혀 있다. [LICENSE](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/LICENSE), [NOTICE](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/NOTICE). 프로젝트 포크에는 이 파일과 개별 SPDX·출처 주석을 보존하고 수정 파일의 변경 내역을 기록한다.

| 항목 | 실제 관측 |
| --- | --- |
| 실행 인터프리터 | `/Users/cheng80/.codex/skills/sprite-gen/.venv/bin/python`, CPython 3.12.10 |
| 엔진 요구 | Python ≥3.11, Pillow ≥12.3.0,<13, NumPy ≥2.2.6,<3; build setuptools ≥77 |
| 설치 패키지 | sprite-gen 2.12.1, Pillow 12.3.0, NumPy 2.5.2, pytest 9.1.1 |
| 설치 형태 | editable install; `direct_url.json`은 공용 설치 경로를 가리킴 |
| 실행 파일 | codex·ffmpeg·node·git 발견; `img2webp` 미발견 |
| 영향 | 이미지 행 생성/추출/아틀라스 분석에는 img2webp 불필요. exact-alpha WebP 영상 출력은 별도 설치 전 미검증 |
| 관련 지침 | 설치본 `SKILL.md`, `docs/run-contract.md`, `docs/interpreter.md`, `docs/architecture.md` 등 읽음. 프로젝트와 설치본 모두 `.agents/skills` 없음, 프로젝트 `AGENTS.md` 없음 |

코드 기준: [pyproject.toml](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/pyproject.toml), [SKILL.md](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/SKILL.md). 모든 Python 관측 명령에 `PYTHONDONTWRITEBYTECODE=1`을 설정했다. `.venv`·캐시·egg-info를 제외한 릴리스 파일 대조 결과는 360/360 일치이며 추가 소스 파일도 없다. 설치본의 Git 작업 상태를 확인했다고 표현하지 않는다.

**관찰:** 모델 호출 없는 `workflow.access.probe_access()` 결과 Codex 로그인은 ready, Grok 인증은 unavailable, OpenAI API 키는 absent였다. Codex 구독 권한·이미지 잔여량은 unknown이다. 로그인 성공은 실제 생성 성공 증거가 아니다. OpenAI는 키 존재와 무관하게 호출별 과금 경로다. 현 함수가 키 부재 시 기본 `billing: subscription` 값을 돌려주는 점은 UI에서 그대로 표시하지 말고 provider capability와 분리한다. [access.py:14](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/workflow/access.py#L14), [gen/__init__.py:14–18](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/gen/__init__.py#L14-L18).

## 2. 실제 입력·출력 계약

**관찰:** 정식 요청 파일 이름은 `sprite-request.json`이다. 기존 설계에서 쓴 `request.json`은 개념명으로만 보아야 한다. `prepare.run()`은 기준 이미지 파일을 `base-source.<ext>`로 복사하고, `states`, `cell`, `chroma_key`, `style`, 선택형 `fit`·`directions`를 요청에 기록한다. 스타일은 문자열이며 역할이 구분된 별도 스타일 이미지 계약은 없다. `gen`은 `--ref` 여러 개를 받지만 `gen-set`은 `identity_ref()`와 layout guide를 조합한다. 새 identity/style UI를 만든다고 기존 gen-set에 스타일 이미지가 자동 전달되지 않는다. [prepare.py:899–1032](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/gen/prepare.py#L899-L1032), [gen_set.py:148–158](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/gen/gen_set.py#L148-L158).

| 파일/영역 | 역할·주의 |
| --- | --- |
| `base-source.*` | 엔진의 생성 정체성 입력. 새 앱 원본 저장소 자체로 사용하면 안 됨 |
| `sprite-request.json` | 상태, frame count, fps, loop, 셀, fit·크로마 등 실행 요청 |
| `references/layout-guides/`, `prompts/` | 상태별 안내 이미지와 생성 프롬프트 |
| `references/generation-plan.json` | 선택형 방향 앵커 → 동작 행 의존관계 |
| `raw/<state>.png` 또는 `raw/<direction>/<pose>.png` | 생성 시트. `gen`은 `<out>.raw.png`도 보존 |
| `raw/...takes/<label>.png` | 추가 후보 생성 스트립. `states.<state>.takes`와 함께 해석 |
| `frames/frames-manifest.json` | 추출된 실제 파일 경로, 상태별 품질 결과, 선택형 plain/orig·takes |
| `frames/.../frame-N.png` | 현재 파생 프레임; 영구 frame ID가 아니라 세대별 candidate index |
| `.plain.png`, `orig/frame-N.png` | 전자는 최종 bake 가능한 셀 크기 대안; 후자는 고해상 표시용. `orig`는 업로드 원본과 다름 |
| `curation.json` | 선택·순서·변형·픽셀·복제·앵커·호흡 등 비파괴 편집 |
| `palette.lock.json` | 픽셀 언페이크 경로의 고정 공유 팔레트 |
| `sprite-sheet-alpha.png`, `manifest.json` | 최종 아틀라스와 절대 rect/재생 계약 |
| `curated/`, `exports/aseprite.json` | 개별 PNG, Aseprite 호환 JSON 기본 출력 |
| `reports/gen-set/` | 상태별 생성 report/log, `table.md`, `set.report.json` |

파일 경로는 문자열 패턴을 재조립하지 않고 `spec/layout.py`와 manifest row `files`에서 얻는다. 방향 계약이 있는 신규 run은 taxonomy/v1 경로, legacy run은 flat 경로가 가능하다. [layout.py:1–23,57–114](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/spec/layout.py#L1-L114).

## 3. 비율·발 위치에 대한 코드 판정

| 경로 | 실제 처리 | 새 앱 의미 |
| --- | --- | --- |
| `slice_sheet.slice_sheet` | 셀 최대 연결 성분 높이로 `target_height / main_height`를 계산, LANCZOS resize, 바닥선 정렬 | **관찰/추론:** 높이 471/320인 포즈를 같은 목표 높이로 맞춤. 웅크림 보존 기본 경로로 사용 불가 |
| `extract.fit_to_cell` | component별 `min(usableW/w, usableH/h, 1)`; 기본 LANCZOS. 확대는 안 하지만 폭/높이 초과 프레임만 축소 | **관찰/추론:** 긴 무기만 셀 폭을 초과하면 몸도 작아짐. 모든 동작의 공통 배율 계약 아님 |
| `extract._snap_strip` → `conform_row_logical` | 프레임별 pixel pitch/phase로 논리격자 복원; 물리 cap 초과 시 **한 스트립의 최대 크기**로 그 스트립 전체 축소 | **관찰/추론:** 같은 스트립 내부는 공통 cap 배율이나 서로 다른 동작·take 전체 배율 보증 없음. 원본 픽셀 비율 그대로 보존하는 모드도 아님 |
| `register_row_frames`/`row_placement` | 상체 65% 알파 겹침으로 작은 이동 정합, 행 union의 x 배치 | 몸/발 의미를 이해하는 검출기가 아니라 실루엣 휴리스틱 |
| `place_row_frame` | 기본 프레임별 알파 하단 접지; `ground_frames=false`면 공통 top 사용 | 점프의 고도·공중 자세를 자동 접지하면 의도 손실 가능 |
| `unpack-atlas` 자동 검출 | 알파 성분 bbox를 공통 셀 중앙에 배치 | 리사이즈는 없지만 발 정렬은 보장하지 않음 |
| `unpack-atlas --pngs-dir` | 전체 PNG 최대 캔버스를 공통 셀로 사용하고 작은 PNG는 중앙 배치, resize 없음 | 비율 검증의 안전한 시작점. 신규 앵커 배치를 이후 적용 |
| `compose-atlas` | source 크기가 요청 셀과 다르면 오류. 셀 내부 transform·pixel edit·breathe 적용 | source만 커지면 자동 셀 확장되지 않음. 변형으로 셀 밖에 나간 픽셀은 잘릴 수 있으므로 미리 검사 |

코드 위치: [slice_sheet.py:218–240](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/frames/slice_sheet.py#L218-L240), [extract.py:1260–1330](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/frames/extract.py#L1260-L1330), [extract.py:2199–2341](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/frames/extract.py#L2199-L2341), [extract.py:3340–3398](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/frames/extract.py#L3340-L3398), [unpack_atlas.py:214–230,280–310](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/frames/unpack_atlas.py#L214-L310), [compose_atlas.py:175–209](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/compose/compose_atlas.py#L175-L209).

**관찰:** 엔진 `foot-centroid`는 실루엣 아래 20%의 알파 가중중심이고 가로 배치는 셀 안으로 clamp한다. 제작 노트 거너의 아래 12%·alpha≥16·좌우 끝 중간 계산과 다르다. 망토/총구/지면 이펙트를 발로 오인할 수 있으므로 새 정렬 어댑터는 자동 후보와 사람이 승인한 발을 구분한다. 몸 체고는 장비 포함 alpha bbox와 분리 저장한다. [extract.py:1202–1218,1304–1316](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/frames/extract.py#L1202-L1316).

**관찰:** 연결 성분 추출은 큰 성분을 seed로 고르고, 작은 위성 성분을 x 최근접 및 seed 주변 15% 범위로 묶는다. 멀리 떨어진 성분은 경고 후 제외한다. 분리된 칼날·총구 섬광이 합법적 장비인지 노이즈인지 자동으로 알지 못한다. 새 UI의 component 선택/병합/제외 검수와 원본 crop 좌표 보존이 필요하다. [extract.py:2518–2561](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/frames/extract.py#L2518-L2561).

**제안:** 엔진 포크에 `segment_to_source_components()` 어댑터를 두어 크로마 제거·분리 결과를 **리사이즈 전 crop + 원본 좌표 + source hash**로 반환한다. 기존 `extract_component_images()`를 기반으로 하되 성분 후보와 drop 이유를 구조화한다. 기존 원본보존 align 모드는 언페이크/자동 cap과 분리하고 `sharedScale`을 기준 자세에서 한 번 계산한다. 모든 동작의 출력 앵커는 `targetAnchor − sharedScale × sourceAnchor + authoredOffset`. 초과 시 전체 공통 축소 또는 셀 확장을 선택하며 한 프레임만 축소하지 않는다. 이 함수/API는 아직 구현되지 않았다.

## 4. 저장·복원·부분 재생성

**관찰:** `curation.json`의 `selected`는 재생 순서, `order`는 후보를 포함한 표시 순서다. `clones`, `unlinked`, `deleted`, `pixels`, `transforms`, `anchors`, `breathe`도 저장한다. 250ms 자동 저장과 출력 직전 flush가 있다. [persistence.js:7–99](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/serve/curator/src/persistence.js#L7-L99).

**관찰:** 세대 계약은 전역 `run_revision` + 행별 `revision`이다. 전역 지문이 달라져도 행의 원료 digest 리스트가 현재 리스트의 prefix면 기존 편집을 구제한다. take가 뒤에 붙는 경우의 기존 인덱스 유지에 적합하다. 읽기는 원문을 바꾸지 않고, stale 값을 덮어쓰는 writer가 `curation.stale-<hash>.json`으로 백업한다. `POST /api/curation`은 클라이언트 `runRevision`이 오래되면 409를 낸다. `docs/architecture.md`의 “불일치하면 전체 무시” 설명보다 이 코드를 기준으로 설계한다. [curation.py:418–554,593–672](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/curate/curation.py#L418-L672), [serve_curation.py:1222–1293](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/serve/serve_curation.py#L1222-L1293).

**제안:** 새 `frameVersionId`는 [FrameVersion 계약](data-contract.md)의 `rawAssetId`, `generationVersionId`, `sourceRect`, `sourceToFrameTransform`, `extractionVersion`이 가리키는 불변 픽셀 버전으로 만들고, 엔진 `(runId,state,candidateIndex,runRevision)`와 mapping한다. 원본 해시는 연결된 Asset이 소유한다. UI timeline은 별도 `occurrenceId`를 가진다. 참조 변경/재생성으로 픽셀이 달라지면 새 frameVersionId를 발급하고 기존 수동 발·몸 landmark를 “재검수 필요”로 둔다. run_revision은 mtime도 포함하므로 프로젝트의 영구 콘텐츠 ID로 사용하지 않는다.

**관찰:** 기존 `/api/base-edit`는 `base-source` 파일을 직접 수정하고 최초 `.orig`만 보존한다. 또한 `gen-set --force`는 같은 raw 경로를 재생성하며 실패 시 row/report를 지운다. 승인 원본과 과거 생성물을 유지하려면 외부 asset store + 시도별 run 사본을 사용해야 한다. [serve_curation.py:1369–1452](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/serve/serve_curation.py#L1369-L1452), [gen_set.py:154–178](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/gen/gen_set.py#L154-L178).

**관찰:** `reroll`은 한 프레임 교체가 아니라 **상태 행 전체 후보 take 추가**다. `fit.pixel_unfake`가 꺼져 있으면 실행 전 거절한다. 기존 curation 서버는 reroll 후 전체 재추출한다. 따라서 새 UI의 “이 프레임만 다시 만들기”를 기존 reroll과 동의어로 표시하면 안 된다. 별도 generation job으로 1프레임 후보를 만들어 immutable source로 가져온 뒤 선택한 occurrence만 교체하는 계약을 추가한다. [reroll.py:69–103,121–132](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/effects/reroll.py#L69-L132).

## 5. 진행·실패·취소

**관찰:** `gen-set` 기본 동시수는 코드에서 **6**이다(일부 소개 문구의 4와 다름). 상태별 완료 JSON line, report/log, 마지막 요약을 기록하며 결과 이미지와 provider가 든 report 둘 다 확인돼야 완료/재사용으로 취급한다. `--states`와 `--force`가 있으나 job 영구 레코드나 취소 API는 없다. [gen_set.py:38,75–103,198–241](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/gen/gen_set.py#L38-L241).

**관찰:** provider는 explicit 선택 시 그대로 사용한다. 미지정 기본은 codex, 가용성 실패 시 grok로 전환할 수 있다. openai는 explicit-only이며 gen-set의 CLI 선택지에는 없다. Codex 생성 자식 timeout 기본은 180초이고 `GenTimeoutError`만 한 번 재시도한다. OpenAI HTTP timeout은 자동 재시도하지 않아 중복 과금 가능성을 피한다. [gen/__init__.py:77–91,243–336](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/gen/__init__.py#L77-L336), [base.py:69–75](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/gen/base.py#L69-L75), [openai_provider.py:210–235](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/gen/openai_provider.py#L210-L235).

**관찰:** extract는 `.sprite-gen.progress.json`의 done/total/phase를 기록하고 staging frames를 commit한다. 부분 `--states` 추출은 나머지 행을 staging에 복사하여 유지한다. `_commit_generation`은 frames와 실패 증거를 잠금하에 함께 전환하며 예외 시 롤백한다. write lock은 죽은 pid의 lock을 회수한다. 이는 정상 Python 예외/프로세스 종료에 대한 기반이며 OS 강제종료·전원손실까지 프로젝트 복구를 보증하는 영구 작업 큐는 아니다. [extract.py:2914–2980,3050–3095,3752–3770](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/frames/extract.py#L2914-L3095), [runio.py:150–216](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/spec/runio.py#L150-L216).

**제안:** Python worker를 별도 subprocess로 실행하고 job DB는 [architecture.md](architecture.md)의 `queued/running/succeeded/needs_review/failed/cancel_requested/canceled/interrupted/provider_outcome_unknown` 상태를 따른다. 취소는 미래 단계 시작을 멈추고 자식 process group 종료를 요청하며, 실제 종료와 결과 격리가 확인된 뒤에만 canceled가 된다. remote provider의 접수/결과를 확인할 수 없으면 provider_outcome_unknown으로 남긴다. UI에 “취소 요청됨”과 “중단 완료”를 구별한다. 네트워크 응답 미확인 생성의 자동 재호출은 금지하고 기존 provider 결과/로그 확인 후 사용자가 새 시도를 만든다. 기존 완료 asset은 취소/실패로 지우지 않는다. 재시작 시 running job을 interrupted로 복구하고 검증된 stage checkpoint부터 재개한다. API에는 정수 inputRevision, 단조 증가 eventSeq를 사용하고 새 operation·필드명은 [data-contract.md](data-contract.md)를 따른다. 이 동작은 새 앱 수용 테스트 대상이며 현재 실행 완료가 아니다.

## 6. 출력과 미리보기 일치의 함정

**관찰:** compose는 canonical/plain 선택, pixel edit, transform, clone 연결, breathe를 bake하며 동일 instance는 atlas rect를 공유한다. `manifest.frame_layout.rows`는 재생 순서의 절대 rect 배열이다. `animation.rows`에는 fps, loop, durations_ms가 들어간다. 현재 durations_ms는 fps에서 만든 **등간격 배열**이며 기존 UI의 늘어난 hold는 clone 반복으로 표현한다. Aseprite export는 duration은 옮기지만 loop 정책은 manifest에 남는다. [compose_atlas.py:93–119,158–232](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/compose/compose_atlas.py#L93-L232), [engine-export.md](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/docs/engine-export.md).

**관찰/추론:** `export-pngs` 기본은 **모든 물리 프레임**이며 `--selected-only`를 줘야 선택 순서를 따른다. 코드에는 `breathe.phase_frame` 적용이 없다. 따라서 호흡이 포함된 최종 애니메이션의 개별 PNG는 compose된 아틀라스 rect를 잘라 만들어야 미리보기와 같다. 반복 index를 파일명으로만 내보내면 같은 이름을 재사용할 수 있으므로 occurrence 번호와 timing manifest를 함께 출력한다. [export_pngs.py:62–112](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/compose/export_pngs.py#L62-L112).

**관찰/추론:** 기존 `save()`는 실패를 배너에 표시하지만 예외를 다시 던지지 않는다. `downloadArtifact()`는 `await save()` 뒤 항상 다운로드로 넘어갈 수 있다. 저장 실패와 출력 연결은 코드를 통해 확인한 위험이며, 브라우저 재현은 이번 담당 범위에서 실행하지 않았다. 새 API는 서버가 승인한 편집 revision을 응답하고 export가 그 revision을 필수로 요구해야 한다. [persistence.js:103–149](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/serve/curator/src/persistence.js#L103-L149).

**관찰/추론:** compose는 PNG와 manifest를 각각 atomic-write하지만 둘을 하나의 publish transaction으로 교체하지 않는다. 새 앱은 job별 임시 export 디렉터리에서 완성·검증 후 완성 bundle을 게시한다. 또한 compose 시작의 `heal_run()`은 엔진 변경 시 프레임을 재추출할 수 있으므로 engine revision을 고정하고 export 전에 파생 세대 변경을 사용자에게 드러낸다. [compose_atlas.py:66–77,297–315](https://github.com/aldegad/sprite-gen/blob/b058341f7543f3adcbea227bd4e6b7587895b1bc/sprite_gen/compose/compose_atlas.py#L66-L77).

## 7. 프로젝트 전용 포크 구조 — 제안, 아직 생성하지 않음

상위 폴더명과 실행 배치는 [architecture.md](architecture.md)가 정본이다. 아래는 해당 구조에 엔진 run의 자료 소유권을 덧붙인 것이다.

```text
copy_spritegen/
  apps/web/                        React+Vite UI
  services/api/                    프로젝트·asset·승인·job API
  services/worker/                 Python subprocess 작업 실행기
  packages/contracts/             UI/API schema 및 타입
  engine/sprite-gen/               고정 커밋의 프로젝트 전용 포크 소스
    LICENSE, NOTICE, pyproject.toml, sprite_gen/, tests/
  adapters/spritegen/              명시적 엔진 함수/CLI 어댑터
  alignment/                      공통 배율·수동 발·초과 검수
  .data/projects/<projectId>/
    project.json
    assets/<sha256>/original.*     업로드·생성 원본 불변
    references/<referenceRevisionId>/ 승인 외형·스타일 역할과 traits
    runs/<runId>/                  sprite-request/frames/curation 등 엔진 호환
    exports/<exportId>/            검증한 bundle 불변
  .data/jobs/<jobId>/<attemptId>/  입력 snapshot·event·checkpoint·실패 증거
  research/                       현재 조사 문서
```

프로젝트 전용 `.venv`에서 고정 fork를 설치하며 공용 `~/.codex/skills/sprite-gen`을 PYTHONPATH 의존이나 수정 대상으로 삼지 않는다. 우선 2.12.1에 대한 수용 테스트를 구축하고, main 2.18.0 도입 여부는 분리된 diff 검토·테스트로 결정한다. GitHub fork 생성·공개 push·배포는 이번에 수행하지 않았다. 엔진 내부의 전역 프로세스 lock 수명 때문에 API 서버에서 모든 단계를 직접 장기 import 실행하기보다 worker subprocess를 단계별로 분리하는 편이 관리하기 쉽다.

## 8. 검증 범위와 미확인

수행: 공용 설치본 읽기, 기존 README/연구/구현 명세/스킬 읽기, 공개 태그와 main 메타 조회, release tarball 360개 파일 해시 대조, venv/의존·실행파일 관측, 무생성 인증준비 probe, CLI/함수/파일 계약 정적 대조.

미수행: 실제 provider 생성·방향 검출 품질·과금·잔여량 검증, provider 취소의 remote 효과, 큐레이션 저장 실패 브라우저 재현, 새 job recovery 통합, 신규 shared-scale 구현, main 2.18.0 전체 코드 분석, 앱 구현/배포. PNG 처리 실험과 수치 검증은 같은 조사 폴더의 별도 테스트 담당 산출물을 기준으로 읽는다. 이 문서의 “추론”을 실행 결과로 대체하지 않는다.
