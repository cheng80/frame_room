# 작업 재개 핸드오프

기록 기준: **2026-10-06 KST**. 프레임룸은 구현·실행 가능한 로컬 스프라이트 에디터다. 프로젝트 폴더/SQLite 관리에 이어 공개 sprite-gen v2.34의 품질 기술과 게임용 걷기 기본 8장을 반영했다. [최신 기술 적용](LATEST_SKILL_UPGRADE_2026-10-06.md), [동작 보완·검사 연결](CLIP_TOOLS_2026-10-06.md)의 실제 검증 범위를 함께 읽는다. 다른 경로나 기기에서 작업을 이어갈 때 이 문서부터 읽는다.

### 2026-10-06 자료 정리

사용자 요청으로 `.data/experiments/`, `.data/research/`, `research/`, 전용 `scripts/skill_compare/`·`scripts/walk_experiment/`, 비교 보고서 7개와 `docs/product/comparisons/`를 삭제했다. 이전 브라우저/pytest 캐시, 실행 로그·빈 작업 폴더·사용 중이지 않은 잠금 파일도 정리했다. 총 4,694파일, 약 404.5 MiB이며 이 중 `.data` 정리는 약 350.2 MiB다.

현재 등록된 프로젝트는 **검사 · 걷기 8·12·24장 + Idle**, **여자 해적 · 걷기 8장 · 목도리 흔들림** 두 개다. 프로젝트 전체 파일·149개 이미지·2개 영상·저장 이력, 공용 SQLite, RIFE, 엔진 원본·해시·LICENSE/NOTICE를 보존했다. `.data/jobs/`·`.data/uploads/`는 완료된 복원 작업의 DB 참조가 있어 유지했다.

과거 실험 경로와 삭제한 비교 스크립트는 재개 명령으로 사용하지 않는다. 아래 자료·검증 기록 중 이 경로를 가리키는 항목은 당시의 이력이다. `engine-lock.json`의 연구용 archive 경로도 원본 출처 기록이며 현재 로컬 파일이 아니다. 실행 무결성은 보존한 엔진 소스와 해시 목록으로 검사한다. 연구 원본에 의존하는 선택 회귀 1건은 skip 처리된다.

정리 후 확인: 보존 파일 237개 SHA-256 일치, SQLite 3개 integrity/foreign-key 검사 통과, 현재 이미지 149개·영상 2개 존재/해시 확인, `scripts/doctor.py`의 엔진 원본/승인 패치 407파일 무결성 통과. 삭제된 자료로 향하는 문서 링크와 JSON도 확인했다. `.data`의 남은 파일 크기 합계는 약 67.2 MiB다. 앱 전체 회귀·브라우저 실행은 이번 정리에서 수행하지 않았다.

## 1. 먼저 실제 Git 상태 확인

**특정 커밋을 ‘최신’으로 고정하지 않는다.** 아래 명령의 현재 결과로 변경·브랜치·이력을 확인한다. 이 문서의 날짜와 테스트 수는 기록 당시의 관찰이며 이후 변경보다 우선하지 않는다.

```sh
git status --short --branch
git log -8 --oneline --decorate
git diff --stat
git diff --cached --stat
git remote -v
git worktree list
# 원격과 비교할 때
git fetch origin
git rev-list --left-right --count HEAD...@{upstream}
```

upstream이 없는 브랜치에서는 마지막 명령에 비교할 원격 브랜치를 직접 지정한다. 미반영 사용자 변경을 먼저 보존한다. 이 문서를 맞추려고 reset/clean/강제 push하지 않는다. 새 작업의 커밋·push·PR·merge·배포는 그때 사용자가 요청한 범위에서 한다.

저장소: `https://github.com/cheng80/frame_room.git` (공개). 2026-10-06 `copy_spritegen`에서 `frame_room`으로 이름을 변경하고 로컬 `origin`을 새 주소에 연결했다. 기록 당시 작업 브랜치는 `main`이다. 원래 경로는 `/Users/cheng80/Desktop/Current_works/copy_spritegen`이지만 실행에 같은 절대 경로가 필요하지 않다. 이하 명령은 **복제한 저장소 루트** 기준이다.

## 2. 새 환경에서 실행

필수: Git, Node.js/npm, uv. 영상에는 PATH에서 실행 가능한 `ffmpeg`와 `ffprobe`도 필요하다. `setup.sh`는 Python 3.12 venv와 잠금 의존성·웹·설명서를 설치/빌드하지만 ffmpeg, Codex/Grok CLI, 계정 로그인, RIFE는 설치하지 않는다. `doctor.py` 성공만으로 이 외부 도구가 준비됐다고 판단하지 않는다.

