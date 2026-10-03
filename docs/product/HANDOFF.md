# 새 구현 세션 핸드오프

2026-10-03 KST · 사용자가 새 세션 생성 및 실제 제작 시작을 요청함

## 목적과 작업 위치

`/Users/cheng80/Desktop/Current_works/copy_spritegen`에서 **게임 캐릭터 스프라이트 에디터**를 실제 구현한다. `sprite-gen`을 프로젝트 내부에 포크하고 React+Vite UI, FastAPI, SQLite, 독립 Python worker를 연결한다. 큐레이션 이전의 기준 자료·생성 설정·생성·배경 제거·추출을 포함하여 끝까지 UI에서 작업할 수 있어야 한다.

이 문서는 구현 시작 지시다. 계획만 다시 제시하거나 문서를 반복 조사하는 데서 끝내지 말고 승인된 로컬 구현·실행·검증·발견한 문제 수정을 진행한다. 최종 제품 요구는 PRD R01–R12 전체다. 연구 결과가 앱 구현 완료를 의미하지 않는다.

## 먼저 읽을 파일

모든 상대 경로의 기준은 위 작업 루트다.

1. `docs/product/README.md`, `PRD.md` — 전체 요구와 완료 경계.
2. `UX_DESIGN.md`, `ARCHITECTURE.md` — 실제 화면과 구성.
3. `DATA_API_SPEC.md` — 최신 데이터·API·정렬·timing 정본.
4. `IMPLEMENTATION_PLAN.md`, `ACCEPTANCE_TESTS.md`, `DECISIONS.md` — 단계·검증·이유.
5. `research/hero-inc/2026-10-03-implementation-design/README.md`, `baseline.json`, `engine-audit.md`, `validation.md` — 코드 감사와 실험 증거.
6. 필요할 때 같은 연구 폴더의 `cli-api-matrix.md`, `data-contract.md`, `sources.md`, `tests/validate_local_engine.py`를 읽는다. 연구 제안과 최종 제품 문서가 다르면 최신 제품 결정이 기준이다.

2–4항의 파일도 모두 `docs/product/` 아래에 있다. 이전 대화의 사용자 합의는 `docs/planning/USER_DECISIONS.md`에 보존했다.

## 현재 완료된 것

- 공개 제작 노트·Threads·YouTube 조사 및 원문 맥락 대조.
- 엔진 설치본2.12.1의360개 릴리스 파일과 공개 commit `b058341f7543f3adcbea227bd4e6b7587895b1bc` 일치 확인.
- 실제 공개 정렬 이미지를 이용한 import→curation→compose→출력 실험, 합성 무기/발 반례 등19개 관찰 검사. 위험 재현도 포함하며 제품 테스트19개 통과가 아니다.
- PRD·화면·기술·데이터/API·구현·수용·결정 문서 작성.

## 아직 하지 않은 것

앱 구현, 프로젝트 전용 포크 생성, 실제 provider 이미지 생성, 제품 브라우저 완주, 실제 raw 체크무늬 제거 품질 검증, 취소/강제종료 복구, 제품 outline, 독립 앱 뷰어 검증은 미완료다. 원격 저장소·공개 배포도 생성하지 않았다. 과거 연구 폴더에 있는 HTML 비교물/테스트 스크립트는 앱이 아니다.

## 구현 핵심과 금지되는 오해

- UI는 프로젝트→참조 승인→동작/프롬프트/provider 설정→생성/가져오기→알파/추출→공통 배율/발→후보/순서/시간→검수→출력으로 연결한다. CLI 또는 JSON 직접 편집이 필수인 단계가 남으면 완주 실패다.
- **pre-fit 원본 crop을 확보한다.** `slice-sheet`는 실제 웅크림320→471px를 재현했으므로 애니메이션 기본 경로에서 사용하지 않는다. 기존 `extract` fit도 그대로 믿지 않는다.
- bbox 체고와 몸 landmark를 구분한다. 자동 발은 후보이며 수동/공중 앵커와 반올림 잔차를 기록한다. 단일 프레임 숨은 확대/축소를 금지한다.
- 원본 assets는 불변이다. engine working base나 curation 편집은 사본/파생 revision에서 처리한다.
- occurrence로 `[A,B,A,C]`를 표현한다. 빈 timeline은 빈 상태이며 출력 차단. 단순 selected 중복이나 `selected:[]` 기본값에 맡기지 않는다.
- 가변 duration은 최종 MVP 필수다. 지원하지 않는 request 필드를 넣는 것으로 완료 처리하지 말고 composer/preview/export 계약을 함께 구현한다.
- **최종 preview·atlas·개별 PNG는 같은 고정 bake**에서 만든다. save ACK 이전 export 금지, clipping gate, 원자적 결과 묶음, source revisions/hash를 검사한다.
- 실제 provider capabilities와 성공 증거를 남긴다. `login-ready`와 mock 결과는 실제 생성 완료가 아니다. 기존 허용된 계정/구독 경로로 필요한 검증을 진행하며 임의 유료 API fallback을 쓰지 않는다. 인증/사용량 실패 호출은 반복하지 않는다.
- provider와 생성 동시성1을 명시하고 engine의 Codex timeout 내부 재시도도 통제한다. 외부 job ledger가 있어도 내부 호출이 재전송되면 중복 방지 계약은 실패다.

