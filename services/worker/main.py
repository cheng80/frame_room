from __future__ import annotations
import fcntl,json,mimetypes,os,signal,subprocess,sys,time
from services.api import store as s

TERMINAL={'succeeded','needs_review','failed','interrupted','provider_outcome_unknown','canceled'}
STOP=False

def beat():
    with s.connect() as c: c.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',('worker_heartbeat',str(time.time())))

def group_members(pgid):
    rows=subprocess.run(['ps','-axo','pid=,pgid=,stat='],capture_output=True,text=True).stdout.splitlines()
    members=[]
    for row in rows:
        values=row.split()
        if len(values)>=3 and values[1]==str(pgid) and not values[2].startswith('Z'): members.append(int(values[0]))
    return members

def terminate_group(pgid):
    if not pgid or pgid==os.getpgrp(): return
    try: os.killpg(pgid,signal.SIGTERM)
    except ProcessLookupError: return
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        if not group_members(pgid): return
        time.sleep(.05)
    try: os.killpg(pgid,signal.SIGKILL)
    except ProcessLookupError: pass
    deadline=time.monotonic()+2
    while group_members(pgid) and time.monotonic()<deadline: time.sleep(.05)
    if group_members(pgid): raise RuntimeError('process group did not terminate')

def recover():
    with s.connect() as c: rows=c.execute("SELECT body FROM jobs WHERE status IN ('running','cancel_requested')").fetchall()
    for row in rows:
        j=json.loads(row[0]); pid=j.get('childPid')
        if pid:
            command=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True).stdout
            if not command.strip() or ('services.worker.task' in command and j['jobId'] in command): terminate_group(pid)
        result_path=s.DATA/'jobs'/j['jobId']/j['attemptId']/'result.json'
        payload=json.loads(result_path.read_text()) if result_path.exists() else None
        if payload and payload.get('ok'):
            try:
                publish(j,payload)
                continue
            except Exception:
                pass  # Preserve the completed files for explicit local recovery.
        with s.transaction() as c:
            current=s.get_job(j['jobId'],c)
            current['status']='provider_outcome_unknown' if j['operation']=='generate' and j.get('externalStarted') else 'interrupted'
            if payload and payload.get('providerCheckpoint'):
                current['status']='failed'
                current['result']={'receipt':payload['providerCheckpoint']['providerResult']['receipt']}
                current['providerCheckpoint']=True
            current['errors']=[dict(code='WORKER_INTERRUPTED',message='작업 처리기가 중단되었습니다. 저장된 원본과 이전 결과는 보존됩니다.',stage=j.get('step'))]
            s.write_job(c,current)

def claim():
    with s.transaction() as c:
        row=c.execute("SELECT body FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if not row: return None
        j=json.loads(row[0]); j.update(status='running',step=j['operation'],lease={'workerPid':os.getpid(),'startedAt':s.now()},externalStarted=j['operation']=='generate')
        if j['operation']=='export':
            export=c.execute('SELECT id FROM exports WHERE job_id=?',(j['jobId'],)).fetchone()
            if not export: return None
            j['exportId']=export[0]
        s.write_job(c,j); return j

def publish(j,payload):
    out=s.DATA/'jobs'/j['jobId']/j['attemptId']/'staging'
    result=payload['result']; files=result.get('files',[])
    published=s.DATA/'artifacts'/j['jobId']/j['attemptId']
    published.parent.mkdir(parents=True,exist_ok=True)
    # Recover a validated directory rename that completed before its DB transaction.
    if not out.exists() and published.exists(): out=published
    # Check every bundle member before making the directory visible.
    for item in files:
        name=item if isinstance(item,str) else item['name']
        path=(out/name).resolve()
        if not path.is_relative_to(out.resolve()) or not path.is_file(): raise s.AppError('ARTIFACT_MISSING','필수 출력 파일이 없습니다.',424)
        expected=result.get('publicationHashes',{}).get(name) or next((x['sha256'] for x in result.get('fileHashes',[]) if x['name']==name),None)
        if expected and s.digest(path.read_bytes())!=expected: raise s.AppError('ARTIFACT_HASH','완료된 출력 파일이 변경되었습니다.',424)
    if out!=published: os.replace(out,published)
    with s.transaction() as c:
        current=s.get_job(j['jobId'],c)
        if current['status']=='cancel_requested':
            if j['operation']=='generate' and result.get('receipt'): current['cancelOutcome']='completed-before-cancel'
            else:
                current['status']='canceled'; s.write_job(c,current); return
        arts=[]
        for item in files:
            name=item if isinstance(item,str) else item['name']; path=published/name; aid=s.uid(); sha=s.digest(path.read_bytes()); media=mimetypes.guess_type(name)[0] or 'application/octet-stream'
            c.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?)',(aid,j['jobId'],name,str(path.relative_to(s.DATA)),sha,media))
            arts.append(dict(artifactId=aid,name=name,url=f'/v1/artifacts/{aid}/download',sha256=sha,mediaType=media))
        if j['operation']=='restore':
            p=result.pop('restoredProject'); s.write_project(c,p,'백업에서 새 프로젝트 복원',True); result['projectId']=p['projectId']
        elif any(result.get(k) for k in ('assets','frames','alignmentGroups','generations')):
            p=s.get_project(j['projectId'],c)
            if j['operation']=='extract':
                result['frameVersionIds']=[f['frameVersionId'] for f in result.get('frames',[])]
            for key in ('assets','frames','generations'): p[key].extend(result.get(key,[]))
            for g in result.get('alignmentGroups',[]):
                old=next((x for x in p['alignmentGroups'] if x['alignmentGroupId']==g['alignmentGroupId']),None)
                if old:
                    # Preserve edits made during image processing; append only new candidates.
                    old['frameVersionIds']+= [fid for fid in g['frameVersionIds'] if fid not in old['frameVersionIds']]
                    for fid,a in result.get('alignments',{}).items(): a['groupRevisionId']=old['groupRevisionId']
                else: p['alignmentGroups'].append(g)
            p['alignments'].update(result.get('alignments',{})); s.write_project(c,p,j['operation']+' 결과 등록'); result['savedRevision']=p['revision']
        current.update(status=result.get('status','succeeded'),step='complete',artifacts=arts,result={k:v for k,v in result.items() if k not in ('assets','frames','alignmentGroups','alignments','generations','files')},checkpoints=[{'step':j['operation'],'inputHash':j['requestHash'],'artifacts':arts}],published=True)
        s.write_job(c,current)