```sh
scripts/setup.sh
command -v ffmpeg
command -v ffprobe
SPRITE_OPEN_BROWSER=0 scripts/start.sh
# 브라우저에서 http://127.0.0.1:8765 열기
```

macOS에서는 `프레임룸 실행.command`도 사용할 수 있다. 실제 전체 실행 검증은 macOS에서 했다. Windows/Linux의 전체 설치·런처 동작은 검증하지 않았으며, 특히 Windows 네이티브 실행은 bash/fcntl 기반 런처의 추가 대응이 필요하다.

- 개발: `scripts/dev.sh` → `http://127.0.0.1:5173`, API/worker는 8765. `start.sh`와 중복 실행하지 않는다.
- Python은 `engine/sprite-gen/.venv/bin/python`을 쓴다. 다른 기기의 venv나 `node_modules`를 복사하지 말고 설치한다. 공용 sprite-gen 스킬에 의존하거나 그 파일을 수정하지 않는다.
- 기본 데이터는 `.data/`. 바꾸려면 시작 전에 `SPRITE_DATA_DIR`을 설정한다. `.env` 자동 로드는 하지 않으므로 필요한 환경변수는 명시적으로 export한다.
- 기존 데이터 편집·MP4 재처리는 생성 로그인이 필요 없다. 새 이미지 생성은 Codex CLI 로그인과 실제 계정 사용 가능 여부가 필요하다. 새 영상은 Grok Build CLI의 `grok login`을 사용한다. 기기마다 직접 로그인하며 인증 파일을 Git이나 프로젝트 폴더로 옮기지 않는다.
- 로그인 준비와 실제 생성 성공/잔여량은 다르다. Grok 영상 adapter는 **Grok 로그인만 사용**하고 API 키로 전환하지 않는다. 인증/사용량 실패를 반복 호출하지 않는다.

RIFE는 선택 기능이며 기본 보정은 꺼져 있다. 필요할 때만 해당 기기용 실행 파일/모델을 설치한다.

```sh
engine/sprite-gen/.venv/bin/python -m sprite_gen.video.rife_install install --dir "$PWD/.data/tools/rife"
```

adapter는 저장소의 `.data/tools/rife`를 우선 탐색한다(`SPRITE_DATA_DIR`과 별개). 이 파일은 Git에 없다. RIFE 설치·보간은 AI 영상 생성 호출과 별개다.

## 3. 프로젝트 데이터 옮기기

**Git clone만으로 사용자 프로젝트·실제 생성 원본은 복원되지 않는다.** 저장·진행 작업 완료와 ‘폴더 저장 보류’ 해제를 확인한 뒤 다음 폴더 전체를 별도로 복사한다.

```text
<프로젝트 이름>--<projectId>/
  project.json
  project.sqlite3
  assets/
  videos/
  jobs/
  outputs/
```

기본 위치는 `.data/projects/`, 사용자가 지정한 외부 부모 폴더도 가능하다. 새 앱에서 **프로젝트 폴더 열기**로 등록하면 동일 ID·현재 상태·저장 이력·원본·영상·작업·출력이 복원된다. 경로는 폴더 기준 상대 경로이며 원본 파일을 실제 복사한다.

- 공용 `.data/app.sqlite3`는 등록/실행 인덱스·캐시다. 정상 저장된 프로젝트를 옮길 때 함께 복사할 필요가 없다. **저장 보류 중에는 공용 DB에만 새 변경이 있을 수 있으므로 이동·삭제하지 말고 보류부터 해결한다.**
- **목록에서 제거**는 등록과 해당 브라우저 초안을 지우며 프로젝트 폴더를 삭제하지 않는다. 미저장 초안은 먼저 저장한다.
- **없는 폴더 정리**는 사라진 루트 폴더의 공용 SQLite 기록만 정리한다. 실행 전 경로/버전/작업을 다시 확인하며 실제 파일을 지우지 않는다. 분리된 외장 디스크와 이동한 폴더도 확인 대상이다.
- 같은 ID의 두 폴더를 한 앱에 동시에 등록할 수 없다. 별도 작업용 사본은 **새 프로젝트로 복제**하거나 ZIP 백업을 복원해 새 ID를 만든다.
- ZIP 백업은 현재 편집 상태의 새 ID 복원용이다. 모든 이력·출력을 보관하려면 전체 프로젝트 폴더를 사용한다.
- 폴더 열기로 과거 대기/실행 생성 작업을 자동 재전송하지 않는다. 여러 앱에서 같은 폴더를 동시에 편집하는 기능은 지원하지 않는다.

