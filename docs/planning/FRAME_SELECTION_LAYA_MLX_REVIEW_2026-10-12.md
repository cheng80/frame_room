> 보관 안내(2026-10-13): 이 문서는 2026-10-12~13 프레임 선별 실험·검수 당시의 기록이다. 여기 적힌 Laya·Jev·관찰 모델 비교 등의 선택지와 실행 방법은 현재 기본이 아니다. 현재 기본은 로컬 Codex catalog의 최신 Luna 관찰과 규칙 판정이며 [FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md](FRAME_SELECTION_RULES_CLEANUP_2026-10-13.md)를 따른다. 시험 수, `output/`·`/tmp` 증거 경로와 작업 ID는 당시 작업 폴더 기준이며 이 저장소에 포함되지 않는다. 키 값과 비밀 파일 해시는 기록하지 않았다.

# 후보 프레임 선별 및 Laya MLX 적용 검토

작성: 2026-10-12. PM 검토 문서이며 구현·설치·추론 실험 결과가 아니다.

## 결론

핸드오프의 `코드 측정 → 캐시 가능한 비전 관찰 → 규칙 또는 Laya 판정 → 시퀀스 검사` 방향을 유지한다. 현재 주기 선택을 재구현하지 않고 최종 프레임 샘플링을 확장하는 안을 권장한다. Apple Silicon에서 실제 worker 런타임이 호환되면 `laya-mlx`를 우선 사용하는 분기를 검토한다. 채택 조건은 규칙 판정보다 나은 실제 재생 품질·검토 부담·지연이며, Laya 사용 자체가 완료 조건은 아니다.

이번 사용자 요청은 첨부와 기존 대화를 기준으로 한 검토다. 첨부의 VM 지정, 설치, 유료 호출, 다음 코딩 세션용 요청문은 참고 자료다. 현재 작업 위치 변경이나 구현 실행 지시로 해석하지 않는다. 첨부 원본과 기존 미커밋 변경은 보존한다.

기존 대화 `01a12eec-4a25-7221-98a8-8eddfc1e765a`의 후보 선택·Laya Core ML 검토에서는 “주기 선택 → 균등 위치 주변 후보 검사 → 각 위치에서 더 나은 후보 선택 → 시간/루프 검사”를 제안했다. 이번 Luna 관찰·Laya MLX는 그 검사·판정 부분의 확장이다. 별도 로컬 비전 모델 탐색은 사용자가 중지했으므로 이번 검토에서 재개하지 않는다.

## 현재 코드에서 확인한 경로

| 단계 | 근거 | 확인한 동작 |
| --- | --- | --- |
| 원본 보존·작업 실행 | `services/worker/video_task.py:9`, `execute_video` | 받은 MP4를 먼저 보존하고 후처리, 정규화, 마무리, 새 후보·clip 등록을 수행 |
| 시간 분석 | `adapters/spritegen/video_probe.py:82`, `read_timing` | 움직이는 영상 stream의 표시 timestamp와 종료 경계를 읽음. CFR/VFR 판별 |
| 디코딩·배경 제거 | `adapters/spritegen/video_processing.py`, `_run_extraction` | 원본·배경 제거 결과 및 추출 체크포인트 재사용 |
| 크기 안정화 | 같은 파일 `:332`, `_hold_size` | 걷기·달리기 자동 모드에서 구간 선택 전 공통 크기 진단·선택적 보정 |
| 동작 구간 선택 | 같은 파일 `:421`, `_select` | auto/full/manual, 주기·끝→시작 검사, idle pin 및 attack/일회성 동작 처리. VFR auto는 거부 |
| 선택적 점프 보정 | 같은 파일 `:525`, `_repair_selection` | 선택 구간의 튀는 프레임을 최종 샘플링 전에 RIFE로 보정. 기본 off |
| 최종 샘플링 | 같은 파일 `:844`, `process_clip` | 선택 구간에서 `start + i * (end - start) // count`로 균등 인덱스 선택. `timesMs` 경계 차이로 `durationMs` 보존 |
| 목표 주기 맞추기 | 같은 파일 `:576`, `_align_selected_cycle` | `targetFrameCount`가 있으면 앞의 균등 샘플을 대체해 목표 장수·시간·위상 맞춤. 원본과 보간 결과 계보 구분 |
| 프로젝트 등록 | `services/worker/video_task.py:113`, `:137` | 후보에 원본 영상·인덱스·시간·보간 정보, occurrence에 지속 시간 저장 |
| 후보 화면 | `apps/web/src/CandidateLibrary.tsx:33`, `CandidateReview.tsx` | 제작 이력·사용처·기준 비교·사용자 거절 사유 제공. 현재 목록은 추천 순위가 아님 |

