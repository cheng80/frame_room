from pathlib import Path
import importlib, json, sys, hashlib
ROOT=Path(__file__).resolve().parents[1]
for name in ['fastapi','uvicorn','PIL','numpy','sprite_gen']:
    module=importlib.import_module(name)
    if name=='sprite_gen' and not Path(module.__file__).resolve().is_relative_to(ROOT/'engine/sprite-gen'):
        raise SystemExit('ERROR: 프로젝트 외부의 sprite-gen을 읽고 있습니다.')
    print(f'OK {name}')
lock=ROOT/'engine/engine-lock.json'
if not lock.exists(): raise SystemExit('ERROR: engine-lock.json 누락')
pin=json.loads(lock.read_text())
if pin['commit']!='b058341f7543f3adcbea227bd4e6b7587895b1bc': raise SystemExit('ERROR: 엔진 기준 commit 불일치')
inventory=json.loads((ROOT/'engine/upstream-files.sha256.json').read_text())
patches={p['path']:p['forkSha256'] for p in pin['patches']}
for name,expected in inventory.items():
    path=ROOT/'engine/sprite-gen'/name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=patches.get(name,expected):
        raise SystemExit('ERROR: 엔진 소스 해시 불일치: '+name)
print(f'OK 엔진 원본/승인 패치 {len(inventory)}파일 무결성')
(ROOT/'.data').mkdir(exist_ok=True)
print('OK 전용 엔진·저장 위치 준비')
