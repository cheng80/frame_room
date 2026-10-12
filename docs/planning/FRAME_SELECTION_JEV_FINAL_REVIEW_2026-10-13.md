> 보관 안내(2026-10-13): 이 문서는 2026-10-12~13 프레임 선별 실험·검수 당시의 기록이다. 여기 적힌 Laya·Jev·관찰 모델 비교 등의 선택지와 실행 방법은 현재 기본이 아니다. 현재 기본은 로컬 Codex catalog의 최신 Luna 관찰과 규칙 판정이며 [FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md](FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md)를 따른다. 시험 수, `output/`·`/tmp` 증거 경로와 작업 ID는 당시 작업 폴더 기준이며 이 저장소에 포함되지 않는다. 키 값과 비밀 파일 해시는 기록하지 않았다.

# Jev 판정 준비 및 실제 비교 독립 검수

최종 결론: 준비·실제 비교 모두 **no blocking findings**. PM 최종 freeze 확정 및 비교 문서 정정까지 확인했다(2026-10-13 KST).
Task `task_2fb9eee0826b`, Dispatch `ctx_c9064e61096c`, Run `run_8445d1de9181`; GPT-6.1 Sol Medium, 읽기 전용. 코드·데이터·프로젝트 문서 편집 없음. 검수 산출물은 `/tmp`에만 기록했다. 실제 키 내용·비밀 파일 hash·실제 외부 호출·모델 설치·영상 생성·브라우저 조작 없음.

## 준비 검수와 해결한 지적

