# 실제 자산·로컬 엔진 검증

조사일: 2026-10-03. 범위: 공개 거너 자산과 설치된 Python 엔진의 결정론 처리. **웹앱 구현·전체 사용자 흐름·실제 provider 연결 완료 보고가 아니다.** 공용 엔진은 읽기 전용으로 사용했고, 생성·과금 호출은 하지 않았다.

## 핵심 결과

1. 공개 정렬 이미지의 실제 알파 bbox가 제작 노트와 일치한다. 대기 377×471px, 수평 조준 338×378px, 웅크림 329×320px. 세 이미지의 바닥 경계는 모두 y=494이고, 웅크림/대기 높이 비율은 320/471 ≈ 0.6794055다.
2. 실제 자산을 재배치한 입력에 `slice-sheet`를 실행하자 웅크림이 320→471px, 수평 조준이 378→471px로 확대됐다. 가로 정렬도 발이 아닌 장비 포함 bbox 중심을 사용하므로 발 위치가 달라졌다. 애니메이션의 공통 배율·발 앵커 경로로 그대로 채택하면 안 된다.
3. 동일한 512px PNG를 `unpack-atlas`로 가져온 뒤 큐레이션 순서·복제·이동·픽셀 편집을 저장하고 `compose-atlas`, `export-pngs`, `export-aseprite`를 실행했다. 원본 PNG 해시 불변, 저장/로드, 최종 atlas와 curated PNG의 보이는 RGBA 일치를 확인했다.
4. 합성 경계 테스트에서 `slice-sheet`는 650px 무기를 512px 셀에 잘라 넣고 성공 코드 0을 반환했다. 2,070개 불투명 픽셀이 사라졌다. 새 정렬 계층에 명시적인 셀 초과 검사와 승인 정책이 필요하다.
5. 기존 composer는 상태 FPS에서 균등 `durations_ms`를 만든다. 임의의 시간 배열은 지원하지 않으며 반복 hold는 clone 인스턴스로 표현해야 한다. 반복/단발은 manifest에 남지만 Aseprite 출력에는 sprite-gen의 loop 정책이 없다.

## 증거와 재현 파일

| 파일 | 내용 |
| --- | --- |
| [tests/validate_local_engine.py](tests/validate_local_engine.py) | 생성 호출 없는 재현 스크립트. 새 출력 폴더만 허용한다. |
| [artifacts/source-assets/provenance.json](artifacts/source-assets/provenance.json) | 다운로드 URL, 파일별 SHA-256·크기, WebP→PNG 구분, 접근 경위 |
| [artifacts/engine-test-runtime.json](artifacts/engine-test-runtime.json) | 인터프리터·Pillow·NumPy 버전과 사용 엔진 모듈 해시 |
| [artifacts/local-validation-run-v2/results.json](artifacts/local-validation-run-v2/results.json) | 최종 19개 검사 결과와 원본/출력 수치 |
| [artifacts/local-validation-run-v2/logs/](artifacts/local-validation-run-v2/logs/) | 실제 CLI argv·exit code·stdout·stderr |
| [artifacts/validation-comparison.html](artifacts/validation-comparison.html) | 원본 공통 배율과 slice-sheet 결과를 같은 표시 배율로 보는 연구용 정적 비교 |
| [artifacts/local-validation-run-v2/engine-run/manifest.json](artifacts/local-validation-run-v2/engine-run/manifest.json) | 게임용 frame rect, 실제 선택 순서, 반복·시간 메타데이터 |
| [artifacts/local-validation-run-v2/engine-run/sprite-sheet-alpha.png](artifacts/local-validation-run-v2/engine-run/sprite-sheet-alpha.png) | 실제 엔진이 compose한 PNG 아틀라스 |
| [artifacts/local-validation-run-v2/engine-run/curated/](artifacts/local-validation-run-v2/engine-run/curated/) | 실제 큐레이션 변형이 bake된 개별 PNG |
| [artifacts/local-validation-run-v2/engine-run/exports/aseprite.json](artifacts/local-validation-run-v2/engine-run/exports/aseprite.json) | 기존 엔진의 Aseprite 호환 JSON; `.aseprite` 소스 파일 아님 |

재현은 설치본의 전용 인터프리터를 사용한다. 기존 결과 덮어쓰기를 거부하므로 새 경로를 지정한다.

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/cheng80/.codex/skills/sprite-gen/.venv/bin/python \
  research/hero-inc/2026-10-03-implementation-design/tests/validate_local_engine.py \
  --out-dir research/hero-inc/2026-10-03-implementation-design/artifacts/local-validation-rerun
