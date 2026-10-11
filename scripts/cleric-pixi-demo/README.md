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

`harmonize-cleric-eightway.py --out <별도 출력 폴더>`는 기존 완성 시트의 동작·시간을 보존하면서 지팡이를 제외한 후드~부츠 높이를 112px로 맞추고, 검수한 머리 영역의 주요 금발 색상을 공통 팔레트로 치환합니다. 클립마다 같은 배율을 사용하고 원본은 덮어쓰지 않습니다. 알파·색상 영역 밖 보존·여백·첫 포즈 높이를 실제 처리 중 assert로 검사하고 `harmonization.json`과 마스크 검수판을 기록합니다. 좌표와 보호 영역은 이 성직자 전용이며 다른 캐릭터에 재사용하면 안 됩니다.

외부 배경 이미지 없이 화면에 등각 격자만 그립니다. `window.__clericDemo.getState()`는 현재 상태를 반환하고 `press(key)`, `release(key)`, `tick(seconds)`는 자동화용 입력·ticker 제어입니다.
