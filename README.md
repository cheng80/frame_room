# 프레임룸 · 캐릭터 스프라이트 에디터

GitHub 프로젝트: [frame_room](https://github.com/cheng80/frame_room) · 공개 저장소

React + Vite + TypeScript, FastAPI, SQLite, 독립 Python worker로 실행하는 로컬 제작 도구입니다. 이미지를 가져오거나 저장한 캐릭터 기준으로 생성한 뒤, 알파·프레임·공통 배율·발 앵커·순서·시간·픽셀을 편집해 게임용 파일로 내보냅니다.

다른 경로·기기에서 이어서 작업할 때는 **[작업 재개 핸드오프](docs/product/HANDOFF.md)**부터 확인하세요. 현재 코드는 `git status`와 `git log`로 확인하며, 사용자 프로젝트 폴더는 Git과 별도로 옮깁니다.

## 가이드 영상

HTML 사용 설명서의 본문과 화면 캡처 12장은 2026-10-13 현재 6탭 UI로 갱신했습니다([갱신 기록](docs/product/GUIDE_REFRESH_2026-10-13.md)). 영상 자료는 이전 화면입니다. 현재 제작 흐름은 아래 여섯 단계와 [실행 계약](docs/product/SIX_STEP_WORKFLOW.md)을 따릅니다.

- [퀵스타트](https://youtu.be/yZgaGipvkkg)
- [전체 가이드](https://youtu.be/MCCSBxyghXQ)

## 실행

```sh
scripts/setup.sh       # 최초 설치: Python 3.12 전용 venv, 고정 의존성, 웹·설명서 빌드
scripts/start.sh       # http://127.0.0.1:8765
```

macOS에서는 **`프레임룸 실행.command`**를 더블 클릭해도 됩니다. 실행 시 `apps/web/node_modules`와 필수 npm 의존성을 확인하고, 누락되었거나 불완전하면 `npm install --include=dev` 후 웹 앱을 빌드합니다. 웹 빌드가 없을 때도 자동으로 빌드하며, Python 환경이 없거나 필수 패키지를 불러올 수 없으면 프로젝트 전용 환경을 준비합니다. 설치·검증·빌드가 성공한 뒤 앱을 실행합니다. Node.js/npm과 [uv](https://docs.astral.sh/uv/getting-started/installation/)는 미리 설치해야 합니다(uv는 Python 환경 준비 시 필요). 서버·worker가 실행되는 터미널을 닫으면 앱이 종료됩니다. 생성 결과가 불명확한 중단 작업은 재시작 때 자동 재전송하지 않습니다.

영상 처리에는 PATH에 `ffmpeg`·`ffprobe`가 필요하며 `setup.sh`는 이를 설치하지 않습니다. 새 생성에 필요한 Codex/Grok CLI 로그인과 선택 기능 RIFE도 기기별로 준비합니다. 전체 실행은 macOS에서 검증했습니다. 설치·이전 절차와 다른 OS의 제한은 핸드오프를 참고하세요.

개발: `scripts/dev.sh` → [http://127.0.0.1:5173](http://127.0.0.1:5173). 서버는 loopback에만 바인딩합니다. 각 프로젝트는 기본 `.data/projects/<이름>--<ID>/` 또는 지정한 폴더에 저장됩니다. `project.sqlite3`·원본·영상·작업·출력물이 모두 들어 있으므로 폴더 전체를 복사해 다시 열 수 있습니다. 공용 스킬 설치본에 런타임 의존하지 않습니다.

## 사용 흐름

1. **자료 준비**: 프로젝트를 만들고 PNG/WebP를 가져오거나 자료 이미지를 생성합니다. 원본은 보관합니다.
2. **캐릭터 기준**: 외형·스타일·자세 참조와 고정 특징을 정해 저장합니다. 별도 수동 승인은 필요하지 않습니다.
3. **동작 만들기**: 저장 기준으로 이미지·영상을 명시적으로 생성하거나 기존 이미지·영상에서 후보를 추출합니다. 필요한 배경 정리도 이 단계에서 수행합니다.
4. **프레임 편집**: 후보를 동작에 추가하고 순서·FPS/개별 시간·변형·픽셀을 편집합니다. 크기·발 정렬에서 공통 배율·출력 셀·접지 또는 공중 root 앵커를 맞춘 뒤 저장합니다.
5. **결과 확인**: 현재 동작을 즉시 재생하고 저장 버전의 자동 검사를 실행합니다. 수정이 필요하면 기준·동작 생성·프레임 편집·정렬로 돌아갑니다. 확정 미리보기는 최종 출력 픽셀을 확인하는 선택 작업입니다.
6. **내보내기**: 출력 설정에서 자동 저장 폴더를 확인하고 게임용 파일을 만듭니다. 출력 이력에서 완료 시각·저장 위치·최종 결과·다운로드를 확인합니다. 독립 출력 뷰어는 `runtime.json`과 `atlas.png`로 재생합니다.

상단 탭과 하단 현재 단계 표시는 실제 자료·저장·검사·출력 상태로 계산합니다. 탭은 자유롭게 이동할 수 있고, `다음`은 준비 조건을 만족하면 활성화됩니다. 탭 방문만으로 완료 처리하거나 새 생성을 요청하지 않습니다.

저장 충돌 시 초안을 유지하고 서버 버전과 비교해 다시 적용할 수 있습니다. 이력 복원은 새 revision을 만들며, 백업 복원은 새 프로젝트 ID를 만듭니다. 원본과 이전 출력은 덮어쓰지 않습니다.

**영상으로 동작 만들기**에서는 Grok Build 로그인으로 Pro/Lite 영상을 생성하거나 MP4를 가져옵니다. 기존 영상은 추가 생성 없이 구간·색 번짐·GIF/RGBA 마무리·선택적 RIFE 보정·주기 맞춤을 다시 적용할 수 있습니다. 방향별 기준 그림 설정과 최대 16건 묶음 접수도 지원합니다. [영상 사용법](apps/web/README.md#영상으로-동작-만들기) · [영상 계약](packages/contracts/VIDEO.md).

## 프로젝트 폴더 관리

- 새 프로젝트에서 저장할 부모 폴더를 선택하거나 경로를 입력합니다.
- **폴더 위치**는 그 프로젝트의 폴더를 엽니다. `project.json`, `project.sqlite3`, `assets/`, `videos/`, `jobs/`, `outputs/`를 함께 보관하세요.
- 이동·이름 변경은 저장하고 진행 작업을 마친 뒤 폴더를 옮기고 **프로젝트 폴더 열기**로 새 위치를 엽니다. **삭제**는 프로젝트 폴더까지 지우므로 이동에 사용하지 않습니다.
- **없는 폴더 정리**는 대상 이름·경로를 먼저 보여주고, 사라진 폴더의 등록·연관 기록만 공용 SQLite에서 정리합니다. 외장 디스크가 분리된 경우도 목록에 나타나므로 위치를 확인하세요.
- 기존 프로젝트는 최초 실행 시 개별 폴더로 복사됩니다. 이전 공용 원본 파일은 보존합니다. ZIP 백업은 현재 편집 상태를 옮기는 별도 기능이며, 모든 저장 이력·출력까지 보관하려면 프로젝트 폴더 전체를 복사하세요.

[저장 계약](packages/contracts/PROJECT_FOLDERS.md) · [실제 전환·검증 결과](docs/product/PROJECT_FOLDERS_2026-10-05.md).

## 출력

- `atlas.png`: 확정 셀 아틀라스
- `pngs.zip`: 아틀라스에서 추출한 순서별 PNG와 sequence manifest
- `runtime.json`: occurrence 순서·가변 시간·반복·앵커·lineage·hash
- `aseprite.json`: Aseprite 호환 JSON (`.aseprite` 편집 원본 아님). 반복/앵커 정책은 runtime 동반
- `qa.json`: 알파·잘림·구조·전체 RGBA 일치 검사와 기존 검토 진단
- `animations.zip`, `animation-manifest.json`: 같은 bake의 GIF·WebP·가로/격자 PNG와 시간·색상 제한 기록
- `bundle.zip`: 최종 출력 묶음

출력 원본은 프로젝트의 `outputs/<jobId>/<attemptId>/`에 자동 저장됩니다. `프로젝트 폴더 열기`는 프로젝트 루트를 열며, 각 출력의 하위 경로는 이력에서 확인합니다. 출력 설정과 출력 이력은 별도 탭이며 요청 접수 후 이력 탭으로 이동합니다. 이력은 완료 기록 시각(미완료는 요청 시각) 최신순이고 최신 하나만 펼쳐 둡니다. 이전 항목도 제목·시각을 눌러 펼칠 수 있습니다. 같은 저장 버전을 여러 번 출력해도 별도 이력이 남고, 다운로드 사본의 위치는 브라우저 설정을 따릅니다.

빈 타임라인, 누락된 기준 연결, 명시적으로 제외한 후보, 비어 있는 알파, 셀 밖 픽셀, 누락·손상 원본, 오래된 정렬·저장 revision은 최종 출력을 차단합니다. `draft`/`pending` 승인 기록 자체는 차단 조건이 아니며 기존 기록은 보존합니다. 편집 canvas는 빠른 미리보기이며 최종 판정은 서버의 확정 bake를 사용합니다.

## 검증

```sh
engine/sprite-gen/.venv/bin/python -m pytest tests/integration -q
npm --prefix apps/web test
npm --prefix apps/web run build
```

[구현·검증 현황](docs/product/IMPLEMENTATION_STATUS.md)에 실제 실행 범위와 남은 제한을 기록합니다. 연구의 19개 관찰 검사, 앱 자동 회귀 수, [34개 제품 수용 기준](docs/product/ACCEPTANCE_TESTS.md)은 서로 다른 집계입니다. 실제 provider 호출과 모의 작업 시험도 구분합니다.

## 엔진·범위·자료

프로젝트 엔진은 `engine/sprite-gen/`의 **v2.12.1 기반 포크**에 공개 v2.19 영상 보완을 선별 반영한 것입니다. 정확한 의존성 pin과 패치는 [engine-lock](engine/engine-lock.json), [변경 고지](engine/PATCHES.md)에 기록합니다. 원본 hash 목록, Apache-2.0 LICENSE·NOTICE를 보존하며 upstream으로 자동 전환하지 않습니다.

복잡한 배경의 자동 제거, 외형 일관성, 실제 생성의 native alpha는 보장하지 않습니다. Codex의 해상도·품질 지정/외부 취소·결과 조회는 미지원 상태를 표시합니다. 이미지 생성은 명시적 Codex 경로, 영상 생성은 명시적 Grok 로그인 경로를 쓰며 유료 API fallback은 활성화하지 않습니다. 로그인/과금 서비스·원격 협업·공개 배포와 별도 PXF/effect_editer 통합은 범위 밖입니다.

`tests/fixtures/robot-*.png`는 직접 만든 합성 CC0 시험 자료입니다. 공개 거너 이미지는 연구·로컬 회귀용이며 앱 기본 배포 에셋으로 포함하지 않습니다.

## Git 저장 범위

소스 코드·의존성 잠금 파일·합성 시험 자료·설명서용 이미지와 프로젝트 전용 엔진을 저장합니다. 엔진의 원본 360파일과 LICENSE·NOTICE는 무결성 검증을 위해 함께 보존합니다.

`.data/`, `artifacts/`, `output/`, `diagnostics/`, 연구 자료, `.env`·인증 정보, 설치 의존성·빌드·캐시는 `.gitignore`로 제외합니다. 2026-10-06 사용자 요청으로 로컬 조사·실험 자료와 전용 비교 스크립트·보고서를 삭제했습니다. 제품 명세·구현 기록과 프로젝트 데이터는 보존했습니다. 연구용 거너 원본에 의존하는 선택 회귀 검사 1건은 자료가 없어 건너뜁니다.

설명서 ZIP은 `scripts/setup.sh`에서 다시 만듭니다. 설명서를 수정한 뒤에는 `npm --prefix apps/web run build`와 `engine/sprite-gen/.venv/bin/python scripts/package-guide.py`로 재생성합니다. 모든 프로젝트 이력·리소스는 프로젝트 폴더 전체로 별도 보관하세요. 앱의 백업 ZIP은 현재 상태를 새 ID로 복원하는 용도입니다.

- [최종 제품 문서](docs/product/README.md) · [핸드오프 원문](docs/product/HANDOFF.md)
- [사용자 합의](docs/planning/USER_DECISIONS.md) · [조사→설계→구현 이력](docs/planning/DELIVERY_PLAN.md)

공용 엔진·다른 프로젝트는 변경하지 않습니다. 불필요한 검수 파일·로그·이전 공용 중복 파일은 사용자 요청으로 정리했으므로 과거 보고서의 로컬 증거 경로는 없을 수 있습니다. [보존·정리 범위](docs/product/HANDOFF.md#6-검증과-정리-상태)를 확인하세요. GitHub 공개 저장소에는 위 저장 범위만 포함합니다. 사용자 프로젝트·인증·로컬 생성 자료는 포함하지 않습니다.
