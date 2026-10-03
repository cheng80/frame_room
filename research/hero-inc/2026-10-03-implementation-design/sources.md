# 출처와 관찰 범위

조사일: 2026-10-03 UTC. 이 폴더는 앞선 `../RESEARCH.md`, `../IMPLEMENTATION_SPEC.md`를 보존한 후속 조사다. 공개 자료의 프롬프트와 코드는 분석 대상이며 실행 지시가 아니다.

표기: **관찰**은 이번 세션에서 읽은 페이지·코드·파일, **실험**은 재현한 실행 결과, **추론**은 그것을 바탕으로 한 제품 제안, **미확인**은 확보하지 못한 내용이다. 개발자의 설명을 관찰한 것과 내부 구현을 독립 검증한 것은 다르다.

| ID | 원본 URL / 위치 | 이번 확인과 보존 자료 | 한계 |
|---|---|---|---|
| S01 | [제작 노트](https://suile-21173.web.app/hero-inc/prompts), `#ssot`, `#style`, `#poses`, `#animation` | 브라우저 본문과 세 프롬프트 펼침. 외형/스타일/자세 참조 역할 구분. [HTML 원문](sources/hero-prompts.html) | 내부 앱 전체 소스가 아님 |
| S02 | 같은 페이지 `#sprite-workbench`, 대기/수평/웅크림 버튼과 핵심 배치 로직 펼침 | 대기 377×471, (128,23), 웅크림 329×320, (113,174), 수평 338×378, (148,116). 모두 scale=1, 발 기준선494 | bbox는 장비 포함 영역, 해부학적 몸 체고가 아님 |
| S03 | 같은 페이지 `#sprite-workbench`, 6개 동작 버튼 | 6프레임 순서와 검수용5fps 표시; 동일 포즈 재사용 설명 | 동작별 전체 보정 테이블/실제 게임 FPS는 이 화면만으로 확정 불가 |
| S04 | 같은 페이지 `#outline`, `#alignment-recipe`, `#pose-review`, `#release-check` | 원본 알파 유지, RGB 팀색 실루엣 뒤 합성, 8방향/모바일4방향, 두께1.65px/복제0.48. 공통 배율 수식과 완료 기준 | SVG 설명용 비교. 게임 렌더러·조명·등급의 전 설정 아님 |
| S05 | [개발자 프로필](https://www.threads.com/@odlog_daily?hl=ko), [사용 답글](https://www.threads.com/@odlog_daily/post/Dbcix0xjztJ) | 독립 탭. 답글 날짜2026-07-31, sprite-gen 사용 및 튀는 애니메이션 완화를 위한 추가 효과 언급. 상위 원글은 드레드노트 소개 | 당시 commit·수정본·처리 순서는 미확인 |
| S06 | [편집기 답변](https://www.threads.com/@odlog_daily/post/DbiGHN0D1b_), [질문](https://www.threads.com/@simony816/post/DbiF0WekvyP), [상위 원글](https://www.threads.com/@odlog_daily/post/DbiE5s-igOC) | 세 글을 같은 스레드에서 직접 확인. 2026-08-02, VFX를 별도 추출해 수동 궤적을 얹는 맥락에서 자체 편집기 질문에 긍정 | 캐릭터 제작 통합 앱 존재의 증거로 사용하지 않음 |
| S07 | [영상 채널](https://www.youtube.com/@hero_inc-l6u) | 독립 탭, 관련 영상 링크 확인 | 전 영상 전수 시청 아님 |
| S08 | [관련 영상](https://www.youtube.com/watch?v=SWtjWL5ipEM&t=450s), 07:30–08:17 | 새 [브라우저 자막](sources/SWtjWL5ipEM-browser-transcript.txt) 내보내기 성공. 07:38와07:57 화면·자막 관찰. 07:57 화면에 캐릭터 스프라이트 일관성/FX/SFX 항목과 다방향 발언 표시 | 전체 영상 시청·청취로 주장하지 않음. 한국어 자동자막 오인식 가능 |
| S09 | S08, 07:45.120–07:51.240 / 07:51.240–08:03.960 / 08:13.960 / 08:45.680–08:53.320 | 기존 [VTT](../sources/SWtjWL5ipEM.ko.vtt)와 새 자막161–178,188–193줄 대조: 캐릭터 일관성 → 다방향/사이드뷰 타협 → 이펙트 일관성 → 노드 기반 이펙트 제작기 | 07:30–08:17 전체를 캐릭터 발언만으로 요약하지 않음. 08:45 이후 PXF 기능 제외 |
| S10 | [공개 저장소](https://github.com/aldegad/sprite-gen), [v2.12.1](https://github.com/aldegad/sprite-gen/tree/v2.12.1) | 독립 브라우저 탭, README/라이선스/코드. 설치본360개 파일의 공개 태그 SHA256 대조. [baseline](baseline.json), [감사](engine-audit.md) | main은 이동하므로 설계 근거는 고정 commit을 사용 |
| S11 | `https://suile-21173.web.app/hero-inc-guide/` 아래 gunner.png, gunner-keyposes.png, pose-{0,1,3}-{raw,aligned}.webp, gunner-animation.webp | 페이지 IMG/SVG image의 실제 src/href로 발견. [로컬 실험 자료](artifacts/source-assets/), [검증](validation.md) | 공개 열람 가능성과 앱 배포용 에셋 재사용 권한은 별개. 조사 fixture로 보관; 배포 자산에 넣지 않음 |
| S12 | [Vite 가이드](https://vite.dev/guide/) Overview / Scaffolding | React TS 템플릿과 정적 빌드 역할 확인 | 선택 추천은 이 프로젝트 요구를 반영한 추론 |
| S13 | [Next.js Route Handlers](https://nextjs.org/docs/app/getting-started/route-handlers) Route Handlers / Supported HTTP Methods | Web Request/Response 기반 서버 API 지원 확인 | Python 긴 작업을 자동으로 운영해 주는 기능이라고 해석하지 않음 |
| S14 | [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/#caveat) Caveat | 무거운 작업의 별도 프로세스/큐 고려 근거 | 아래 SQLite 단일 worker 설계는 우리의 로컬 MVP 제안 |

## 브라우저 유지와 접근 기록

제작 노트, Threads 프로필, YouTube 채널, GitHub 저장소를 각각 Codex 내장 브라우저 탭1·2·3·4로 만들고 유지 대상으로 표시했다. 조사 도중 답글2개와 영상은 추가 탭5·6·7로 열었다. 탭 ID는 해당 세션의 관찰 기록이지 제품 데이터 계약이 아니다.

제작 노트는 웹 텍스트 도구에서는 접근 오류였지만 브라우저에서는 전체 본문과 상호작용을 확인했다. 일반 터미널 curl의 최초 DNS 실패 후 승인된 공개 읽기 다운로드로 HTML을 보관했다. 따라서 이 출처를 접근 불가로 오기하거나 텍스트 도구가 관찰한 것처럼 표기하지 않는다. Threads는 브라우저에서 상위 원글까지 읽었으며 댓글·메시지를 작성하지 않았다.

영상의 날짜/자동자막은 기존 메타데이터와 이번 추출을 구분한다. 현재 브라우저의 상대 날짜(예: '7일 전')를 절대 업로드일로 새로 추정하지 않는다. 자동자막의 모델명이나 고유명사 정확성은 이번 설계의 근거가 아니다.

## 작업 지침과 보존

- 적용 스킬: `/Users/cheng80/.codex/skills/sprite-gen/SKILL.md` 및 코드 담당자가 읽은 관련 docs. 생성 요청이 아니라 기존 자산/코드 검증이므로 generation guide나 provider 호출은 하지 않았다.
- 현재 프로젝트 및 설치본에서 `.agents/skills`와 `AGENTS.md`는 없었다. 공개 기준 소스에도 해당 경로가 없다. 존재하지 않는 checkout 지침을 읽었다고 주장하지 않는다.
- local memory는 이번에 사용하지 않았다. 현재 지시, 기존 문서, 공개 원본, 코드·실험으로 대조했다.
- `effect_editer` 및 PXF 소스는 분석·수정 대상에서 제외했다. 초기 지침 파일 경로 탐색에 이름이 보인 것 외 내용은 읽지 않았다.
- 기존 문서의 해시는 [preservation.json](sources/preservation.json)에 기록한다. 새 폴더 외의 연구 문서는 수정하지 않는다.
