# 프레임룸 웹 검증 결과

> 현재 브라우저 정책: ego만 사용합니다. `test:e2e`는 기존 탭의 읽기 전용 ego smoke로 변경됐으며 실행 방법은 [README](README.md#브라우저-smoke--ego-전용)를 따릅니다. 아래 Playwright/Chromium 실행 결과와 캡처는 정책 변경 전 historical 기록으로 보존하며 현재 명령의 검증 결과가 아닙니다. 이번 runner 변경은 구문검사만 수행했고 ego 연결·브라우저 실행·TaskSpace9 접근은 하지 않았습니다. ego smoke 런타임 판정은 **NOT_RUN**입니다.

2026-10-03 · 최종 검증: 16:36 KST 이후 · API 8765 / Vite 5173 / 실제 worker 연결

## 완료된 검증

- `npm install`: 성공. `npm audit`: 취약점 0건.
- `npm run build`: TypeScript 및 Vite 프로덕션 빌드 성공. `dist/` 생성.
- `npm test`: 9개 통과.
- `npm run test:e2e`: Playwright Chromium 실제 API 여정 2개 통과, 15.5초.

### 브라우저 여정 1

새 프로젝트 생성 직후 편집기 진입 → PNG 업로드 → 외형 기준 초안과 승인 → whole 추출 → 자동 발 후보 재계산 → 앵커 승인 → 동작 생성 → 같은 frame을 참조하는 독립 occurrence 복제 → 240ms 가변 시간 → 후보 승인 → 저장 ACK 및 선택 유지 → 동작 검수 승인 → bake bitmap preview → atlas/runtime/PNG/Aseprite/bundle 출력 → API 요청을 차단한 `/#viewer`에서 로컬 runtime+atlas 읽기 및 재생 → 320px reflow.

### 브라우저 여정 2

다른 클라이언트의 저장을 실제 API로 발생 → 409 로컬 초안 유지 → 최신 버전에 명시적 재적용 → 서버의 별도 캐릭터 이름 변경 보존 → 숫자 0 입력 차단 및 180ms 유효 입력 → undo/redo → occurrence 픽셀 보정 저장 → 백업 파일 다운로드 → 새 프로젝트로 복원 및 열기 → Aseprite metadata 영역 가져오기 → 영역 병합 및 되돌리기 → 미지원 JSON 오류 → 320px 편집 화면 가로 넘침 없음.

### 단위 회귀

- 반복 슬롯 독립 ID/시간, 원본 snapshot 불변
- 저장 ACK에서 생성 ID를 후속 명령에 치환
- 마지막 슬롯 제거 후 빈 타임라인 보존
- 그룹 정렬 변경의 앵커 승인 무효화 및 무관 동작 승인 보존
- 기본 FPS 변경 시 직접 지정한 duration 보존
- 80/120/200ms 누적 시간 경계, 반복, 단발 마지막 유지
- 미지원 runtime schema 거부
- 실제 셀 중심 pivot: 128×96 → (64,48)
- 후보 검수 변경은 그 프레임을 참조하는 동작만 검수 무효화

## 산출물

- `dist/`: 정적 웹 빌드
- `test-results/editor.png`: 편집기 전체 화면
- `test-results/export.png`: 확정 출력 미리보기와 다운로드
- `test-results/mobile.png`: 320px 화면
- `tests/draft.test.ts`: 단위 회귀 / `tests/journey.e2e.ts`: 실행 비활성화된 historical 검증

## 범위

이 구현자는 `apps/web/`만 직접 수정했으며 commit/push를 수행하지 않았습니다. 실제 provider 생성 호출을 중복 실행하지 않았습니다. 부모 통합 검증자가 보고한 Codex 실제 생성 성공 및 실제 생성물 최종 출력 검증은 부모의 통합 증거에 속합니다. 이 문서의 UI E2E는 실제 PNG/API/worker 기반이며 mock provider 성공으로 대체하지 않았습니다. 전체 제품의 모든 수용 테스트 완료를 뜻하지 않습니다.

최종 브라우저 테스트는 종료됐으며 API/worker 재시작을 위해 대기 중인 클라이언트 작업은 없습니다.

## TEST33 보강 (16:45 KST 이후)

- `CandidateReview.tsx`: 승인 기준 선택 및 현재 후보 나란히 비교, 맞춤/1:1/확대, 거절 사유 필수 입력, `review=rejected` + `reason` 초안 적용, 저장한 `reviewReason` 다시 표시.
- 거절된 후보의 출력 gate에 저장된 사유 표시. 후보 숨김은 거절 사유를 지우지 않음.
- `FinishSteps.tsx`: 출력 응답 errors 또는 연결된 job 오류를 카드 안에 표시. 필요하면 `jobId`로 상세 조회·재조회.
- `npm run build` 통과, `npm test` 11개 통과, 기존 실제 API E2E 2개 재통과(15.6초).
- TEST33 전용 E2E를 추가했으나 당시 실행 API가 이전 스키마이므로 rejected 저장·재열기의 새 브라우저 시험은 미실행. 당시 제안했던 Playwright 재실행 명령은 폐기했다. TEST33 전체 UI 여정은 별도 ego 검증이 필요하며 현재 smoke에는 포함하지 않는다. 기존 API 테스트 10개 통과는 부모 통합 증거다.
- 상위 편집 컴포넌트 훅 순서 변경 없음. HMR 강제 재로드 불필요. API/worker를 이 구현자 쪽에서 재시작하지 않음.

## 자료 출처 라벨 보강 (16:58 KST)

- AssetsStep은 `provenance.kind`를 기준으로 `AI 생성 원본 · Codex`, `배경 제거 결과`, `추출 프레임`, `가져온 원본`을 표시하며 자료 역할도 한국어로 표시한다.
- `parentAssetId`를 asset ID로 재귀 추적하여 실제 provider 원본에서 나온 결과에 `AI 생성에서 파생`을 표시한다. 같은 파일명의 자료도 합치지 않는다. 누락된 부모·순환 관계는 안전하게 중단한다.
- robot-idle/robot-sheet 등 파일명 또는 이미지 모양으로 합성 여부를 추정하지 않는다.
- `npm run build` 통과, `npm test` 19개 통과(출처 회귀 8개 포함).
- 사용자 요청대로 브라우저/Chrome/Chromium은 실행하지 않았으며 브라우저 시험과 API·worker 재시작도 수행하지 않았다.
