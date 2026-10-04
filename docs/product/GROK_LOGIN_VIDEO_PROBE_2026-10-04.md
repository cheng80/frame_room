# Grok 로그인 영상 제작 실측

2026-10-04 KST. **실제 Grok 영상 1건으로 기준 그림 → 영상 → 투명 프레임 → 반복 구간 → 스프라이트 시트·GIF를 확인했다.** 웹 편집기의 영상 생성 버튼·작업 복구·백업까지 구현한 결과는 아니다.

## 인증과 사용 범위

- Grok Build 재로그인 후 `grok models`가 정상 응답했다.
- 프로젝트 엔진의 `grok-login` 인증으로 `GET https://api.x.ai/v1/models`가 HTTP 200을 반환했다. 영상 모델 `grok-imagine-video`, `grok-imagine-video-1.5`, `grok-imagine-video-1.5-lite`가 포함됐다.
- `grok-imagine-video-1.5`에 **영상 생성 POST 정확히 1회**, 3초·480p·무음으로 요청했다. HTTP 200으로 접수됐고 상태 조회 5회 후 약 20.10초에 MP4를 받았다.
- `XAI_API_KEY` 전환이나 추가 이미지 생성·방향 판정 모델 호출·재생성은 없었다. Spritegen 웹사이트의 500크레딧은 사용하지 않았다. Grok 계정의 정확한 잔여량·차감량은 확인하지 않았다.
- 토큰은 결과물에 기록하지 않았다. 요청 ID는 접수 직후 체크포인트에 저장했고, 같은 실험 스크립트를 재실행하면 추가 POST를 거부한다. 앱 전체의 복구 기능은 별도 구현 대상이다.

## 입력과 원본

입력은 앞선 GPT 제작 실험에서 저장한 [idle-base.png](../../.data/experiments/original-sprite-gen-20261004/idle-base.png)다. 64×128 이미지의 알파 영역 `[7,24,53,118]`을 4배 nearest-neighbor로 확대하고 512×512 마젠타 캔버스에 합성했다. 이 준비 이미지는 기존 그림의 로컬 변환이며 새 AI 생성물로 세지 않는다.

- 입력 SHA-256: `38f4e9daa2d28b6b75bcb61f377038823f4afaafa045844fd062bfb284c5ec7c`
- 원본 MP4 SHA-256: `65754461cb508c0582224a82097c91493c52f93b10db0e69f5b74cc8819acf93`
- 요청 ID: `1b4c3994-8177-9a31-8f02-ee0f0ee4abd2`
- 요청은 480p였으나 실제 파일은 **544×544, 24fps, 73프레임, 3.041667초**다. 작업 등록 시 요청값 대신 실제 미디어 정보를 기록해야 한다.

## 후처리와 검증

프로젝트 전용 엔진의 `video.frames`를 사용해 마젠타 배경을 제거했다. 참조 그림을 바탕으로 spill 처리를 정했고 `decontam=auto`를 적용했다. 원본 프레임과 투명 프레임은 각각 보존했다. 검사에서 위·좌·우 가장자리 접촉은 없었다.

`video.loop.detect_cycle`이 0부터 센 **41~68번, 28프레임**을 선택했다. 반복성 점수 `0.7004`는 기준 `0.15`를, 연결 경계의 변화 비율 `0.98945`는 상한 `2.0`을 통과했다. 이 수치는 다리의 의미나 접지를 판정하지 않는다.

선택 프레임에는 보간이나 추가 생성을 적용하지 않았다. `build_strip`으로 첫 프레임의 몸 높이를 기준 삼아 공통 배율을 적용한 뒤 64×128 셀에 배치했다. 목표 몸 높이는 이전 Idle과 같은 94px다. 각 셀의 원본 프레임 번호·시각·재생 시간을 별도 JSON에 보존했다.

- PNG 시트의 28개 셀이 개별 PNG와 바이트 단위로 일치함을 확인했다.
- GIF를 다시 읽어 28프레임·무한 반복·모서리 투명을 확인했다.
- 원본 반복 구간은 1,166.667ms다. GIF의 10ms 단위 반올림을 분산해 1,170ms로 저장했다.
- 같은 크기의 정지 프레임 비교에서 머리·목도리·어깨 갑옷·옷·장화·검과 전반적인 스타일은 유지됐다. 몸의 시점과 검 각도는 움직이며 변한다. 실제 보행의 자연스러움·접지·게임 채택 여부는 아직 승인하지 않았다.
- 이번 실험은 엔진의 주기 검출·시트 처리와 GIF 인코더를 직접 조합했다. `img2webp`가 없어 WebP 묶음 출력은 실행하지 않았으며 시스템 의존성을 설치하지 않았다.

## 결과 파일

- [확대 GIF 미리보기](../../.data/experiments/grok-walk-probe-20261004/walk-preview-3x.gif)
- [64×128 셀 GIF](../../.data/experiments/grok-walk-probe-20261004/walk.gif)
- [28프레임 PNG 시트](../../.data/experiments/grok-walk-probe-20261004/walk.sheet.png)
- [실제 Grok 원본 MP4](../../.data/experiments/grok-walk-probe-20261004/walk.mp4)
- [Idle과 동일 크기 비교](../../.data/experiments/grok-walk-probe-20261004/cycle-contact-sheet.png)
- [요청 설정·프롬프트](../../.data/experiments/grok-walk-probe-20261004/request.json)
- [생성 결과 기록](../../.data/experiments/grok-walk-probe-20261004/video.report.json)
- [후처리·검증·프레임 계보](../../.data/experiments/grok-walk-probe-20261004/probe.report.json)

결과와 실험 스크립트는 Git에서 제외된 `.data/experiments/grok-walk-probe-20261004/`에 보존된다. 원본·공용 스킬·기존 앱 구현은 변경하지 않았다.

## 다음 구현 단위

사용자의 추가 로그인 설정은 현재 필요 없다. [핵심 연결 설계](AI_SPRITE_EDITOR_IMPLEMENTATION_2026-10-04.md)에 따라 앱의 영상 작업 제출·접수 ID 저장·조회 재개·MP4 보존·프레임 후보 등록을 연결해야 한다. 후처리 개발과 검수는 이번에 받은 MP4를 재사용할 수 있다. 웹 UI·편집·게임 출력·백업 복원은 이번 실측의 검증 범위에 포함되지 않는다.
