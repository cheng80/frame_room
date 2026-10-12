# 별도 생성·보정 동작의 프로젝트 저장

8방향 성직자 작업은 앱 작업 큐 대신 별도 제작 스크립트에서 진행되어 PNG/JSON만 남고 프로젝트 라이브러리에는 등록되지 않았다. 생성·보정 결과의 완료 조건을 파일 생성과 프로젝트 폴더 저장 모두로 변경한다.

## 저장 계약

- `cleric-eightway.py`의 동작 생성·기존 결과 재사용·주기 맞춤·시트 묶음, `harmonize-cleric-eightway.py`, 성직자 S/E 보정 스크립트는 공통 `scripts/project_library.py`를 통해 저장한다.
- 출력 루트의 `project-library.json`에 프로젝트 ID와 앱 데이터 위치를 연결한다. 처음에는 `--project-id`가 필요하고 이후 같은 폴더의 단계는 연결을 재사용한다. 대상이 없거나 목록에서 제거됐거나 다른 프로젝트와 연결됐으면 생성 요청 전에 중단한다. 목록에서 제거한 프로젝트는 먼저 폴더를 다시 연다.
- 라이브러리는 최종 셀 PNG, 프레임, 앵커, 슬롯 순서·개별 재생 시간, 방향별 기준 그림과 원본 영상 연결을 함께 저장한다. 수동 승인은 자동 부여하지 않는다.
- 새 동작에는 정규화·색상 마무리, 구간 선택·시간 조정과 방향별 보정 정보를 `libraryProcessing`으로 보존한다. 생성 요청의 로컬 파일 경로나 인증 자료는 복사하지 않는다. S/E 생성 단계의 후보도 검수 대기 동작으로 저장하며, 검수 후 확정·보정은 같은 저장 경로를 사용한다.
- 같은 프레임·시간·앵커·원본의 재시도는 기존 동작 ID를 사용한다. 새 보정 결과 또는 기존 동작에 사용자 편집이 있으면 새 동작으로 추가하고 기존 동작과 이력을 보존한다.
- 저장 트랜잭션과 프로젝트 폴더 반영을 마친 뒤 실제 폴더 DB를 다시 읽고 프레임·시간 연결을 확인한다. 성공 시 결과 폴더의 `library-publication.json`에 프로젝트 ID, 저장 버전과 동작 ID를 기록한다. 이 검증 이전에는 완료를 출력하지 않는다.
- 파일은 완성됐지만 저장이 실패하면 파일과 생성 체크포인트를 보존한다. 저장 재시도는 기존 파일을 읽으며 새 GPT/Grok 요청을 보내지 않는다.
- 앱의 `generate_video`, `process_video`, `apply_follow`도 빈 동작이나 끊어진 프레임 연결을 `LIBRARY_PUBLICATION_INCOMPLETE`로 거부한다. 앱 결과 저장은 기존 작업 트랜잭션·폴더 저장 경로를 사용한다.

## 실행

저장소 루트에서 프로젝트 목록의 대상 프로젝트 ID로 처음 연결한다.

```sh
engine/sprite-gen/.venv/bin/python scripts/cleric-eightway.py --stage clips --project-id <projectId>
engine/sprite-gen/.venv/bin/python scripts/cleric-eightway.py --stage pack
engine/sprite-gen/.venv/bin/python scripts/harmonize-cleric-eightway.py --out <별도-보정-출력-폴더>
```

성직자 복원 프로젝트 `0f699bdc-1002-443f-ab9d-8128068adf31`은 기존 `output/cleric-quarterview-8way`와 연결했다. 최종 16개 동작의 같은 내용을 다시 저장해 중복 추가·저장 버전 증가 없이 기존 라이브러리 연결을 확인했다.

저장 실패 후 파일만 다시 등록할 때:

```sh
engine/sprite-gen/.venv/bin/python scripts/project_library.py --run output/cleric-quarterview-8way --delivery output/cleric-quarterview-8way/delivery-motion-refined-v2
engine/sprite-gen/.venv/bin/python scripts/project_library.py --run output/cleric-quarterview-8way --record <완성된-complete.json>
```

원본 보호 때문에 기존 출력 폴더를 덮어쓸 수 없는 보정 스크립트도 이 저장 전용 명령으로 재개한다. 연결 정보를 지우거나 다른 프로젝트로 임의 전환해서 재시도하지 않는다.

## 검증

`tests/integration/test_standalone_library.py`: 라이브러리 저장·폴더 재열기, 동일 결과 재시도, 사용자 시간 편집 보존, 저장 실패 롤백·재개, 대상 누락·충돌 차단, checkpoint 출력이 앱 데이터 루트를 바꾸지 않는지, manifest 재생 시간 보존과 생성 전 대상 확인을 검사한다. 시험 이미지는 합성 fixture이며 GPT 결과로 소개하지 않는다.

`tests/integration/test_animation_publication_guard.py`: 앱 영상 생성·처리·보정의 빈 결과가 동작 없이 완료되지 않으며 프로젝트·작업·이력 기록이 롤백되는지 검사한다. 실제 유료 생성은 이 변경 검증에 사용하지 않는다.