def run(j):
    work=s.DATA/'jobs'/j['jobId']/j['attemptId']; work.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy(); env['PYTHONPATH']=str(s.ROOT); env['PYTHONDONTWRITEBYTECODE']='1'
    with open(work/'process.log','ab',buffering=0) as log:
        proc=subprocess.Popen([sys.executable,'-m','services.worker.task',j['jobId'],j['attemptId']],cwd=s.ROOT,env=env,stdout=log,stderr=log,start_new_session=True)
        with s.transaction() as c:
            current=s.get_job(j['jobId'],c); current['childPid']=proc.pid; s.write_job(c,current)
        canceled=False; stop_at=None; start=time.monotonic()
        while proc.poll() is None:
            beat(); current=s.get_job(j['jobId'])
            if (current['status']=='cancel_requested' or STOP or time.monotonic()-start>900) and stop_at is None:
                canceled=True; stop_at=time.monotonic()
                try: os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError: pass
            if stop_at and time.monotonic()-stop_at>3:
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
            time.sleep(.2)
        proc.wait()
        # Descendants can survive after the task leader exits. Reap the whole group.
        terminate_group(proc.pid)
    payload_path=work/'result.json'
    if not canceled and payload_path.exists():
        payload=json.loads(payload_path.read_text())
        if payload.get('ok'):
            try: publish(j,payload); return
            except Exception as e: payload={'error':dict(code=getattr(e,'code','PUBLICATION_FAILED'),message=getattr(e,'message','결과 게시를 완료하지 못했습니다. 이전 출력은 보존됩니다.'))}
    else:
        payload={'error':dict(code='CANCELED' if canceled else 'PROCESS_INTERRUPTED',message='로컬 실행이 중단되었습니다. 외부 생성의 취소 여부는 별도 확인이 필요합니다.'),'outcomeUnknown':j['operation']=='generate'}
    with s.transaction() as c:
        current=s.get_job(j['jobId'],c)
        status='provider_outcome_unknown' if payload.get('outcomeUnknown') else ('interrupted' if STOP else 'canceled' if canceled else 'failed')
        if payload.get('providerCheckpoint'):
            current['result']={'receipt':payload['providerCheckpoint']['providerResult']['receipt']}
            current['providerCheckpoint']=True
            current['checkpoints']=[{'step':'generate','inputHash':j['requestHash'],'confirmed':True}]
        current.update(status=status,errors=[payload['error']],step='stopped'); s.write_job(c,current)

def main():
    global STOP
    s.init(); lock=open(s.DATA/'worker.lock','a+')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('다른 작업 처리기가 실행 중입니다.')
    def stopping(*args):
        global STOP; STOP=True
    signal.signal(signal.SIGTERM,stopping); signal.signal(signal.SIGINT,stopping)
    recover()
    while not STOP:
        beat(); j=claim()
        if j: run(j)
        else: time.sleep(.3)
    with s.connect() as c: c.execute("DELETE FROM meta WHERE key='worker_heartbeat'")
if __name__=='__main__': main()