기록 당시 등록 프로젝트는 5개였다. 이 목록도 현재 앱/폴더에서 재확인한다.

| 프로젝트 | ID | 당시 저장 버전 |
| --- | --- | --- |
| 하늘 해적 · GPT 실제 제작 | `f29b69ab-8f8d-4dd2-ba87-37671121ff96` | 37 |
| 검증 전용 · 제작 이력·승인·다음 작업 | `c69183dc-1408-4d29-a16a-905720c0238b` | 3 |
| 판타지 검사 · 픽셀 64×128 | `1ae8af0c-d313-453f-a834-c8bfabbc6ec7` | 38 |
| 보행 후보 검수 · Idle 기준 정렬 · 2026-10-04 | `2b5a85d7-89b5-4211-a19b-0be18dd71aa2` | 25 |
| Grok 영상 · 실제 보행 검수 | `9717eb79-f63f-40ab-adda-149697e2c8db` | 26 |

## 4. 구현 상태와 중요한 결정

React/Vite/TypeScript + FastAPI + SQLite + 독립 Python worker. 기존 이미지 가져오기/생성 → 배경 제거/원시 crop → 공통 배율·발/공중 앵커 → 반복 occurrence·가변 시간·픽셀 편집 → 수동 검수 → 확정 bake/출력을 연결했다. 원본·저장 이력·출처를 보존하고 저장 충돌/중단 작업을 처리한다.

이번까지 반영한 영상 기능:

- Grok Pro/Lite 영상 생성, MP4 가져오기·기존 영상 재처리. 기본 3초·480p, 2–6초·480p/720p. 5방향·8동작·좌우 설정과 방향별 기준 그림 프롬프트 준비, 명시적 최대 16건 묶음 접수.
- 원본 MP4/추출/배경 제거/축소/마무리 PNG의 출처 분리, 자동·전체·수동 구간, 공통 셀/배율/앵커, 참조 그림 기반 색 번짐 보정.
- `gif` 기본 마무리는 사용자가 좋다고 본 GIF와 같은 색/알파 처리를 **실제 PNG 후보에 저장**한다. `rgba`는 색상/알파 분리 축소로 반투명을 유지한다.
- 선택적 RIFE 보간과 보간 계보, 기존 동작과 주기/시간/프레임 수 맞춤. 자동 추가 이미지 생성은 하지 않는다.
- 걷기는 기본 8장, 선택 12장이고 한 사이클 시간을 유지한다. 원본 8장 샘플링에는 RIFE를 추가하지 않는다. 최신 보간 보호·크기/여백 보정·주기/그림 갱신 빈도 진단·방향별 발 판정·수동 시작 위치를 연결했다. 체형·장비 명세, 단일 이미지 구도 가이드, 정확한 VFR/stream 처리와 lossless/exact WebP를 반영했다.
- 동일 bake에서 atlas/PNG/runtime/Aseprite 호환 JSON/QA와 GIF·WebP·가로/격자 PNG를 출력한다. `animations.zip`, `animation-manifest.json`, `bundle.zip`에 반영된다. GIF는 10ms·255색·이진 알파 제한이 있다.
- 외부 접수 ID를 먼저 저장하며 중단 시 기존 요청 조회부터 재개한다. 접수 불명 POST는 재전송하지 않는다. 완료 MP4를 보존해 후처리 실패에 새 생성 비용이 들지 않게 한다.

프로젝트 폴더 저장은 공용 DB의 durable outbox → 원본 복사/프로젝트 SQLite 반영 → 성공 응답 순서다. 실패 시 `storage.syncPending`과 보류 기록을 유지한다. 폴더 이동 후에도 보류 반영을 재개하며 경로 탈출·손상·ID 충돌을 거부한다. 실행 중 폴더가 사라지면 해당 프로젝트의 작업만 중단한다.

엔진은 v2.12.1 기반에 공개 v2.19와 v2.34 품질 보완을 반영한 **프로젝트 전용 포크**다. `qualityVersion: 2.34.0`과 기반 pin을 구분한다. 비공개 spritegen 웹 내부 구현의 완전 복제를 뜻하지 않는다. 정확한 원본/패치 의존성은 `engine/engine-lock.json`, `engine/PATCHES.md`를 확인한다. 의존성 pin은 재현성 정보이며 이 저장소의 ‘최신 커밋’ 표기가 아니다.

