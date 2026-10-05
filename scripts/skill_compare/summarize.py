"""Summarize saved evidence, without generation, database access or rendering."""
from pathlib import Path
import hashlib,json,subprocess,argparse
p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();r=a.root.resolve();repo=Path(__file__).resolve().parents[2]
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
x={'date':'2026-10-06','scope':'two shared MP4 inputs, real local processing; not prompt A/B or statistical model ranking','frameRoomRevisionAtComparison':subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),'skillRelease':'v2.34.0','skillRevision':'1fc35090fa9c359bc96d1287fbc32f733acaa7e4','newGeneration':{'gptImages':read(r/'new/base/generation.json')['extra']['inline_results'],'grokVideoPosts':read(r/'new/video/checkpoint.json')['postCount'],'model':read(r/'new/video/result.json')['receipt']['model'],'imageSha256':sha(r/'new/base/base.png'),'videoSha256':sha(r/'new/video/original.mp4'),'requestedSeconds':3,'requestedResolution':'480p','remainingQuota':'unknown'},'cases':{}}
cmd="import json,sys,PIL,numpy;from PIL import features;print(json.dumps(dict(python=sys.version.split()[0],pillow=PIL.__version__,numpy=numpy.__version__,webp=features.version('webp'),webpAvailable=features.check('webp'))))"
x['environments']={k:json.loads(subprocess.check_output([str(v),'-c',cmd],text=True)) for k,v in [('frameRoom',repo/'engine/sprite-gen/.venv/bin/python'),('upstream',Path('/Users/cheng80/.codex/skills/sprite-gen/.venv/bin/python'))]}
for case,fr in [('existing','frame-room/run-02'),('new','frame-room')]:
 report=read(r/case/fr/'report.json');variants={}
 for key,vr in report['variants'].items():
  proc=read(r/case/fr/key/'processing.json');s=proc['selection'];variants[key]={'frames':len(proc['frames']),'durationMs':sum(f['durationMs'] for f in proc['frames']),'start':s['startFrame'],'endExclusive':s['endFrame'],'repairSourceIndices':s.get('repair',{}).get('sourceFrameIndices',[]),'qaErrors':vr.get('qaErrors'), 'status':vr['status']}
 up={}
 for mode in ['auto','no-repair','fixed']:
  z=read(r/case/'upstream'/mode/'walk.loop.report.json');up[mode]={'status':z['status'],'start':z['cycle']['start'],'length':z['cycle']['length'],'durationMs':round(z['cycle_seconds']*1000),'replacedRelativeIndices':z.get('jump_repair',{}).get('replaced',[]),'sizeHold':z.get('size_hold'),'joltIndex':z.get('jolt',{}).get('index'),'seamRatio':z['resampled_seam_ratio'],'specksDropped':z.get('specks_dropped')}
 al=read(r/case/'upstream/aligned32/align.report.json');lr=al['loops'][0]
 x['cases'][case]={'videoSha256':report['sources']['clip']['sha256'],'referenceSha256':report['sources']['reference']['sha256'],'frameRoom':variants,'upstream':up,'align32':{'frames':32,'durationMs':1333,'made':lr['made_by_rife'],'nearestFallback':len(lr['nearest_at']),'retake':al['retake'],'startFoot':lr['start_foot'],'startFootSource':lr['start_foot_source']},'keyedParity':{'frames':read(r/'controlled-parity.json')[case]['keyedFrameCount'],'differentFrames':len(read(r/'controlled-parity.json')[case]['keyedDifferent'])}}
x['sharedRife']={'inputFrames':28,'outputFrames':32,'sameInputHashes':read(r/'shared-rife/frame-room/resample.json')['inputSha256']==read(r/'shared-rife/upstream/resample.json')['inputSha256'],'sameBinary':read(r/'shared-rife/frame-room/resample.json')['interpolator']==read(r/'shared-rife/upstream/resample.json')['interpolator'],'results':{}}
for name in ['frame-room','upstream']:
 f=read(r/'shared-rife'/name/'resample.json')['facts'];q=read(r/'shared-rife/quality.json')[name];x['sharedRife']['results'][name]={'made':f['made_by_rife'],'fallback':len(f.get('nearest_at',[])),'flaggedByLatestHeuristic':q['flagged'],'maxDarkExcess':q['maxDarkExcess']}
x['webp']={case:{mode:{k:v for k,v in row.items() if k not in ['differences','exactDiagnosticPath']} for mode,row in v.items()} for case,v in read(r/'webp-app-diagnostic.json').items()}
before=read(r/'preservation-before.json');changes=[p for p,h in before.items() if not (repo/p).is_file() or sha(repo/p)!=h];x['userDataPreservation']={'filesChecked':len(before),'changed':changes};assert not changes
for path in [r/'summary.json',repo/'docs/product/comparisons/sprite-gen-v2.34.0/ab-results.json']:
 path.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:x[k] for k in ['environments','sharedRife','userDataPreservation']},indent=2))