```

스크립트는 다운로드를 하지 않고 `source-assets/`의 보존 자산을 읽는다. 필요한 파일이 없으면 먼저 provenance의 공개 URL을 내려받고 WebP를 RGBA PNG로 변환해야 한다. 공용 경로에 `__pycache__`를 쓰지 않도록 실행과 subprocess 모두 bytecode 생성을 비활성화했다. 출력·로그·fixture는 이 연구 폴더 내부에만 생성했다.

## 실제 자산과 합성 입력의 구분

**직접 관찰:** 작업 시작 시 workspace에는 PNG가 없었다. 엔진 `tests/fixtures/`와 `docs/assets/`에는 이미지가 있었지만 거너 검증에는 공개 제작 노트에서 직접 발견한 URL을 사용했다. 다른 프로젝트는 탐색하지 않았다. 최초 네트워크 sandbox DNS 실패 후 승인된 공개 `curl GET` 다운로드가 성공했다.

실제 파일의 출처는 [제작 노트의 스프라이트 워크벤치](https://suile-21173.web.app/hero-inc/prompts#sprite-workbench)이며, URL은 `/hero-inc-guide/` 아래다. 공개 접근 가능 여부를 상업적 재배포 허가로 해석하지 않는다. 테스트 이미지는 로컬 연구용 사본이다.

| 입력 | 분류 | 실제 알파 관찰 |
| --- | --- | --- |
| [gunner-keyposes.png](https://suile-21173.web.app/hero-inc-guide/gunner-keyposes.png) | 공개 원본 PNG, 1536×1024 | 전 픽셀 alpha=255. 체크무늬가 그림에 포함됨. |
| [gunner.png](https://suile-21173.web.app/hero-inc-guide/gunner.png) | 공개 PNG, 512×512 | alpha 0/255의 실제 투명 이미지. |
| [pose-0-raw.webp](https://suile-21173.web.app/hero-inc-guide/pose-0-raw.webp), [pose-1-raw.webp](https://suile-21173.web.app/hero-inc-guide/pose-1-raw.webp), [pose-3-raw.webp](https://suile-21173.web.app/hero-inc-guide/pose-3-raw.webp) | 공개 포즈별 raw, 384×512 | 모두 불투명. WebP라는 포맷 자체가 투명성을 보장하지 않음. |
| [pose-0-aligned.webp](https://suile-21173.web.app/hero-inc-guide/pose-0-aligned.webp), [pose-1-aligned.webp](https://suile-21173.web.app/hero-inc-guide/pose-1-aligned.webp), [pose-3-aligned.webp](https://suile-21173.web.app/hero-inc-guide/pose-3-aligned.webp) | 공개 배경제거·정렬 결과, 512×512 | 모두 alpha 0/255. PNG 변환 후 디코딩 RGBA가 완전히 같은지 검사함. |
| `real-assets-green-montage.png` | **실제 공개 포즈를 테스트용 초록 배경 위에 재조합한 입력** | 원작의 원본 생성 시트가 아님. slice 정규화 재현을 위해 구성함. |
| `synthetic-overflow-green.png` | **합성 도형 fixture** | 알려진 650px 무기·471px 높이로 잘림을 측정함. 실제 거너의 잘림 사례라는 주장이 아님. |
| `synthetic-prop-below-feet.png` | **합성 도형 fixture** | 발 아래로 내려가는 장비 때문에 바닥 밴드가 발을 잘못 잡는 경우를 구성함. |

PNG 전환은 **디코딩된 WebP 픽셀의 무손실 저장**이다. 공개 PNG 원본을 확보했다거나 WebP 이전의 색을 복원했다는 뜻이 아니다.

## 정렬 수치

좌표는 0부터 시작하고 bbox 오른쪽·아래쪽은 exclusive다. 따라서 `bottom=494`는 마지막 보이는 픽셀 y=493과 높이 512 셀의 바닥 여백 18px를 뜻한다. 알파 bbox 측정은 alpha≥16이며, 세 공개 정렬 자산은 원래 alpha가 0/255라 이 임계값에서 모호하지 않다.

| 공개 포즈 | bbox `(x0,y0,x1,y1)` | bbox 크기 | 장비 포함 bbox 가로 중심 | 아래 12% 밴드 가로 중심 | 실제 알파 픽셀 |
| --- | --- | --- | --- | --- | --- |
| 대기 pose-0 | (128,23,505,494) | 377×471 | 316 | 256 | 53,630 |
| 수평 조준 pose-1 | (148,116,486,494) | 338×378 | 316.5 | 256 | 45,197 |
| 웅크림 pose-3 | (113,174,442,494) | 329×320 | 277 | 256.5 | 40,920 |

**직접 관찰:** 공통 배율 1의 연구용 정렬 prototype은 이 픽셀들을 재배치하며 크기를 변경하지 않았다. 세 포즈 모두 y=494와 알파 픽셀 수가 유지됐고, 웅크림/대기 비율 0.6794055가 보존됐다. 오른쪽 끝이 가장 먼 대기 포즈도 exclusive x=505이므로 2px 가장자리 조건 안에 있다.

**추론/설계:** 장비 포함 bbox의 중심과 발 후보의 중심 차이가 대기 60px, 수평 조준 60.5px, 웅크림 20.5px다. bbox 가운데 정렬을 몸/발 정렬과 혼동하면 무기 방향이 바뀔 때 몸이 움직인다. 위 수치는 몸의 해부학적 체고 측정값이 아니며, `approvedBodyHeight`는 별도 승인 정보가 필요하다.

**측정 한계:** 공개 페이지에서 직접 펼친 코드의 밴드 높이는 `Math.max(4, Math.round(bounds.height * 0.12))`다. 이 테스트의 Python `max(4, round(...))`도 세 bbox에서 57/45/38px로 같은 결과다. 일반적인 정확히 `.5` 경계에서는 JS/Python 반올림 규칙이 다르므로 제품에서는 JS 규칙을 명시적으로 재현해야 한다. 웅크림은 x=256.5라 정수 픽셀 배치 후 0.5px 잔차를 기록했다. 새 앱은 이를 숨기지 않고 앵커 좌표계·반올림을 명시해야 한다.

## slice-sheet 재현과 코드 대조

코드: [frames/slice_sheet.py:218](/Users/cheng80/.codex/skills/sprite-gen/sprite_gen/frames/slice_sheet.py:218)의 최대 연결 성분, 222행의 `target_height / main_height`, 234행의 LANCZOS, 236~240행의 bbox 가로 중심·offset clamp·alpha composite. 문서 `docs/sheet-slicing.md`는 variant 입상용이며 애니메이션 row pipeline이 아니라고 명시한다.

실제 CLI 입력: 위 실제 자산 montage, `--grid 3x1 --cell-width 512 --cell-height 512 --baseline-y 494 --target-height 471 --chroma-key green`. [원시 실행 로그](artifacts/local-validation-run-v2/logs/slice-real.json)를 보존했다.

| 포즈 | 입력→출력 높이 | 코드 배율 | 출력 alpha≥16 bbox | 출력 발 밴드 중심 |
| --- | --- | --- | --- | --- |
| 대기 | 471→471 | 1 | 377×471 | 196 |
| 수평 조준 | 378→471 | 1.2460317 | 421×471 | 181 |
| 웅크림 | 320→471 | 1.471875 | 484×471 | 226.5 |

**직접 관찰:** 웅크림 비율은 0.6794에서 1로 바뀌었다. 픽셀 아트의 LANCZOS 처리와 chroma 재처리 후 출력에는 부분 알파가 생겼다(대기 179개, 수평 조준 8,325개, 웅크림 9,853개). 새 정렬 계층의 최근접 정책과도 구분해야 한다. 이 검사는 배경 제거 품질의 합격 판정이 아니라 정규화의 부작용을 관찰한 것이다.

**합성 반례:** 650×471 subject를 512 셀로 처리할 때 CLI 0, 출력폭 512, 알파 46,230→44,160으로 2,070픽셀이 유실됐다. 코드가 음수 offset을 0으로 제한하고 셀 밖 영역을 잘라 넣기 때문이다. 발 아래 장비 fixture는 수동 정답 (250,451)에 비해 heuristic (341.5,497)을 반환했다. 이를 anatomical foot의 확정값으로 쓰면 안 된다.

새 UI는 상태별 키/격자/연결 성분 검토 뒤, **배율을 적용하기 전** 원본 측정값을 보존하고 공통 배율·앵커·셀 초과를 검사해야 한다. 이미 커진 웅크림을 단순히 다시 발에 맞추는 것으로 체형은 복원되지 않는다.

## 실제 기존 출력 경로 검증

1. 실제 512 PNG 세 장을 `idle`과 `oneshot` 두 입력 그룹으로 복사하고 `_base/gunner.png`를 등록했다.
2. `unpack-atlas --pngs-dir ... --out-dir ...`를 실행했다. 같은 셀 크기의 PNG는 배율 변경 없이 보존됐고 base-source는 바이트 복사됐다. 이 명령의 다른 크기 PNG는 최대 셀에 **가운데 배치**되므로, 가변 크기 원본의 발 정렬 기능으로 해석하면 안 된다. 코드 [unpack_atlas.py:288](/Users/cheng80/.codex/skills/sprite-gen/sprite_gen/frames/unpack_atlas.py:288).
3. `write_curation_atomic`를 writer guard 안에서 호출했다. 순서 `[2,0,3]`, clone `3→1`, clone 이동 `(-3,-2)`, 한 픽셀 색 편집을 저장했다. `load_curation`으로 다시 읽고 revision과 편집을 확인했다. 웹 UI 클릭을 검증한 것은 아니다.
4. `compose-atlas`, `export-pngs --selected-only`, `export-aseprite`를 실행했다. atlas rect 순서의 이미지와 `curated/` 이미지, 엔진 변형 함수의 예상 결과가 보이는 RGBA에서 일치했다. 완전 투명 픽셀의 숨은 RGB는 alpha composite가 정규화할 수 있으므로 비교 기준을 alpha와 alpha>0 RGBA로 정했다.
5. 모든 소스 파일과 `frames/*.png` SHA-256가 작업 전후 동일했다. 원본에 편집을 덮어쓰지 않고 최종 출력에만 적용됐다. 게임 입력은 `frames/`가 아니라 composed atlas 또는 `curated/`다.
6. 잘못된 `_refs` 역할 이름을 포함한 `unpack-atlas --force`가 코드 1로 실패했고, 기존 성공 run의 요청·큐레이션·프레임·출력 바이트가 유지됐다. 강제 종료·취소 복구를 시험한 것은 아니다.

`compose-atlas`는 imported run에 raw가 없어 다시 추출할 수 없다는 `[heal] stale rows kept as-is` 진단을 냈다. 이 경로에서는 보존된 imported 프레임을 사용했으며 새로운 생성이나 추출을 수행하지 않았다.

## 재생 시간·반복 계약

**직접 관찰:** idle FPS 5/loop=true → duration `[200,200,200]`; oneshot FPS 10/loop=false → `[100,100,100]`가 manifest에 저장됐다. 동일 원본 clone은 동일 atlas rect를 재사용했고 Aseprite JSON의 순서·duration도 동일했다.

**제약 확인:** oneshot request에 probe로 `durations_ms:[80,160,320]`를 추가했지만 출력은 `[100,100,100]`이었다. 현재 지원 입력 필드라고 가정해 넣으면 조용히 무시된다. 근거 [compose_atlas.py:216](/Users/cheng80/.codex/skills/sprite-gen/sprite_gen/compose/compose_atlas.py:216). MVP는 기존 모델의 FPS+복제 hold를 명시적으로 UI화하거나, 임의 프레임 duration용 별도 승인 계약·serializer·모든 preview/export 소비자를 함께 구현해야 한다.

첫 연구 실행은 `selected:[1,0,1]`로 반복을 표현한 테스트 작성 오류 때문에 중간 assertion이 실패했다. 엔진은 중복 index를 제거하므로 clone으로 수정했다. [첫 시도 설명](artifacts/local-validation-run/ATTEMPT-NOTE.md)과 완료된 CLI 산출물은 보존했다. 최종 19/19는 수정 후 전체 재실행 결과다.

## 완료 범위와 미수행 항목

19개 검사가 기대한 관찰과 일치한다. 여기에는 **위험 동작을 재현했을 때 pass인 negative/risk 검사**가 포함된다. 앱의 수용 기준 19개가 통과했다는 뜻이 아니다.

| 수행 | 결과 |
| --- | --- |
| 실제 공개 PNG/WebP 측정, bbox·알파·발 밴드 | 수치 저장·페이지 값 대조 완료 |
| 실제 자산 구성 시트의 slice normalization | 체형 변화·가로 발 이동 재현 |
| 공통 s=1 연구용 배치 | 비율·알파 픽셀·바닥 유지 |
| 기존 import→curation→compose→PNG/Aseprite | 실제 실행·아틀라스/PNG bake 일치 |
| 원본 불변, 저장/로드, 실패 reimport | 해당 실험에서 확인 |
| 합성 overflow·발 heuristic 실패 | 위험 재현; 실제 거너 upstream 결함 판정 아님 |

미수행: 새 웹앱 UI 완주, 실제 provider 인증/생성/부분 재생성, paid call, raw 체크무늬 배경 제거 품질, canonical `extract` row 전체 파이프라인, 브라우저 preview와 bake의 픽셀 비교, 부분 실패·취소·SIGKILL 후 자동 복구, 해부학적 몸/발 분할, 팀 색 아웃라인, Phaser/Flame 실제 로더 실행. 연구용 prototype 배치와 임시 JSON 구성은 설계 검증 도구이며 제품 UI 구현이 아니다.