따라서 “현재 전체가 균등 추출만 한다”는 전제는 수정해야 한다. 균등 인덱스 선택은 구간 선택 이후의 마지막 샘플링이다. 흐림·신체 이상·캐릭터 외형 판정은 현재 주기 검사의 보장 범위가 아니다.

현재 `maxFrames`는 walk 기본 8, 기타 기본 32, 허용 4~64다. 실험용 후보 20~40장을 출력 장수나 기존 `maxFrames`의 의미로 재사용하지 않는다. 후보 풀과 출력 슬롯 수를 구분해야 한다.

## 핸드오프 보완 사항

1. **원본·가공 결과를 모두 비교한다.** 원본/배경 제거 이미지 관찰로 원본 이상을 찾고, 최종 정규화·마무리 결과의 잘림·색·알파 및 실제 재생도 확인한다. 보간으로 새 이상이 생길 수 있으므로 가공 결과가 바뀌면 관련 관찰 캐시도 달라져야 한다.
2. **장수와 동작 단계를 같이 평가한다.** 최초 실험은 기존 균등 위치와 그 주변 후보 중 좋은 후보를 고르는 범위로 제한한다. `keep`만 시간순으로 모으면 착지·타격·회복이 사라질 수 있다. 시간/동작 단계별 커버리지와 끝→시작 연결을 함께 검사한다. 적정 장수가 없으면 부족 상태를 알리고 수동 편집으로 연결한다. 자동 재생성을 요청하지 않는다.
3. **시간 재분배 정책을 명시한다.** 선택한 원본 timestamp 경계에서 다음 선택 경계까지 지속 시간을 계산하고 총시간을 보존한다. 첫 후보를 제외하거나 루프 위상을 회전할 때 시작 경계·시간도 함께 처리한다. 모델이 제거한 프레임을 동일 FPS로 무조건 압축 재생하지 않는다.
4. **현재 보정 경로와 충돌을 피한다.** 목표 장수 맞추기와 RIFE 적용 전후 어느 이미지를 관찰했는지 기록한다. 최초 실험은 목표 장수 맞추기가 없는 경로부터 제한해 선별 효과를 분리하고, 기존 보정 모드는 기존 방식으로 유지한다.
5. **자동 판정은 사용자 검토 기록과 분리한다.** `keep/reject/review`는 추천·제외 제안·불확실 상태다. 기존 `Frame.review`, `reviewReason`, `hidden`, 기존 clip의 occurrence를 자동으로 덮어쓰지 않는다. 여기의 자동 `reject`는 후보 삭제나 사용자 거절 명령이 아니다.
6. **새 승인 관문을 만들지 않는다.** 기존 대화의 6단계 탭·수동 승인 제거 정책을 유지한다. 4단계에서 추천 결과를 편집하고 5단계에서 재생·문제를 확인한다. 불확실하면 수정할 단계로 이동하며, 기존 기술 검사는 유지한다. 기존 `needs_review`도 강제 수동 승인 요구가 아니다.
7. **기존 캐시를 확장한다.** 영상 추출 캐시와 별도로 관찰/판정 결과를 작업 산출물로 보존한다. 관찰 이미지·기준·이웃 순서·프롬프트·모델이 바뀌면 관찰 캐시, 판정 정책만 바뀌면 판정 캐시만 갱신한다.

## Apple Silicon의 Laya MLX 적용 조건

