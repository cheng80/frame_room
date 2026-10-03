# 프레임룸 웹 편집기

React + Vite + TypeScript. API는 `/v1`, 개발 서버는 `127.0.0.1:5173`, API 프록시는 `127.0.0.1:8765`입니다.

```sh
cd apps/web
npm install
npm run dev
npm run build
npm test
```

## 브라우저 smoke — ego 전용

`npm run test:e2e`는 `scripts/ego-smoke.mjs`를 실행합니다. 설치된 macOS `ego-browser` CLI와 실행 중인 ego lite, 사용 허가된 기존 TaskSpace의 managed 탭, 실행 중인 앱/API/worker가 필요합니다. 브라우저·탭 생성, 이동, 종료, 설치, 다른 브라우저 fallback은 하지 않습니다. 기본 TaskSpace는 없으며 부모가 사용 중인 TaskSpace9도 자동 선택하지 않습니다.

아래 환경변수를 실제 허가된 기존 탭에 맞게 설정한 뒤 실행합니다. **다른 작업이 사용하는 TaskSpace에는 실행하지 마세요.**

```sh
# EGO_TASK_SPACE_ID: 허가된 기존 TaskSpace의 숫자 ID
# EGO_PAGE_LABEL: 해당 공간의 기존 managed 탭 라벨 (예: p1)
EGO_TASK_SPACE_ID="$AUTHORIZED_SPACE_ID" EGO_PAGE_LABEL="$AUTHORIZED_PAGE_LABEL" npm run test:e2e
```

- CLI는 `PATH`와 `~/.local/bin/ego-browser`에서 찾습니다. `EGO_BROWSER_BIN`으로 실행 파일 경로, `EGO_SERVER_NAME`으로 기존 named service를 지정할 수 있습니다.
- `SPRITE_TEST_URL`은 로컬 앱 origin이며 기본값은 `http://127.0.0.1:5173`입니다. 탭이 다른 origin이면 이동하지 않고 실패합니다.
- 앱 DOM 렌더링·화면의 서비스 연결 표시와 `GET /v1/health`의 API/worker/engine 상태만 읽습니다. provider 생성, 데이터 변경, 화면 캡처는 하지 않습니다. session token은 출력하지 않습니다.
- CLI/브라우저/탭이 없거나 연결되지 않으면 종료 코드 1로 명확히 실패합니다. 전체 연결 검사 제한은 20초이고 자동 재시도하지 않습니다. 성공은 `EGO_SMOKE_PASS`로 표시합니다.
- 기존 `tests/journey.e2e.ts`와 Playwright 라이브러리는 historical 자료로 보존합니다. `playwright.config.ts`는 직접 실행을 오류로 중단하며 Chromium 실행 경로와 설치 명령은 없습니다. `--grep`/`--project` 등 과거 옵션도 거부합니다.

브라우저 연결 없이 구문만 확인하려면 다음을 사용합니다.

```sh
node --check scripts/ego-smoke.mjs
node --check scripts/ego-smoke-page.mjs
```

빌드 결과물은 `dist/`, 과거 Playwright 캡처와 trace는 `test-results/`에 보존됩니다. 이 smoke는 전체 UI 여정·키보드·독립 뷰어·bitmap parity 검증을 대신하지 않습니다.

## 화면

- 프로젝트 생성·목록·복제, ZIP 백업·새 ID 복원, 저장 이력 복원
- PNG/WebP 업로드, 외형·스타일·자세 참조와 기준 승인
- 제공자 capability에 맞춘 생성 옵션과 단일 프레임 재생성 요청
- 배경 제거, whole/grid/components/regions 추출, Aseprite/runtime JSON 영역 가져오기, 수동 영역 병합·제외·되돌리기
- 공통 배율·셀·안전 여백, 몸 landmark 측정, 접지/공중 수동 앵커, 자동 발 후보 계산 및 명시적 초기화
- 후보 승인·숨김, 반복 occurrence·재정렬·복제·교체, 가변 시간, FPS, 이동·변형·펜·지우개, 로컬 undo/redo
- 편집 미리보기·배경·onion skin, 팀 테두리, 체크리스트 검수, 확정 bake·출력 다운로드
- 상태별 작업 센터, 취소 요청·실패 재시도, 외부 접수 불명 안내
- 저장 ACK, 409 비교·초안 재적용, 브라우저 초안 보관
- `/#viewer`: runtime.json+atlas.png를 서버와 프로젝트 DB 없이 읽는 독립 파일 뷰어

## 저장 규칙

편집은 명시적 저장 전 브라우저 초안입니다. 새 clip/occurrence ID는 API가 발급하므로 저장 시 순차 ACK에서 생성 ID를 찾아 후속 편집 명령을 치환합니다. 중간 저장 실패 시 성공한 명령은 기준 snapshot에 반영하고 남은 명령만 초안으로 보존합니다. 숫자 입력은 blur/Enter에서 범위를 확인한 뒤 반영합니다.

정렬·후보 변경은 해당 프레임을 참조하는 동작의 검수만 무효화하고, 테두리 변경은 모든 동작 검수를 무효화합니다. 관련 변경을 먼저 저장한 다음 수동 승인 탭에서 동작별 체크리스트를 확인하고 승인 명령을 별도로 저장합니다. 최종 내보내기의 authoritative 검증은 서버 bake/QA입니다. 빠른 편집 캔버스는 최종 bitmap과 구별하며 최종 미리보기는 서버 atlas bitmap을 사용합니다.

## 검증 범위

`tests/draft.test.ts`는 반복 occurrence 독립성, 빈 타임라인, ID 재매핑, FPS/가변시간, 검수 무효화 및 재생 시간 경계를 검증합니다. `tests/journey.e2e.ts`는 가져오기·export·독립 뷰어·충돌·백업 등을 다루던 historical Playwright 테스트이며 현재 실행 대상이 아닙니다. 현재 ego smoke 범위는 위 연결 검사에 한정됩니다. 실제 provider 성공 여부는 상위 통합 시험에서 별도로 기록해야 합니다.

## HTML 사용 설명서

- 퀵스타트: `/guide/` · 상세 설명서: `/guide/manual.html`
- 프로젝트 목록과 에디터의 `사용 설명서`에서 새 탭으로 엽니다.
- `public/guide/content.json`: 기능별 본문, FAQ, 단축키. `scripts/generate-guide.mjs`: 6단계 퀵스타트와 정적 HTML 생성.
- `public/guide/screens/`: 실제 에고 화면 9장. `media/`: 실제 예제 출력 atlas와 재생 좌표. 별도 API 호출 없이 설명서에서만 재생합니다.
- `npm run guide:build`는 HTML을 갱신하며 `npm run build`에도 포함됩니다. 이후 저장소 루트에서 `python3 scripts/package-guide.py`를 실행하면 오프라인 ZIP을 갱신합니다.
- `frame-room-guide.zip`을 풀고 `index.html` 또는 `manual.html`을 열면 서버 없이 본문·이미지·예제가 동작합니다. 에디터로 이동할 때만 로컬 앱이 필요합니다. 인쇄/PDF 버튼은 브라우저의 인쇄 기능을 사용합니다.
- 설명서 체크리스트는 현재 문서 세션에서만 유지하며 프로젝트 승인과 연결하지 않습니다. ‘수동 승인됨’은 승인 버튼으로 기록된 상태이고, 자동 품질 판정이나 자동 후보 추천을 뜻하지 않습니다.