선택 동작의 **속성 → 슬롯 → 동작 보완·검사**를 펼치면 부위 흔들림과 장비 좌우 검사를 사용한다. 저장된 편집·정렬·표시 시간을 사용하며 외부 생성은 호출하지 않는다. 흔들림은 타원 영역의 전후 미리보기 확인 후 새 검수 대기 동작으로 저장한다. 프로젝트나 설정이 바뀌면 다시 미리보기해야 한다. 장비 검사는 사용자가 지정한 표식 색에 한정되며 의심 슬롯 이동·검수판을 제공한다. 자동 수정·승인은 하지 않는다. 외부 영상 프롬프트 도우미는 엔진/CLI 범위다.

## 5. 걷기 색상 회귀를 다시 볼 때

원본 영상의 작은 색 변화에 축소·반투명 경계·GIF 팔레트 처리 차이가 겹쳤다. 검수 GIF의 마무리 단계를 에디터 PNG에 반영하고 참조 기반 색 번짐 처리를 연결했다. 기본 마무리를 임의로 생략하거나 프레임별 높이를 따로 맞추지 않는다.

- 실제 보행 프로젝트: `9717eb79-f63f-40ab-adda-149697e2c8db`, 최종 28프레임 동작: `3ffd6b67-9dff-4b25-828f-e8becb9f13c9`.
- 원본 영상 ID: `b8dfdede-a127-473a-9bf2-85c92987cda7`. MP4 SHA-256: `65754461cb508c0582224a82097c91493c52f93b10db0e69f5b74cc8819acf93`.
- 셀 64×128, 전체 1167ms. 검수 GIF와 앵커 배치 차이(오른쪽 1px/아래 2px)를 보정해 비교했을 때 28프레임 색/알파 차이 0이었다.
- 과거 별도 기준 GIF는 2026-10-06 실험 자료 정리 때 삭제했다. 현재 검수에는 프로젝트 폴더에 보존된 영상과 출력을 사용한다.
- 기존 수동 검수 미승인을 보존했다. `needs_review`/`QA_NOT_VERIFIED`를 시험 실패로 오인하거나 자동 승인으로 숨기지 않는다.

상세: [색상 회귀](VIDEO_COLOR_REGRESSION_2026-10-04.md), [웹 보완 적용](WEB_QUALITY_COMPLETION_2026-10-04.md).

사용자 결정: 드물게 발생하는 원본 영상의 장갑·무기 변색은 **에디터 색 복원 기능으로 개발하지 않는다.** 필요할 때 해당 자료를 대상으로 GPT에 개별 작업을 요청한다. 기존 배경색 번짐 제거·GIF 마무리는 유지한다.

## 6. 검증과 정리 상태

자동 검증 명령과 재실행 결과는 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)를 확인한다. 동작 보완·검사 연결 후 앱 710·웹 325개 시험이 통과했다. 엔진은 직전 품질 반영에서 9,211개 통과·기본 RIFE 실기 1건 skip이며, 이번 UI 연결에서는 엔진을 다시 변경하지 않았다. 실제 프로젝트 RIFE는 보존 영상으로 별도 실행했다. 단위·통합 테스트 수를 제품 수용 기준 전체 통과나 실제 생성 품질 승인으로 대체하지 않는다. 이하 2026-10-05 검증/정리는 당시 기록이다.

이미 실행한 실제 검증:

- 5개 프로젝트 전환 후 저장 이력 91개·작업 33개·이벤트 153개·출력 기록 87개·export 3개 보존. 원본/영상/출력 480개 파일 해시 확인.
- 보행 프로젝트 **폴더만 복사**해 새 공용 인덱스에서 열고 v26/이력 26개/이전 출력 56개 확인. 사본 편집·28프레임 bake 결과는 기존 448×512 atlas와 전체 RGBA 일치. 원본 v26 유지.
- ego TaskSpace 1의 새 탭에서 지정 부모 폴더 생성·목록 제거·재열기·이동·없는 등록 정리·이동 폴더 재열기 확인. OS 선택창은 모의 테스트, 실제 화면에서는 경로 직접 입력 사용.
- 실제 GPT 이미지 생성과 Grok 로그인 영상 생성은 이전에 성공했다. 이번 인계 검증에서는 새 유료 생성 요청을 하지 않았다.

