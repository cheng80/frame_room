"""Own and reap API, worker and optional Vite process groups."""
import argparse,fcntl,os,signal,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--dev',action='store_true');args=parser.parse_args()
os.chdir(ROOT);(ROOT/'.data').mkdir(exist_ok=True)
lock=open(ROOT/'.data/launcher.lock','a+')
try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError: raise SystemExit('앱이 이미 실행 중입니다: http://127.0.0.1:8765')
commands=[[sys.executable,'-m','services.worker.main'],[sys.executable,'-m','uvicorn','services.api.main:app','--host','127.0.0.1','--port','8765']]
if args.dev: commands.append(['npm','--prefix','apps/web','run','dev','--','--host','127.0.0.1','--strictPort'])
env={**os.environ,'PYTHONPATH':str(ROOT),'PYTHONDONTWRITEBYTECODE':'1'}
children=[];stop=False
def shutdown(*_):
    global stop;stop=True
signal.signal(signal.SIGINT,shutdown);signal.signal(signal.SIGTERM,shutdown)
try:
    for argv in commands: children.append(subprocess.Popen(argv,cwd=ROOT,env=env,start_new_session=True))
    url='http://127.0.0.1:'+('5173' if args.dev else '8765')
    print('프레임룸: '+url,flush=True)
    launched=time.monotonic();opened=False
    while not stop:
        if any(p.poll() is not None for p in children):
            print('서비스가 종료되었습니다. 위 오류를 확인하세요.',file=sys.stderr);break
        if not opened and time.monotonic()-launched>2 and os.environ.get('SPRITE_OPEN_BROWSER','1')=='1':
            try:
                with urllib.request.urlopen(url,timeout=1) as r:
                    if r.status==200: subprocess.Popen(['open',url]);opened=True
            except OSError: pass
        time.sleep(.3)
finally:
    for p in children:
        try: os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError: pass
    deadline=time.monotonic()+7
    while any(p.poll() is None for p in children) and time.monotonic()<deadline: time.sleep(.1)
    for p in children:
        try: os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        p.wait()
