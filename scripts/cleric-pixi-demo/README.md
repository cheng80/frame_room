# 여성 신관 PixiJS 데모

PixiJS `8.20.1` 로컬 브라우저 번들을 사용합니다. CDN이나 생성 API 의존성은 없습니다. `vendor/LICENSE.txt`에 번들 MIT 라이선스를 포함합니다. `cleric-atlas.json`, `cleric-manifest.json`, `cleric-atlas.png`를 이 폴더에 복사한 뒤 이 폴더에서 정적 HTTP 서버를 실행해 여세요. 브라우저의 `file://` 정책은 JSON fetch를 차단할 수 있습니다.

```sh
python3 -m http.server 8000
```

`http://localhost:8000/`에서 확인합니다. deliverable 디렉터리로 옮길 때 `index.html`, `main.js`, `controls.js`, `vendor/pixi.min.js`, `vendor/LICENSE.txt`와 atlas·manifest·PNG 세 파일을 함께 복사합니다. JSON의 `meta.image`는 atlas PNG 경로를 가리켜야 합니다.

manifest의 `durationsMs[index]`를 먼저 사용하며 값이 없으면 atlas frame `duration`, 둘 다 없으면 100ms를 사용합니다. 키 입력 수학은 브라우저 없이 검사할 수 있습니다.

```sh
npm run verify
```

스프라이트 생성·추출은 상위 `cleric-eightway.py`를 사용합니다. `--stage match-walks`는 저장된 Grok 영상만 재처리해 모든 걷기를 1초·8프레임으로 맞춥니다. `--stage pack`은 PNG/JSON 및 동작별 파일을 내보내고 기존 출력은 `delivery-history/`에 보존합니다. `verify-cleric-eightway.py`는 실제 결과와 원본 기록의 일치·여백·프레임 수를 검사합니다. 생성 원본과 인증·영상은 Git에 포함하지 않습니다.

`harmonize-cleric-eightway.py --out <별도 출력 폴더>`는 기존 완성 시트의 동작·시간을 보존하면서 지팡이를 제외한 후드~부츠 높이를 112px 기준으로 맞추고, 검수한 머리 영역의 주요 금발 색상을 공통 팔레트로 치환합니다. 폭이 좁아 작게 보이는 N 방향은 걷기·대기 모두 추가로 6% 확대합니다. 클립마다 같은 배율을 사용하고 원본은 덮어쓰지 않습니다. 알파·색상 영역 밖 보존·여백·첫 포즈 목표 높이를 실제 처리 중 assert로 검사하고 `harmonization.json`과 마스크 검수판을 기록합니다. 좌표와 보호 영역은 이 성직자 전용이며 다른 캐릭터에 재사용하면 안 됩니다.

외부 배경 이미지 없이 화면에 등각 격자만 그립니다. `window.__clericDemo.getState()`는 현재 상태를 반환하고 `press(key)`, `release(key)`, `tick(seconds)`는 자동화용 입력·ticker 제어입니다.

W 대기는 얼굴 처짐이 적은 원본 39번의 감긴 눈을 125ms 표시하고 45번의 뜬 눈으로 돌아옵니다. `--idle-s-record <complete.json>`은 같은 S 기준 그림으로 다시 만든 Grok 대기를 적용합니다. `retake-cleric-idle-S.py quieten`은 저장된 영상에서 덜 흔들리는 `0,18,20,35,38,51,54,63`번을 별도 선택하고 눈감기 167ms·전체 3초·8장을 유지합니다. 원본 시간과 조정된 재생 시간은 별도로 기록하며 새 생성 요청은 하지 않습니다.

`retake-cleric-walk-E.py`는 기존 E 기준 그림에서 앞쪽 오른팔의 지팡이 연결을 유지하도록 걷기를 한 번 다시 생성하고, 시각 검수 후 1초·8장으로 확정합니다. `--walk-e-record <complete.json>`으로 적용합니다. 생성 도구는 checkpoint를 재사용하며 원본과 이전 출력은 보존합니다. 출처·프레임 선택·재생 시간은 manifest의 `harmonization.motionCorrections`와 각 동작의 `selection`에 기록합니다.

Cloudflare 공개 배포는 저장소 루트에서 다음 순서로 실행합니다. Wrangler 로그인과 `fastmake.net` 계정 권한이 필요합니다.

```sh
engine/sprite-gen/.venv/bin/python scripts/cleric-pixi-demo/prepare-public.py output/cleric-quarterview-8way/delivery-motion-refined-v2
npx wrangler@4.148.0 deploy --config scripts/cleric-pixi-demo/wrangler.jsonc
```

`prepare-public.py`는 HTML·JS·로컬 Pixi 번들/라이선스·atlas PNG/JSON·런타임 전용 manifest만 `dist/`에 준비합니다. 생성 요청 ID·로컬 경로·검수 자료·영상·기준 그림은 공개하지 않습니다. 기존 `dist/`가 있으면 덮어쓰지 않으므로 이전 패키지를 별도 보관한 뒤 실행하세요. `wrangler.jsonc`는 정적 파일을 `https://cleric.fastmake.net`에 연결하며 별도 Worker 코드는 없습니다. 생성 이미지와 공개 패키지는 Git에서 제외하고, 소스와 배포 설정만 커밋합니다.