공식 TypeSafe [API](https://docs.typesafe.ai/api), [모델](https://docs.typesafe.ai/models), [Choice](https://docs.typesafe.ai/primitives/choice), [신뢰도](https://docs.typesafe.ai/confidence), [citation cookbook](https://docs.typesafe.ai/cookbooks/citation_check) 및 typesafe-ai SKILL, AGENTS.md, Orca 최신 CLI/orchestration 지침을 확인했다. Markdown 주소는 web 도구 접근 실패, 확장자 없는 공식 페이지는 읽었다.

Jev `jev-1.13.0`은 text-only이고 요청은 Bearer 인증의 `{model,state,questions}`이며 Choice 응답은 model/answers/usage와 라벨·전체 확률·confidence다. 질문 ID는 모델에 전달되지 않으므로 instructions에 후보 state 경로를 명시해야 한다. 신뢰도는 분포 집중도이며 정확도·승인 권한이 아니다. Cookbook의 0.8은 예시 게이트다.

- P1 인증 헤더: fake sentinel과 `http.client.putheader` 로컬 연산으로 CR/LF ValueError 인증값 노출을 재현했다. 구현 담당이 ASCII·control·공백 키 검증, capability에서 관찰 전 실패, transport ValueError 고정 코드, 원본 cause/context 제거로 수정했다. 실제 키·HTTP는 사용하지 않았다.
- P2 명시 빈 process-env가 .env로 fallback하는 문제: 환경에 이름이 있으면 빈 값도 우선하도록 수정됐다.
- P2 큰 숫자의 OverflowError와 확률 합 1.005 허용: 초대형 정수 안전 거부, `fsum` 공차 0.001로 수정됐다. 공차는 미보정 실험값이다.
- P2 `frameJudge=jev`의 uniform 경로 무시: API와 처리 계층 모두 vision 전용으로 거부한다.
- Jev는 opt-in이며 auto/rules/laya 기본값·Laya state/criteria·관찰 VERSION/PROMPT와 Luna 캐시 키를 보존한다. 코드 정책·unknown/missing/conflict review·시퀀스 롤백·타이밍·균등 대체 후보·사용자 review/hidden 보존을 확인했다.
- transport는 요청 1회, 자동 retry/fallback 없음, 상태/고정 오류 코드만 기록한다. malformed JSON·모델 불일치·HTTP 오류는 auto-keep 하지 않는다. 관찰 cache-only 미스는 Jev 전에 중단하며 Luna를 호출하지 않는다.
- 키 로더는 좁은 lazy parser이고 쉘 실행 없이 process-env/.env의 두 변수만 읽는다. 키를 os.environ에 넣지 않고 Codex subprocess에는 TYPESAFE_API_KEY를 제거한다. .env Git 제외와 권한600을 확인했고 내용/hash는 수집하지 않았다.

## 실제 독립 실행한 오프라인 검증

- 기존 selection 기준: **40 passed, 1 deselected** (9.48초). 실제 Laya smoke 제외, capability offline·socket·_laya 차단. `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-pytest-baseline.txt`.
- 초기 freeze 관련/독립 시험: **87 passed, 4 failed, 1 deselected** (21.15초). 세 실패는 P1, 하나는 검수 harness가 mocked urlopen까지 막은 문제였다. harness를 바로잡고 P1 수정 후 재검증했다. `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-pytest-final.txt`.
- 최신 Jev44 + 독립15: **59 passed** (7.12초). 실제 key env 제거 및 `.env`는 /tmp의 없는 경로로 대체, 실제 network/MLX 추론 차단. `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-pytest-fixed.txt`.
- 독립 dry-run: key loader/dotenv/capability/network를 강제 차단하고 OUT=/tmp로 실행. 두 영상 각각 기존 Luna 23관찰, 같은 원본·9이미지·관찰 캐시·state/질문23개 확인. `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-runner-review.txt`, `/tmp/frame-selection-jev-runner-review/prepared/`.
- 정상 녹색 합성 sprite + **fake observer/fake HTTP** 정책 self-check: keep23/reject0/review0/changed0. `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-normal-green-policy.txt`. 실제 Jev 녹색 오탐률 증명 아님.
- freeze 14개 및 `git diff --check` 통과. 구현 담당의 전체2457 passed/1 skipped, 웹503 passed·tsc/build는 기록을 확인했으며 검수자가 전체를 다시 실행하지 않았다.

## 실제 두 영상 결과의 독립 검증

PM 승인 뒤 Opus가 실제 비교를 실행했다. 검수자는 다시 호출하지 않고 실제 job·캐시·프로젝트 SQLite를 read-only로 읽고 최종 이미지/재생물을 검증했다.

새 프로젝트 `28dbc952-3849-428a-bef4-b566d0f9ffb2`, 저장 revision7, clip2, frame18 (사용16·미사용 균등 대체2).

| 항목 | 해적 | 성직자 |
|---|---|---|
| 작업 | `013a595b-6232-43f2-9eab-29ff15a3ee77` | `37a9093a-67ca-40ba-9293-ac120bc9b830` |
| 적용 인덱스 | 18,21,25,27,30,33,36,39 | 33,36,39,42,46,50,52,55 |
| 교체 | F024→F025 | F049→F050 |
| keep/reject/review | 15/6/2 | 19/1/3 |
| 요청→실제 모델 | jev-1.13.0→jev-1.13.0 | 동일 |
| 호출/HTTP/질문 | 1/200/23 | 1/200/23 |
| 입력/출력 tokens | 4502/877 | 4382/877 |
| HTTP 지연 | 0.250s | 0.224s |
| 저장·WebP 시간 | 1000ms | 1083ms |
| GIF 시간 | 1000ms | 1080ms (기존10ms tick 반올림) |

실제 TypeSafe 요청은 총2회, 추가 Luna 관찰0회, 재시도·다른 모델 fallback 없음. 같은 Luna 캐시 key와 cacheHit, 호출수0, 이미지9장의 SHA, 준비 preview와 실제 Jev cache의 state/questions 및 receipt SHA를 직접 대조했다. 기존 Laya 결과를 재사용했으며 새 Laya 추론을 하지 않았다.

라이브러리 clip은 각각 8개 slot, walk, loop=true, 양의 duration과 증가하는 인덱스, 합계1000/1083ms를 유지한다. F024/F049는 슬롯에서 제외된 uniform-alternative로 이미지가 존재하고 사용횟수0이며 사용자 pending/hidden=false/reviewReason 없음이다.

SQLite artifact 표의 GIF/WebP 네 파일 해시가 실제 파일과 같다. 모든 파일은8프레임/무한루프. **실제 WebP16셀을 라이브러리 alignment로 메모리 렌더한 RGBA와 대조하여 전부 정확히 일치**했다. `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-live-artifacts.json` 및 `.txt`에 독립 증거가 있다.

라이브 runner의 `/v1/providers` 객체 `{providers:[...]}` wrapper 처리1줄 수정도 API source의 반환형과 일치한다. 해당 첫 오류는 프로젝트/TypeSafe 호출 전에 발생했고 현재 두 작업 receipt는 예산 안이다.

## 품질 해석

실제 신규 라이브러리의 균등 대체와 선택 셀을 /tmp로 렌더·확대하여 봤고, 기존 raw/keyed/final의 F024/25 및 F048/49/50 비교도 직접 봤다. 이 이미지들은 기존 Grok 생성 영상에서 추출한 실제 데이터이며 합성 정책 시험과 구분했다.

- 해적 F024의 화면 오른쪽 부츠 정강이·발에 올리브 색조가 있으며 F025는 갈색으로 개선된다. magenta raw에서도 있어 배경 제거의 녹색 잔여라고 단정하지 않는다.
- 성직자 F049 하체 얼룩은 명확하며 F050은 덜하지만 약한 색조가 남는다. 완전히 clean인 이웃을 선택했다고 주장하지 않는다.
- **두 영상의 Jev 최종 GIF/WebP4개 SHA가 기존 Laya와 모두 같다.** 선택 인덱스도 동일하다. `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-quality-identity.json`.
- Laya 대비 추가 review는 해적 F040, 성직자 F033/F056뿐이다. 선택 개선·영상 품질 우월성은 입증되지 않았다. Jev가 이미지를 보지 않아 Luna의 누락 결함을 보완할 수 없다.
- Laya는 후보별 state, Jev는 영상 전체 state의 독립 질문을 함께 받으므로 문맥 범위가 다르다. 0.6 gate도 각 모델에서 같은 품질 의미로 보정된 것이 아니다. 영상2개/모델시각라벨로 일반 정확도·우열을 추정하지 않는다.
- 해적 F021(review) 지속167ms, F025 83ms 등 기존 시간 비용은 그대로다. applied가 모든 결함 해결을 뜻하지 않는다.

확대 증거: `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-actual-pirate-uniform-vs-selected.png`, `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-actual-cleric-uniform-vs-selected.png`.

## UI·원본 보존

구현 담당의 ego TaskSpace21 UI screenshot/JSON을 읽고 확인했다. Jev 옵션 enabled, 실제 새 프로젝트 revision7, 해적 슬롯3의 F025/83ms와 8slot/1000ms, review 슬롯 설명 및 F024/F049 후보0회 사용 기록이 데이터와 일치한다. 검수자는 직접 브라우저를 조작하지 않았다. 사용자 mouse/Chrome 없음. saved UI evidence는 `output/frame-selection-jev/ui/`에 있다.

독립 보존 검증: baseline data15981 missing0, 변경은 `.data/app.sqlite3`와 실행 중이던 이전 앱 stdout2개뿐. 기존 비교 원자료110 전부 unchanged. baseline worktree108 missing0, 변경9개는 기능범위이며 사용자 AGENTS 등 보존. 최신freeze14 일치. 신규프로젝트·새Jev캐시는 요청된 추가분이다. .env값 변화는 사용자 등록이므로 hash를 수집하지 않았다. `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-preservation-live.txt` 및 `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-preservation-current.json`.

## 검증 한계

실제 키 내용·비밀 hash, 검수자의 live API 호출/재호출, 모델 설치, 영상 생성, Git 게시, 직접 browser 테스트와 전체 빌드 반복은 하지 않았다. fake 계약 시험은 실제 서비스 품질 증명이 아니다. 실제 두 요청의 결과는 저장·재생·동일 입력을 검증했지만 사람 정답 라벨·반복성·일반 정확도·Laya 대비 품질 우월성을 입증하지 않는다.

최종 문서 예비 P3: 실비교 문서 결과요약의 규칙 대비 차이6개는 실제로5개(해적F018/F040, 성직자F033/F048/F056)다. 그중4개 풀경계라는 집계는 맞다. 경계 unknown의 존재는 코드사실이나 review 원인 효과는 상태치환 ablation 없이 추론이다. PM에 msg_b895d63f8610으로 최소 문서 정정을 요청했다.

실행 범위 보충: 오프라인 pytest는 `/tmp`의 합성 fixture MP4를 ffmpeg로 만든다. 이것은 새 AI 영상 생성이나 실제 사례가 아니며, 기존 실영상 원본·실험 데이터는 읽기만 했다.

## 최종 확정

PM msg_45ef5038287e로 최종 freeze 및 더 이상 수정 없음을 통보받았다. 실비교 문서의5reviews(해적2+성직자3),4경계+F048, 실제실험일2026-10-13KST, 경계효과추론·분리실험미실행, 공식단가출처 정정을 직접 확인했다. P3도 해결됐으며 미해결 blocking finding은 없다. 코드freeze14개와 실제output 검증은 위 증거 그대로다. 사용자의 원본·기존변경을 보존했고 검수자는 프로젝트 파일을 수정하지 않았다.

최종 보고 실체: `/Users/cheng80/Desktop/Current_works/frame_room/docs/planning/FRAME_SELECTION_JEV_FINAL_REVIEW_2026-10-13.md`. 핵심 실제 증거는 `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-live-artifacts.json`, `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-quality-identity.json`, `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-preservation-live.txt`, `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/review/frame-selection-jev-review-pytest-fixed.txt`다. 신규실험 원자료는 `/Users/cheng80/Desktop/Current_works/frame_room/output/frame-selection-jev/`, 수정된 비교문서는 `/Users/cheng80/Desktop/Current_works/frame_room/docs/planning/FRAME_SELECTION_JEV_COMPARISON_2026-10-12.md`다.
