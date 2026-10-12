# 프로젝트 폴더 저장 계약

사용자 요구: 프로젝트 하나를 폴더 하나로 복사·이동·백업하고 다시 열 수 있어야 한다. 기존 공용 저장 데이터와 작업 이력은 보존한다.

## 폴더

- 새 프로젝트 기본 위치: `SPRITE_DATA_DIR/projects/<이름>--<projectId>`; 생성 시 `parentDirectory`로 부모 폴더 선택 가능.
- `project.json`: 형식 `frame-room-project`, `formatVersion: 1`, `projectId`, `name`, `database: project.sqlite3`, 저장 버전.
- `project.sqlite3`: 현재 편집 상태, 모든 저장 이력, 이미지/영상 메타데이터, 작업·이벤트·출력 기록, 게시 전 원본의 프로젝트 소유 관계. 원본의 경로는 폴더 기준 상대 경로.
- `assets/`, `videos/`: 이 프로젝트 및 과거 이력에서 쓰는 실제 파일. 다른 프로젝트 폴더를 참조하는 링크를 사용하지 않는다.
- `jobs/`: 생성 접수·재개 체크포인트와 중간 파일. `outputs/`: 처리·내보내기 결과.
- 공용 DB는 실행 중인 앱의 목록·작업 인덱스/캐시다. 폴더만 새 앱 저장소에서 열어도 편집·이력·원본·출력을 복원할 수 있다.
- 저장 응답 전 폴더 반영을 완료한다. 실패하면 저장 성공으로 응답하지 않고 동기화 오류를 표시한다. 보류 기록은 시작 시 재반영한다.
- 폴더 이동/이름 변경은 저장과 실행 작업 완료 뒤 실제 폴더를 옮기고 새 위치를 `POST /v1/project-folders/open`으로 연다. 기존 경로에 폴더가 없으면 등록이 새 위치로 바뀌고 보류 기록도 새 위치에 반영된다. 삭제나 없는 폴더 정리를 먼저 쓰지 않는다. 누락된 폴더를 기존 경로에 조용히 다시 만들지 않는다.

## API

- `POST /v1/projects`: 기존 필드 + 선택 `parentDirectory: string`. 지정한 부모 아래 새 폴더를 만들며 기존 폴더를 덮어쓰지 않는다.
- `GET /v1/projects`, `GET /v1/projects/{pid}`의 snapshot에 `storage: {layout: 'project-folder', path: string, available: boolean, syncPending: boolean}` 제공.
- `POST /v1/project-folders/open` `{path: string}` → snapshot. 폴더 또는 그 안의 `project.json`/`project.sqlite3` 경로 허용. 파일·해시·스키마 검증 후 목록에 등록한다. 동일 경로 재열기는 멱등. 동일 ID의 다른 경로가 이미 등록돼 있으면 `PROJECT_ALREADY_OPEN` 409; 기존 경로가 없으면 이동한 경로로 재등록 가능.
- `POST /v1/project-folders/pick` `{purpose: 'open'|'parent'}` → `{path: string|null}`. 로컬 OS 폴더 선택창. 취소는 null, 미지원 OS는 명시 오류. 경로 직접 입력도 제공.
- `POST /v1/projects/{pid}/reveal`: 해당 프로젝트 폴더를 연다. `storageLayout: 'project-folder'`.
- `DELETE /v1/projects/{pid}` `{expectedRevision}` → `{deletedProjectId, folderDeleted: boolean}`: **프로젝트 삭제**. 등록·앱 인덱스·브라우저 초안과 함께 등록된 프로젝트 폴더(SQLite·원본·편집 이력·작업·출력)를 실제로 삭제한다. UI는 영구 삭제로 표시하고 확인을 받는다.
  - 진행 작업(`PROJECT_BUSY`)·저장 버전 충돌(`REVISION_CONFLICT`)·세션 토큰·Origin 검사는 기존과 같다. 폴더 동기화(flush)를 하지 않는다. 삭제 대상의 보류 기록은 함께 지운다.
  - 등록 경로에 아무것도 없으면 인덱스만 지우고 `folderDeleted: false`. 폴더를 다시 만들지 않는다.
  - 등록 경로가 있으면 다음을 모두 만족할 때만 삭제한다. 아니면 409 `PROJECT_DELETE_UNSAFE`/`PROJECT_FOLDER_MISMATCH`로 아무것도 바꾸지 않는다: 경로와 상위 경로에 심볼릭 링크가 없음(`realpath`가 등록 경로와 같음), 실제 폴더, 유효한 `project.json`의 `projectId`가 같음, 앱 저장소(`SPRITE_DATA_DIR`)를 포함하지 않음, 안쪽에 다른 등록 루트나 유효한 프로젝트 표식이 없음, 다른 디스크 마운트 없음, 모든 하위 폴더와 상위 폴더에 쓰기 권한이 있고 잠긴 파일이 없음.
  - 남는 프로젝트가 쓰는 원본의 인덱스 경로가 삭제 폴더 안이면, 해시가 같은 다른 등록 폴더의 사본으로 바꾼다. 사본은 그 등록 폴더 안의 실제 파일이어야 하며(사본 경로·상위 폴더에 심볼릭 링크 없음) 실제 위치가 삭제 폴더 밖이어야 한다. 사본이 없으면 409 `PROJECT_RESOURCE_SHARED`로 거부한다.
  - 순서: 인덱스 잠금(`BEGIN IMMEDIATE`) 안에서 검증 → 인덱스 행 삭제 → 삭제 대기 기록 `meta['project_delete:<pid>'] = {path, dev, ino}`(이름을 바꿔도 유지되는 루트 폴더의 장치·inode) → 폴더를 같은 부모의 `.<이름>.deleting-<uuid>`로 이름 변경(원자적, 파일 삭제 없음) → 커밋 → 삭제 대기 폴더 삭제 → 기록 삭제.
  - 커밋 전 실패(이름 변경 실패 503 `PROJECT_DELETE_FAILED`, 커밋 실패 포함 DB 오류)는 인덱스를 롤백하고 폴더를 원래 경로로 되돌린다. 파일은 하나도 지워지지 않는다. 되돌리기도 실패하면 503 `PROJECT_DELETE_FAILED`의 `details.leftoverPath`로 직접 옮길 경로를 알린다.
  - 커밋 후 삭제 대기 폴더 삭제가 실패하면 503 `PROJECT_DELETE_INCOMPLETE` `{projectId, leftoverPath}`. 등록은 이미 삭제됐으므로 UI는 목록·초안을 지우고 실패와 남은 경로를 표시한다. 같은 ID의 `DELETE` 또는 앱 시작(`store.init`)이 기록된 대기 경로만 다시 삭제한다. 원래 경로에 폴더가 다시 생겨도 재시도 대상이 아니다. 재시도마다 대기 경로를 `lstat`해 실제 폴더이고 `dev/ino`가 기록과 같으며 상위 경로에 심볼릭 링크가 없을 때만 삭제한다. 부분 삭제로 `project.json`이 없을 수 있어 표식은 기준으로 쓰지 않는다. 다른 폴더·파일·심볼릭 링크로 바뀌었으면 409 `PROJECT_DELETE_UNSAFE`로 거부하고 기록을 유지한다. 재시도는 인덱스 잠금 안에서 기록을 다시 확인하고, 대기 폴더 안으로 옮겨지거나 등록된 다른 프로젝트·유효한 프로젝트 표식·잠긴 파일·다른 디스크가 있거나 남는 프로젝트가 쓰는 원본의 대체 사본이 없으면 같은 409로 거부하고 기록과 폴더를 유지한다. 다른 재시도가 먼저 끝냈으면 성공으로 처리한다.
  - 한계: 파일시스템과 SQLite를 하나의 원자 작업으로 묶을 수 없다. 남을 수 있는 불일치는 "등록 삭제 + 기록된 삭제 대기 폴더 일부 남음"뿐이며 오류로 알리고 재시도한다. 휴지통 보관은 하지 않는다.