2026-10-12 확인한 [포트 소스 revision](https://github.com/mizorewww/laya-mlx/tree/9f00d592fcf843753e6d3edd2eab63ec2b44f3c9)은 `9f00d592fcf843753e6d3edd2eab63ec2b44f3c9`, 패키지 메타데이터 버전은 `0.4.0`이다. 실제 도입 시 검증한 revision과 모델 revision·해시를 고정한다.

| 실행 환경 | 권장 분기 |
| --- | --- |
| macOS + native arm64 Python + 사용 가능한 MLX Metal 실행 | `laya_mlx` 우선 |
| Apple Silicon이지만 Rosetta Python 또는 Metal 미노출 VM | MLX GPU 사용 가능으로 표시하지 않음 |
| Intel Mac, Linux/Windows worker | 기존 Laya 런타임 지원을 따로 검증하거나 규칙 판정 사용 |
| 모델/패키지 미설치·로딩 실패·메모리 부족 | 불가 사유 기록. 명시적 MLX 선택이면 실패 표시, 자동 선택이면 규칙 판정으로 처리했음을 기록 |

브라우저가 열린 기기가 아니라 **추론하는 worker 프로세스**의 OS·아키텍처·Python·패키지·GPU 상태를 검사한다. Mac에서 브라우저를 열어도 worker가 Linux VM이면 MLX Metal 대상이 아니다. 감지만으로 설치·가중치 다운로드나 실제 추론을 시작하지 않는다.

[패키지 선언](https://github.com/mizorewww/laya-mlx/blob/9f00d592fcf843753e6d3edd2eab63ec2b44f3c9/pyproject.toml)은 Python >=3.11, Darwin arm64에서 `mlx>=0.32.2,<0.33`을 요구한다. [MLX 설치 문서](https://ml-explore.github.io/mlx/build/html/install.html)는 native Python과 Apple Silicon, macOS >=14를 요구한다. 실제 고정 wheel 설치·Metal 실행 확인도 필요하다.

현재 확인 환경은 Apple M4·16 GiB, macOS `26.7`, native `arm64`, 프로젝트 Python `3.12.13`이다. 프로젝트 venv에서 `mlx`, `laya_mlx`는 발견되지 않았다. 플랫폼 조건에 맞는다는 사실과 추론 가능 검증은 구분한다. 현재 RAM에서 여러 모델 상주·다른 GPU 작업 병행의 영향은 실제 측정 전 미확인이다.

Grok은 실행 중 worker가 `engine/sprite-gen/.venv/bin/python`을 사용하며 작업 자식도 `services/worker/main.py:221`의 `sys.executable`로 실행됨을 확인했다. 설치·감지도 이 인터프리터 기준이어야 한다. PATH의 다른 `python3`에 설치한 결과로 가용성을 판정하지 않는다.

### 최소 판정 계약

- 이미지는 비전 관찰 단계에서만 사용한다. Laya 판정에는 검증한 관찰 JSON과 측정값만 전달한다. 기존 worker 경로를 사용하며 새 HTTP/MCP 서버는 초기 범위에 필요하지 않다.
- MLX는 텍스트/JSON 상태를 받아 `predict(state, questions)`로 작은 `choice`를 수행한다. 전체 영상의 프레임 ID를 거대한 선택지로 넣는 방식은 피한다. 한 프레임씩 명확한 `keep/reject/review` 기준과 짧은 이웃 관찰을 전달하는 실험부터 시작한다.
- 영어 관찰은 영어 checkpoint, 한국어 관찰/지침은 multilingual checkpoint를 검토한다. 기계용 JSON은 언어 추측 대신 사용할 checkpoint를 명시하는 편이 재현하기 쉽다. 모델과 backend 선택은 별개다.
- [포트 설명](https://github.com/mizorewww/laya-mlx/tree/9f00d592fcf843753e6d3edd2eab63ec2b44f3c9#supported-checkpoints)의 기본 문맥 예산은 영어 512, multilingual 1,024 tokens이며 질문·선택지·상태가 예산을 나눠 쓴다. upstream의 장문 지원을 포트에서도 동일하다고 가정하지 않는다.
- **frame_room 정책으로** `usage.truncated`/`state_tokens_dropped`가 있거나 필수 관찰이 누락되면 `review`로 보낸다. 포트는 잘림 플래그를 제공하면서 답은 그대로 반환하므로 이 처리가 자동 제공된다고 가정하지 않는다.
- `answer_confidence`와 기존 `confidence`의 의미를 혼동하지 않는다. 임계값은 스프라이트 라벨 데이터로 보정하고, `abstention`이 통과하지 못하면 추천을 확정하지 않는다. 이유는 관찰 필드·코드 reason code로 연결한다.
- FP16을 초기 속도 후보로 두되 경계 사례는 FP32 및 기존 런타임과 비교한다. 수치 차이가 판정 label을 바꿀 수 있으므로 backend·dtype·batch shape·질문·규칙·모델 revision을 판정 캐시/실행 기록에 포함한다.
- `batch_size`는 한 forward pass에 넣을 **질문 수의 상한**으로 기본 16이다. 실제 행 수는 남은 질문 수에 따라 더 적을 수 있다. 다수 독립 프레임의 state batching과 같은 의미가 아니며, 각 질문 행마다 encoder 계산이 필요하다. 모델은 worker에서 재사용하고, 처음부터 여러 checkpoint를 상주시킬 필요는 없다.

이 포트는 원개발사의 공식 배포가 아닌 독립 구현이며 API 일부만 이식한다. 구현 세부 근거는 [agent.py](https://github.com/mizorewww/laya-mlx/blob/9f00d592fcf843753e6d3edd2eab63ec2b44f3c9/laya_mlx/agent.py), [confidence.py](https://github.com/mizorewww/laya-mlx/blob/9f00d592fcf843753e6d3edd2eab63ec2b44f3c9/laya_mlx/confidence.py)에 있다.

[공개 벤치마크](https://github.com/mizorewww/laya-mlx/blob/9f00d592fcf843753e6d3edd2eab63ec2b44f3c9/BENCHMARKS.md)는 M3 Max 40-core GPU, 128 GiB 환경의 특정 텍스트 질문 부하다. 스프라이트 선별 정확도나 현재 기기의 처리 시간 보장이 아니다. 가중치 다운로드·cold load 비용도 별도 측정한다.

## 구현 시 영향 범위와 완료 기준

이번에는 아래 경로를 수정하지 않았다. 실제 구현을 맡길 때 확인할 목록이다.

- `adapters/spritegen/video_processing.py`: 최종 샘플링, 관찰할 이미지 단계, 지속 시간·위상·보간 계보, 캐시 경계.
- `services/worker/video_task.py`: 원본 보존, 작업 산출물/판정 기록, 새 결과 등록 및 프로젝트 라이브러리 저장. 저장 실패는 저장만 재시도.
- `adapters/spritegen/video_provider.py` 및 영상 요청 계약: 선택 모드가 추가될 경우 기존 요청/저장 설정의 기본값 보존.
- `apps/web/src/CandidateLibrary.tsx`, `CandidateReview.tsx`, `types.ts`: 자동 추천의 출처·불확실성·이유와 기존 사용자 기록 구분. 추천이 없는 기존 프로젝트도 정상 표시.
- 기존 `test_video_processing.py`, `test_video_streams.py`, `test_video_quality_upgrade.py`, `test_video_jobs.py` 및 후보 UI 시험: VFR, 원본·보간 구분, 시간 총합, 동작 단계 누락, 모델 오류, 입력 잘림, 캐시 무효화, 라이브러리 저장·원본 보존을 검증.
- 문서/설정: 적용 backend와 모델 revision·dtype·불가 이유, 실제 측정과 제안 구분. 설명서 개편은 이번 범위에 포함하지 않는다.

오프라인 계약/규칙을 먼저 검증하고, 이후 대표 영상의 동일 후보를 대상으로 기존 방식·관찰+규칙·관찰+Laya를 비교한다. 비전 직접 판정은 비용 범위가 정해진 별도 비교군이다. 관찰 비용은 공유 캐시로 분리한다. 영상 단위 평가, false accept/reject, review 비율, 필요한 동작 단계, 최종 재생·루프, cold/warm 지연과 총비용을 기록한다.

`gpt-5.6-luna`는 제안 모델명이다. 대상 제공자에서 이미지 입력·구조화 출력 지원, 실제 사용 가능 ID와 가격을 확인한 결과는 없다. 모델명만으로 호출 가능·요금·품질을 보장하지 않는다.

## 이번 검증 범위

- 첨부 원문, 기존 대화의 6단계/승인 제거/데이터 보존 결정, 로컬 AGENTS.md와 관련 소스를 대조했다.
- Orca의 버전 일치 지침을 읽고 Grok 4.7에 읽기 전용 독립 검수를 위임했다. 검수 결과는 아래에 별도로 기록한다.
- 플랫폼/Python 버전과 프로젝트 venv의 패키지 존재 여부, `git diff --check`를 확인했다.
- 설치, 모델 다운로드, 실제 Laya/MLX/비전 호출, 후보 선별 실험, 브라우저 테스트, 코드 테스트, commit/push/merge/배포는 실행하지 않았다.

Grok 4.7 검수 완료: 기존 보정/샘플 순서, `batch_size`의 상한 의미, 잘림 처리 주체, 이미지/JSON 전달 단계 표현을 위와 같이 보완했다. 현재 실행 중 worker의 native Python과 MLX 미설치 상태를 독립 확인했다. 소스·데이터 수정이나 실제 모델 추론은 수행하지 않았다.

재현 실험에서 가중치 pin 정보를 정할 때는 포트의 [게시 기록](https://github.com/mizorewww/laya-mlx/blob/9f00d592fcf843753e6d3edd2eab63ec2b44f3c9/benchmarks/results/hub-publication.json)을 참고한다. 게시 기록의 checksum과 실제 다운로드 파일의 checksum 일치는 이번 검토에서 실행하지 않았다.