사용자 요청으로 불필요한 검수 파일/로그 **4,385개, 435,014,185바이트(약 435MB)**를 정리했다. 임시 DB/복제본/중간 비교 이미지/캡처/로그/캐시와 프로젝트 폴더로 복사된 이전 공용 중복 리소스를 제거했다. 등록 프로젝트 5개의 데이터, 원본 유료 생성 결과, 채택한 기준 GIF, 소스/테스트/설명서 자료, RIFE는 보존했다. 소스 567개·프로젝트 파일 1,180개의 정리 전후 해시가 같고 SQLite 기록도 보존됐다.

**과거 보고서의 로컬 증거 경로는 현재 존재를 보장하지 않는다.** 특히 `artifacts/`, `output/`, `diagnostics/`, `.data/experiments/project-folders-20261005/`와 그 안의 전환 전 DB 백업·복제본·보고서/캡처는 정리됐다. 기록된 시험 결과는 역사적 요약이며 증거 파일을 새 기기에서 열 수 있다는 뜻이 아니다. 다시 검증할 때는 별도 임시 경로를 쓰고 사용자 원본을 덮어쓰지 않는다.

## 7. 코드·계약 탐색과 다음 작업

| 영역 | 진입점 |
| --- | --- |
| 앱/프로젝트 관리 | `apps/web/src/App.tsx`, `apps/web/src/useStudio.ts`, `services/api/main.py`, `services/api/store.py` |
| 폴더·정리·복구 | `services/api/project_folders.py`, `services/api/desktop.py`, `services/worker/main.py` |
| 영상 UI·요청 | `apps/web/src/VideoStep.tsx`, `VideoBatchPlan.tsx`, `VideoBasePreset.tsx`, `services/api/videos.py` |
| 영상 생성·처리 | `services/worker/video_task.py`, `adapters/spritegen/`의 `video_provider.py`, `video_processing.py`, `video_normalization.py`, `video_finish.py` |
| 동작 보완·검사 | `apps/web/src/ClipToolsPanel.tsx`, `clipTools.ts`, `adapters/spritegen/clip_tools.py`, `services/worker/clip_tools_task.py` |
| bake·검증·애니메이션 출력 | `alignment/pipeline.py`, `alignment/verify_artifacts.py`, `alignment/animation_exports.py` |
| 실행 계약 | `packages/contracts/IMPLEMENTATION.md`, `VIDEO.md`, `CLIP_TOOLS.md`, `PROJECT_FOLDERS.md`, `openapi.json` |
| 시험 | `tests/integration/`, `apps/web/tests/`, `engine/sprite-gen/tests/video/` |

현재 계약·코드·회귀 시험, 이 핸드오프/구현 현황, 날짜가 있는 과거 설계·조사를 구분해 읽는다. 초기 PRD/계획에 ‘영상 제외’, ‘구현 전’, NOT_RUN이라고 적힌 것은 당시 범위다. 계약 변경 시 코드·테스트·설명서도 함께 갱신한다.

다음 세션은 Git 확인 → 설치/로그인 필요 여부 확인 → 프로젝트 폴더 열기 → 연결/저장 상태 확인부터 시작한다. 이미 끝난 M0–M5 구현을 처음부터 다시 계획하지 않는다. 새 생성 전에 기존 원본 재처리로 문제를 재현하고 비용을 아낀다. 원 서비스 크레딧은 마지막 사용자 고지 기준 500이었으며 현재 잔여량은 확인되지 않았다. 조사 목적 호출은 필수 데이터에만 제한한다. 과거 실험 전용 스크립트는 삭제했으므로 현재 앱·엔진의 검증 명령을 사용한다.

남은 제한: OS 네이티브 폴더 선택창과 다른 OS 전체 실행은 실기 검증하지 않았다. 34개 수용 기준의 모든 하위 시나리오, 화면리더/대비/키보드 조합, 복잡한 배경의 수동 복원 품질은 전체 완료로 선언하지 않는다. 생성 결과의 외형·장비·색상·동작 일관성과 수동 미술 검수는 계속 필요하다. Codex의 해상도/품질 지정·외부 취소/결과 조회는 미지원이다. 로그인/과금 서비스, 원격 협업, 공개 배포, PXF/effect_editer 통합은 구현 범위 밖이다.

브라우저 검증은 `apps/web/README.md`에 따라 **ego-browser의 사용 허가된 기존 TaskSpace**를 재사용한다. 10-05 폴더 검증은 TaskSpace 1, 10-06 비교/업데이트 검증은 TaskSpace 3을 사용했다. 다른 환경에서 같은 숫자를 자동 선택하지 않는다. Chrome/별도 Chromium을 설치·실행하지 않고 사용자 작업 창을 가로채지 않는다.