- `GET /v1/project-folders/missing` → `{projects: [{projectId, name, path, revision}]}`. 루트 폴더 자체가 사라진 등록만 대상이며 내부 파일 손상은 이 정리 대상이 아니다.
- `POST /v1/project-folders/cleanup` `{projects: [{projectId, expectedRevision, path}]}` → `{removedProjectIds, removedCount}`. 비어 있는 목록은 아무것도 지우지 않는다. 미리 확인한 ID·버전·경로와 폴더 부재를 트랜잭션에서 다시 확인한다. 다시 생긴 폴더·진행 작업·버전/경로 변경은 409로 전체 정리를 거부한다. 물리 파일은 삭제하지 않으며 존재하는 폴더는 건드리지 않는다. 개별 `DELETE`와 다르다. UI 버튼 `없는 폴더 정리`에서 명단·경로를 보여준 뒤 실행한다.
- 인덱스 제거 시 관련 프로젝트·이력·작업·이벤트·출력·묶음 제출 캐시를 정리한다. 어떤 등록 프로젝트의 현재/과거 상태에서도 사용하지 않는 자산·영상 인덱스도 정리하되, 진행 중인 작업이 있으면 그 임시 원본을 보존한다. 없는 폴더 정리에서는 폴더 원본과 SQLite를 건드리지 않는다.
- 폴더 열기는 외부 AI 호출을 하지 않는다. 가져온 대기/실행 중 작업을 자동으로 다시 실행하지 않는다.
- 세션 토큰·Origin 보호를 유지한다. 폴더 DB의 임의 SQL은 실행하지 않고 정해진 테이블/필드만 읽는다. 경로 탈출·외부 심볼릭 링크·누락/변조 리소스를 거부한다.

## 구현 연결

저장 계층 인터페이스: `store.project_folder(pid, c=None)`, `store.public_project(snapshot)`, `store.job_directory(jid)`, `store.artifact_directory(jid)`, `store.resolve_work_path(jid, stored_path)`. 작업이 프로젝트에 속하지 않으면 기존 공용 임시 작업 폴더를 쓴다. `store.project_scope(pid)` 안에서 새 자산을 프로젝트 폴더에 기록한다.

폴더 서비스: `project_folders.open_project(path)`, `project_folders.delete_project(pid, expected_revision)`, `project_folders.finish_pending_deletions()`(시작 시), `project_folders.missing_projects()`, `project_folders.cleanup_missing(items)` (`items`는 위 body의 projects dict 목록). `store.create_project(..., parent_directory=None)`.

## 수용 검증

기존 프로젝트의 snapshot/이력·파일 해시를 이전 전후 비교한다. 실제 프로젝트 폴더만 독립 저장소로 복사해 열기·편집·영상 읽기·과거 출력 다운로드·bake를 검증한다. 폴더 이동 뒤 새 위치 열기, 개별 삭제(없는 폴더·실제 폴더·거부 조건·부분 실패 복구), 다른 프로젝트 원본 보존, 충돌/손상/진행 작업/저장 실패 처리를 검사한다. 실제 생성 요청은 보내지 않는다.
