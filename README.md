# 프레임룸 · 캐릭터 스프라이트 에디터

React + Vite + TypeScript, FastAPI, SQLite, 독립 Python worker로 실행하는 로컬 제작 도구입니다. 이미지를 가져오거나 승인한 기준으로 생성한 뒤, 알파·프레임·공통 배율·발 앵커·순서·시간·픽셀을 편집해 게임용 파일로 내보냅니다.

## 실행

```sh
scripts/setup.sh       # 최초 설치: Python 3.12 전용 venv, 고정 의존성, 웹·설명서 빌드
scripts/start.sh       # http://127.0.0.1:8765
```

macOS에서는 **`프레임룸 실행.command`**를 더블 클릭해도 됩니다. Node.js/npm과 [uv](https://docs.astral.sh/uv/getting-started/installation/)가 필요합니다. 서버·worker가 실행되는 터미널을 닫으면 앱이 종료됩니다. 생성 결과가 불명확한 중단 작업은 재시작 때 자동 재전송하지 않습니다.

개발: `scripts/dev.sh` → [http://127.0.0.1:5173](http://127.0.0.1:5173). 서버는 loopback에만 바인딩합니다. 작업 파일은 `.data/`에 저장되며 프로젝트 백업 ZIP으로 이동할 수 있습니다. 공용 스킬 설치본에 런타임 의존하지 않습니다.

## 사용 흐름

1. 프로젝트를 만들고 PNG/WebP를 가져옵니다. 외형·스타일·자세 참조를 나누고 외형 기준을 승인합니다.
2. 기존 이미지는 추출로 이동합니다. 생성은 **Codex · ChatGPT 구독**을 명시적으로 선택하고 프롬프트·요청 프레임 수를 설정합니다. 로그인 준비와 실제 생성 성공·잔여량은 별도 표시됩니다.
3. 필요하면 균일 배경을 제거합니다. 전체·격자·연결 성분·수동 영역으로 원시 crop을 추출합니다. 자세별로 높이를 맞추는 자동 확대는 하지 않습니다.
4. 같은 그룹의 배율·출력 셀을 정하고 각 후보의 발 또는 공중 root 앵커를 확인합니다. 원본 크기 유지 또는 승인한 몸 기준의 공통 배율을 사용합니다.
5. 동작에 후보를 추가합니다. 반복 슬롯, 순서, FPS/개별 밀리초, 변형, 픽셀 펜·알파 지우개를 편집하고 저장합니다.
6. 후보·앵커·동작을 검수합니다. 팀 테두리는 미리보기 전용 또는 출력에 포함할 수 있습니다.
7. 게임용 파일을 출력하고 **최종 결과 보기**로 실제 출력 bitmap을 확인합니다. 독립 출력 뷰어에서는 `runtime.json`과 `atlas.png`만 열어 재생합니다.

저장 충돌 시 초안을 유지하고 서버 버전과 비교해 다시 적용할 수 있습니다. 이력 복원은 새 revision을 만들며, 백업 복원은 새 프로젝트 ID를 만듭니다. 원본과 이전 출력은 덮어쓰지 않습니다.

## 출력

- `atlas.png`: 확정 셀 아틀라스
- `pngs.zip`: 아틀라스에서 추출한 순서별 PNG와 sequence manifest
- `runtime.json`: occurrence 순서·가변 시간·반복·앵커·lineage·hash
- `aseprite.json`: Aseprite 호환 JSON (`.aseprite` 편집 원본 아님). 반복/앵커 정책은 runtime 동반
- `qa.json`: 승인·알파·잘림·전체 RGBA 일치 검증
- `bundle.zip`: 최종 출력 묶음

빈 타임라인, 미승인 기준/앵커/동작, 비어 있는 알파, 셀 밖 픽셀, 누락·손상 원본, 오래된 저장 revision은 최종 출력을 차단합니다. 편집 canvas는 빠른 미리보기이며 최종 판정은 서버의 확정 bake를 사용합니다.

## 검증

```sh
engine/sprite-gen/.venv/bin/python -m pytest tests/integration -q
npm --prefix apps/web test
npm --prefix apps/web run build
```

[구현·검증 현황](docs/product/IMPLEMENTATION_STATUS.md)에 실제 실행 범위와 남은 제한을 기록합니다. 연구의 19개 관찰 검사, 앱 자동 회귀 수, [34개 제품 수용 기준](docs/product/ACCEPTANCE_TESTS.md)은 서로 다른 집계입니다. 실제 provider 호출과 모의 작업 시험도 구분합니다.

## 엔진·범위·자료

프로젝트 엔진은 `engine/sprite-gen/`의 **v2.12.1 / `b058341f7543f3adcbea227bd4e6b7587895b1bc`**입니다. [engine-lock](engine/engine-lock.json), 원본 hash 목록, 변경 고지, Apache-2.0 LICENSE·NOTICE를 보존합니다. 최신 upstream으로 자동 전환하지 않습니다.

복잡한 배경의 자동 제거, 외형 일관성, 실제 생성의 native alpha는 보장하지 않습니다. Codex의 해상도·품질 지정/외부 취소·결과 조회는 미지원 상태를 표시합니다. OpenAI 유료 API·Grok fallback은 활성화하지 않습니다. 영상·다방향 자동화·원격 협업·공개 배포와 별도 PXF/effect_editer 프로젝트는 범위 밖입니다.

`tests/fixtures/robot-*.png`는 직접 만든 합성 CC0 시험 자료입니다. 공개 거너 이미지는 연구·로컬 회귀용이며 앱 기본 배포 에셋으로 포함하지 않습니다.

## Git 저장 범위

소스 코드·의존성 잠금 파일·합성 시험 자료·설명서용 이미지와 프로젝트 전용 엔진을 저장합니다. 엔진의 원본 360파일과 LICENSE·NOTICE는 무결성 검증을 위해 함께 보존합니다.

`.data/`, `artifacts/`, `output/`, `diagnostics/`, 연구의 원본 다운로드·캡처·외부 자료, `.env`·인증 정보, 설치 의존성·빌드·캐시는 `.gitignore`로 제외합니다. 제외한 파일은 로컬에 그대로 남습니다. 연구 문서의 원본·증거 경로는 로컬 자료를 가리키므로 새 복제본에는 없을 수 있습니다. 연구용 거너 원본이 없는 환경에서는 해당 회귀 검사 1건만 건너뜁니다.

설명서 ZIP은 `scripts/setup.sh`에서 다시 만듭니다. 설명서를 수정한 뒤에는 `npm --prefix apps/web run build`와 `engine/sprite-gen/.venv/bin/python scripts/package-guide.py`로 재생성합니다. 프로젝트 작업 데이터는 앱의 백업 ZIP으로 별도 보관하세요.

- [최종 제품 문서](docs/product/README.md) · [핸드오프 원문](docs/product/HANDOFF.md)
- [mydot 후속 조사·코드 감사·원본 증거](research/hero-inc/2026-10-03-implementation-design/README.md)
- [초기 조사와 출처](research/hero-inc/RESEARCH.md) · [출처 목록](research/hero-inc/sources/index.json)
- [사용자 합의](docs/planning/USER_DECISIONS.md) · [조사→설계→구현 이력](docs/planning/DELIVERY_PLAN.md)

조사 원본·공용 엔진·다른 프로젝트는 로컬에 보존합니다. GitHub 비공개 저장소에는 위 저장 범위만 포함합니다.