## 첫 구현과 계속할 작업

현재 파일/Git 상태부터 확인하고 사용자 변경을 보존한다. M0 환경/소스 pin을 만든 뒤 M1의 프로젝트 저장·실제 업로드·재열기를 먼저 end-to-end로 구현한다. M2 공통 정렬과 M3 편집/출력을 연결하고, M4/M5 생성 앞단·worker·실제 생성까지 계속한다. 첫 화면이나 기존 PNG 가져오기 경로만으로 전체 제작 완료를 선언하지 않는다.

독립 하위 작업은 병렬 위임해도 된다. `IMPLEMENTATION_PLAN.md`의 쓰기 범위를 나누고 계약/루트 설정은 주 세션이 통합한다. 완료되는 코드를 실제 리뷰·실행한다. 타 사용자 채팅에 임의로 메시지를 보내지 않는다.

## 검증·실행 계약

`scripts/setup.sh`, `scripts/dev.sh`, `scripts/start.sh`, package build/test scripts는 **만들어야 할 진입점**이며 현재 존재하거나 성공했다고 가정하지 않는다. 구현 후 실제 명령으로 README를 갱신한다. Python/엔진은 프로젝트 전용 venv를 사용한다. UI는 실제 브라우저에서 기존 PNG 여정과 실제 생성 여정을 각각 확인한다.

연구 가설을 다시 확인할 필요가 있을 때만 아래 기존 스크립트를 새 out-dir에 실행한다. 이것은 제품 수용 테스트의 대체가 아니다.

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/cheng80/.codex/skills/sprite-gen/.venv/bin/python \
  research/hero-inc/2026-10-03-implementation-design/tests/validate_local_engine.py \
  --out-dir research/hero-inc/2026-10-03-implementation-design/artifacts/handoff-recheck
```

공용 경로로 앱을 실행하지 않는다. 위 읽기 전용 연구 재현 외 제품 테스트와 실행은 새 engine 사본을 사용한다. 기존 결과가 있으면 덮지 말고 별도 output을 쓴다.

제품 수용 테스트는 처음 모두 NOT_RUN이다. 실제 실행한 테스트만 결과·명령·artifact를 기록해 PASS/FAIL로 바꾼다. mock/실제 provider/실제 소재/합성 소재를 구분한다. 처음부터 다시 연구할 필요는 없지만 핵심 회귀는 포크 코드에서 실행한다.

## 작업 경계와 최종 보고

공용 `/Users/cheng80/.codex/skills/sprite-gen`, 별도 `/Users/cheng80/Desktop/Current_works/effect_editer`와 PXF 프로젝트, 기존 연구 증거는 수정하지 않는다. 공개 거너 fixture는 로컬 연구용이며 제품 기본 에셋은 자체/사용 허가 소재로 구성한다. 코드 라이선스·고지를 보존한다. 명시 요청 없는 commit/push/PR/merge/공개 배포를 수행하지 않는다.

일상적인 설계와 되돌릴 수 있는 로컬 작업은 자율 진행한다. 실제 계정 접근·중요 입력이 없을 때만 해결에 필요한 구체 정보를 보고하고 가능한 독립 구현을 계속한다. 같은 승인을 반복 요청하지 않는다.

최종 보고는 한국어로 실행 URL/실행법, 구현된 흐름, 실제 출력 파일, 테스트 결과, 실제 provider 성공 여부와 남은 제한을 먼저 제시한다. 로컬 앱이 실행되지 않거나 필수 경로가 미완성인데 전체 완료라고 말하지 않는다.
