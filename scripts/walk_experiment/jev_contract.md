# Jev 보행 관측 비교 sidecar 계약

계약 확인일: 2026-10-04. 앱과 연결하지 않는 Python 표준라이브러리 CLI다.
이 계약을 먼저 확정하고 `jev_compare.py`를 구현한다.

## 공식 근거

- [HTTP API](https://docs.typesafe.ai/api.md): `POST https://api.typesafe.ai/v1/systemone`, Bearer 인증, `state/model/questions`, `answers/model/usage`.
- [Choice](https://docs.typesafe.ai/primitives/choice.md): `criteria` 옵션 맵, 응답 `choice/probabilities/confidence`.
- [Noul](https://docs.typesafe.ai/primitives/noul.md): `criteria.true/false`, 응답 `noul`; 별도 confidence 없음.
- [State](https://docs.typesafe.ai/concepts/state.md): 모든 질문이 같은 state를 보고 독립적으로 응답.
- [Models](https://docs.typesafe.ai/models.md): 텍스트 전용. 재현성을 위해 문서에 등재된 `jev-1.13.0` 고정. 응답 모델도 따로 기록.
- [Choice 비교 cookbook](https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook.md): 분포와 불확실성을 보존하고 비교한다. cookbook의 반복 유료 호출과 예시 임계값은 적용하지 않는다.

공개 문서만 읽었다. 모델 목록 조회, 인증 검사, doctor, 평가 API 호출은 구현 작업에서 수행하지 않는다.

## CLI / 입력

```bash
python3 scripts/walk_experiment/jev_compare.py \
  --observations /absolute/path/observations.json \
  --output /absolute/path/jev-request.json

# 아래는 부모 작업자가 승인된 유료 실행 시 사용할 명령이다.
python3 scripts/walk_experiment/jev_compare.py \
  --observations /absolute/path/observations.json \
  --output /absolute/path/jev-result.json \
  --env-file /absolute/path/.env --execute
```

Python 3.9 이상. 기본은 네트워크·키 로딩 없는 dry-run이며 출력 파일에는 **HTTP 요청 JSON 본문만** 저장한다.
`--execute`만 평가 요청을 보낸다. 환경변수 `TYPESAFE_API_KEY`를 우선 사용하고, 없으면 명시한 env 파일에서 같은 키만 읽는다.
env 파일을 shell로 실행하지 않으며 변수·명령 치환, escape 처리, 다른 키의 환경변수 주입을 하지 않는다.
한 줄 `KEY=value`, 선택적 `export`, 단일/이중 따옴표, 값 뒤 공백과 `#` 주석을 지원한다. 대상 키 중복·치환 문법·공백 포함 키 값은 거부한다.
dry-run에서는 `--env-file`도 읽지 않는다.

```json
{
  "frames": [
    {
      "id": "sample-a",
      "observation": "The figure faces screen right. The camera-near leg extends forward with the heel at ground level. The camera-far leg trails with its toe on the ground.",
      "baseline_phase": "near_contact",
      "baseline_confidence": 0.8
    }
  ]
}
```

위 텍스트는 입력 형식 예시이며 실제 이미지를 관측한 결과가 아니다.

- `frames`: 1–16개. `id`: 중복 없는 비어 있지 않은 문자열(최대 256자) 또는 정수. `observation`: 비어 있지 않은 텍스트, UTF-8 최대 2,000바이트.
- `baseline_phase`: 생략/null 또는 아래 9개 라벨. `baseline_confidence`: 생략/null 또는 유한한 0–1 숫자. boolean은 숫자로 받지 않는다.
- 다른 필드는 무시한다. `id`와 baseline은 로컬 결과 조인용이며 요청에 넣지 않는다.
- 관측문은 비전이 **원본 또는 출처를 기록한 에디터 보정 이미지를 보고** 작성한 중립적 영어/한국어 증거여야 한다. 지면 접촉, 무릎 굽힘, 발의 몸통 대비 앞뒤 위치, 몸통 높이, 가림과 불확실성을 기술한다. 해부학적 left/right는 추정하지 않는다.
- 관측문 자체에 정답/요청 단계, 순번, 파일명, 생성 프롬프트, credentials를 넣지 않는다. CLI는 임의 자연어 속 누출을 완전 검출할 수 없다. 입력 작성자가 원본과 관측 출처를 보관한다.
- 원래 배열 순서를 노출하지 않도록 **관측문 SHA-256 순**으로 정렬하여 `state.observations`에 문자열만 담는다. 동일 관측문끼리의 순서는 판정 증거를 바꾸지 않는다. 질문은 해당 배열 위치만 참조한다.
- 각 질문은 해당 관측문만 판정하며 다른 프레임이나 배열 순서로 보행 순서를 보충하지 않도록 지시한다. 모든 관측문이 같은 state에 있으므로 모델 수준의 완전한 프레임 격리는 보장하지 않는다.

## 보행 Choice의 9개 옵션

고정된 카메라에서 **화면 오른쪽을 향한 제자리 걷기**를 대상으로 한다. 앞은 화면 오른쪽, 뒤는 왼쪽이다.
`near`는 카메라쪽 다리, `far`는 반대쪽 다리이며 해부학적 왼쪽/오른쪽과 대응시키지 않는다.
접두사는 해당 반주기 시작에서 앞으로 접촉한 다리이며, down/passing/up 동안 그 다리가 지지 역할을 이어간다.
아래는 실험용 8포즈 정의다. 단일 정지 영상만으로 속도·수직 운동·제자리 여부를 입증하지 않는다.

| 라벨 | 판정 기준 |
| --- | --- |
| `near_contact` | near 발이 몸 앞에서 지면에 닿기 시작한 자세(보통 뒤꿈치), far 발은 뒤에서 발끝으로 지면에 접촉. 두 다리가 앞뒤로 벌어짐. 아직 down의 뚜렷한 압축 자세가 아님. |
| `near_down` | near 발이 앞쪽에서 체중을 받고 무릎이 굽으며 몸이 낮아진 자세. far 발은 뒤에서 지면을 떠나기 시작함. far 무릎/발이 지지 다리 옆을 통과하는 passing 전. |
| `near_passing` | near 다리가 몸 아래에서 지지하고 far 다리는 무릎을 굽힌 채 공중에서 지지 다리 옆을 통과. 발의 앞뒤 간격이 작고 두 발 동시 접촉은 아님. |
| `near_up` | near 지지 다리가 몸 뒤에서 펴지고 뒤꿈치가 들리며 몸이 높아진 자세. far 다리는 몸 앞으로 뻗는 중이지만 아직 지면에 닿지 않음. far 접촉 직전. |
| `far_contact` | far 발이 몸 앞에서 지면에 닿기 시작한 자세(보통 뒤꿈치), near 발은 뒤에서 발끝으로 지면에 접촉. 아직 뚜렷한 압축 자세가 아님. |
| `far_down` | far 발이 앞쪽에서 체중을 받고 무릎이 굽으며 몸이 낮아진 자세. near 발은 뒤에서 지면을 떠나기 시작함. near 다리가 지지 다리 옆을 통과하기 전. |
| `far_passing` | far 다리가 몸 아래에서 지지하고 near 다리는 무릎을 굽힌 채 공중에서 지지 다리 옆을 통과. 발의 앞뒤 간격이 작음. |
| `far_up` | far 지지 다리가 몸 뒤에서 펴지고 뒤꿈치가 들리며 몸이 높아진 자세. near 다리는 앞으로 뻗지만 아직 접촉하지 않음. near 접촉 직전. |
| `unknown` | near/far 식별, 지지/유각, 접촉, 방향 또는 인접 단계 구별에 필요한 증거가 부족/모순됨. 가려진 다리를 임의 추론하거나 요청 단계를 따라가지 않는다. 달리기·서 있기·왼쪽 향하기 등 대상 외 자세도 포함. |

주기는 `near_contact → near_down → near_passing → near_up → far_contact → far_down → far_passing → far_up`이다.
이 순서를 프레임 번호에 적용하지 않는다. 몸의 높이 단서만으로 단계를 확정하지 않는다.

## 같은 요청의 usable Noul

프레임마다 phase Choice와 별도 `usable` Noul을 함께 묻는다. 방향·다리·접촉 관계가 판독 가능하고, **에디터 정렬 후 주요 요소와 대체로 같은 스타일을 유지하는가**가 기준이다.
머리·스카프·견갑·조끼·검·부츠가 유지되는지 보며, 미세 픽셀·명암·디테일·자연스러운 포즈 차이는 허용한다. 모든 픽셀과 세부 표현의 일치를 요구하지 않는다. 주요 요소가 빠지거나 스타일이 뚜렷하게 바뀌면 외형 실패다.
다리 구분이나 접촉 관계가 불확실하면 보행 사용 가능성은 미확정으로 남는다. 외형 통과와 보행 판독 가능성은 별도로 기록한다.
이는 **관측문 기반 사용 가능성의 확률**이다. Jev는 이미지를 볼 수 없고 실제 보행 자연스러움이나 전체 애니메이션을 검증하지 못한다. phase 결과와 독립적이며 API 결과만으로 자동 승인하지 않는다.

## 요청과 응답 검증

요청은 `{ "model": "jev-1.13.0", "state": {"observations": [...]}, "questions": {...} }`다.
`phase_000`는 `{type:"choice", instructions:..., criteria:{9개 옵션...}}`,
`usable_000`는 `{type:"noul", instructions:..., criteria:{"true":...,"false":...}}`이며 뒤 번호는 정렬된 관측 위치다.
옵션과 지침은 모든 프레임에 동일하게 적용한다. 실제 전송 본문은 dry-run으로 검토할 수 있다.

실제 HTTP 성공 본문도 다음을 **모두 검증한 뒤** 결과로 채택한다.

- JSON 객체, 중복 JSON 키와 NaN/Infinity 금지. 응답 모델은 `jev-`로 시작하는 제한된 모델명 문자열.
- `answers` 키 집합이 요청 질문 키 집합과 정확히 같아야 한다.
- Choice: `type == "choice"`, 9개 중 `choice`, 9개 옵션 전체의 `probabilities`, 유한한 0–1 `confidence`.
- 각 확률은 boolean이 아닌 유한한 0–1 숫자. 합은 원칙적으로 1과 절대오차 0.001 이내다. 실응답처럼 모든 확률이 소수 둘째 자리까지 반올림된 경우에만 항목당 0.005의 반올림 오차(9개 최대 0.045)를 허용한다. 선택은 최대 확률 옵션(오차 0.000001, 동률 허용)이어야 한다. 정규화·라벨 교정 없음.
- Noul: `type == "noul"`, 유한한 0–1 `noul`. `value`/`probability` 같은 대체 필드는 허용하지 않는다.
- `usage.input_tokens/output_tokens`: boolean이 아닌 0 이상의 정수. 다른 확장 필드는 저장하지 않는다.

성공 출력에는 `schema_version`, `status`, `requested_model`, 응답 `model`, 검증한 `usage`, HTTP 상태, 실제 시도 수, `latency_ms`, UTC 시각, 요청 SHA-256과 입력 순서의 `frames`를 기록한다.
각 프레임은 로컬 `id/baseline_phase/baseline_confidence`, Jev `phase/confidence/probabilities/usable_noul`, `agrees_with_baseline`을 가진다. baseline이 없으면 일치 여부는 null이다.
`baseline_phase`는 vision 라벨이다. 비교는 **vision 라벨과의 agreement**이며 ground truth나 phase accuracy가 아니다. 두 confidence의 보정도 동일하다고 가정하지 않는다. 모델이 선택한 `unknown`과 API/파싱 실패를 구분한다.

## 비용·보안·실패 계약

- 실행당 최대 **1회 POST / 최대 32개 질문**. SDK, 자동 재시도, 429/529 재시도, 모델 fallback, 자동 분할 없음.
- 입력 파일 256 KiB, state 16 KiB, 전체 요청 64 KiB, 성공 응답 1 MiB 제한. 바이트 제한은 로컬 실험 예산이며 정확한 토큰 계산이나 비용 보장은 아니다. 초과는 호출 전에 실패한다.
- HTTPS 호스트와 경로 고정, TLS 인증서 검증. 프록시 환경변수·redirect를 사용하지 않는다. 소켓 timeout 30초; 이는 각 blocking I/O의 제한이며 전체 wall-clock 상한은 아니다.
- HTTP 오류는 상태 코드만 기록하고 **오류 본문을 읽거나 저장하지 않는다**. 예외 원문, 헤더, credentials, raw 성공 본문도 저장/출력하지 않는다. 알려진 인증키가 전송/저장 대상 데이터에 섞이면 실행을 거부한다.
- 출력은 새 파일만 생성(0600), 기존 파일·symlink를 덮어쓰지 않는다. 출력 부모 디렉터리는 미리 있어야 한다. 실행 전에 `not_started` 보고서를 기록한 후 `in_flight`를 기록하고 호출한다. 중단/디스크 오류로 `in_flight`가 남으면 과금 여부 미상으로 취급하며 자동 재실행하지 않는다.
- 실패 보고서는 안전한 오류 코드와 latency, 시도 수를 기록한다. 응답 검증 실패 시 `model/usage`는 null이고 유료 평가가 수행되었을 가능성이 있다. 사용량을 0으로 꾸미지 않는다.
- 종료 코드: 0 dry-run/성공, 1 실행 중 HTTP/전송/응답 오류, 2 입력·키·출력 파일 준비 오류. 오류 메시지는 입력/키/서버 본문을 반사하지 않는다.

## 최초 구현 검증 범위

2026-10-04: 메모리 내 `compile()` 문법 검사 및 표준라이브러리 `unittest/mock` **17개 테스트 통과**. 테스트 중 소켓 생성을 차단했고, 출력 파일 I/O도 메모리로 대체하여 별도 테스트 파일이나 결과 파일을 만들지 않았다.

- dry-run 요청 본문 일치, 키 미로딩·무호출, 요청의 ID/baseline/파일명 제외, 입력 순서가 달라도 동일한 요청.
- mock 성공 응답의 원래 ID 연결, usage/model/latency와 baseline agreement 기록, 당시의 identity 기준과 미확인 no 지침(외형 기준은 이후 사용자 지시에 따라 위와 같이 완화).
- 누락/추가 질문, 잘못된 type/라벨/확률합/argmax/confidence/Noul/usage, 중복 JSON 키와 비유한값 거부. `unknown`과 최대 확률 동률 허용.
- HTTP 301/307/401/422/429/500/529에서 오류 본문 미열람·재시도 없음, timeout/전송/예상 밖 예외 원문 비노출.
- 인증키의 일반/Unicode escape 응답 반사 거부, provider 추가 필드 미보관, `.env` 우선순위·안전 파싱, 입력·응답 크기 제한.
- 기존 출력 경로와 입력의 알려진 인증키를 호출 전에 거부. 파일 생성 플래그 `O_EXCL`과 권한 0600 확인(mock).

이 최초 검증에는 실제 인증·네트워크 평가·판정 정확도·보행 품질이 포함되지 않았다.

## 제작 실험에서 추가 확인

실제 호출은 `.data/experiments/walk-candidates-20261004/` 영수증으로 기록했다. 1차 관측 3회와 정렬 후 관측 4회 중 6회가 검증 성공했다. 나머지 1회는 HTTP 200 이후 로컬 확률합 검사에서 거부했으며, 그 호출의 usage는 보관하지 못해 비용이 미상이다. 이를 모델 판단 실패나 무과금으로 계산하지 않는다. 반올림 허용 범위를 수정한 뒤 명시적으로 새 호출했으며 자동 재시도는 없다.

정렬 후 최종 비교에는 수정된 외형 기준을 사용한 성공 3회(24후보)만 포함한다. 1차 관측 및 로컬 검증 실패 영수증은 감사용으로 보존하며 최종 판정과 섞지 않는다. `test_jev_contract.py`는 반올림 허용과 잘못된 확률합·argmax 거부를 재현한다. 모델 간 unknown 일치는 보행 정확도나 유료 서비스의 일반적인 효용을 증명하지 않는다.
