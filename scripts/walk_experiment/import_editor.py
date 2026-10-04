"""Import preserved raw rows into an isolated editor copy through its existing API."""
import argparse,hashlib,json,time,uuid,sys
from pathlib import Path
import httpx
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from alignment.pipeline import render_occurrence, extract_regions
from services.api import store

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve()
 client=httpx.Client(base_url='http://127.0.0.1:8765',timeout=30)
 token=client.get('/v1/health').json()['sessionToken'];client.headers['X-Session-Token']=token
 def request(method,path,**kw):
  response=client.request(method,path,**kw)
  if response.is_error:raise RuntimeError(f'{method} {path}: {response.status_code} '+response.text[:500])
  return response.json()
 original=request('GET','/v1/projects/1ae8af0c-d313-453f-a834-c8bfabbc6ec7')
 assert original['revision']==38
 record=out/'editor-project.json'
 if record.exists():
  previous=json.loads(record.read_text())
  if previous.get('status')=='aligned-for-review':raise RuntimeError('Completed editor copy already exists; use it instead of importing again')
  project=request('GET','/v1/projects/'+previous['projectId'])
 else:
  project=request('POST',f"/v1/projects/{original['projectId']}/duplicate",json={'expectedRevision':original['revision'],'name':'보행 후보 검수 · Idle 기준 정렬 · 2026-10-04'})
 pid=project['projectId'];base=f'/v1/projects/{pid}';record.write_text(json.dumps({'projectId':pid,'originalProjectId':original['projectId'],'originalRevision':original['revision'],'status':'importing'},ensure_ascii=False,indent=2))
 def load():return request('GET',base)
 def edit(ops):
  project=load();return request('PATCH',base+'/edits',json={'expectedRevision':project['revision'],'operations':ops})['snapshot']
 def job(op,aids,params):
  project=load();j=request('POST',base+'/jobs',json={'operation':op,'inputRevision':project['revision'],'assetIds':aids,'params':params,'idempotencyKey':str(uuid.uuid4())})
  deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   j=request('GET',f"/v1/jobs/{j['jobId']}")
   if j['status'] in ('succeeded','needs_review'):return j
   if j['status'] not in ('queued','running'):raise RuntimeError('Local processing failed: '+json.dumps(j.get('errors')))
   time.sleep(.3)
  raise RuntimeError('Local processing timeout; inspect job, no resubmission')
 reports={};orders={'a':list(range(8)),'b':[4,5,6,7,0,1,2,3],'c':[0,4,1,5,2,6,3,7]}
 for letter in 'abc':
  raw=out/f'set-{letter}/raw/walk.png'
  project=load();existing=next((x for x in project['assets'] if x['originalFilename']==f'GPT-actual-row-{letter}.png'),None)
  if existing is None:
   with raw.open('rb') as stream:
    uploaded=request('POST',base+'/assets',files={'files':(f'GPT-actual-row-{letter}.png',stream,'image/png')},data={'role':'source','importMode':'whole'})
   existing=uploaded['assets'][0]
  raw_id=existing['assetId'];project=load()
  cut_asset=next((x for x in reversed(project['assets']) if x['provenance'].get('parentAssetId')==raw_id),None)
  if cut_asset is None:
   job('cutout',[raw_id],{'key':'auto','tolerance':24});project=load()
   cut_asset=next(x for x in reversed(project['assets']) if x['provenance'].get('parentAssetId')==raw_id)
  components=extract_regions(store.asset_path(cut_asset['assetId']),{'mode':'components','minArea':4})
  components.sort(key=lambda c:c.get('area',0),reverse=True)
  if len(components)<8 or components[7].get('area',0)<1000:raise RuntimeError('Eight full characters not separated')
  rects=[dict(c['rect']) for c in components[:8]]
  for c in components[8:]:
   q=c['rect'];qx=q['x']+q['width']/2;qy=q['y']+q['height']/2
   def distance(b):return max(b['x']-qx,0,qx-b['x']-b['width'])**2+max(b['y']-qy,0,qy-b['y']-b['height'])**2
   b=min(rects,key=distance)
   if distance(b)>400:raise RuntimeError('Detached pixels need manual grouping')
   x=min(b['x'],q['x']);y=min(b['y'],q['y']);right=max(b['x']+b['width'],q['x']+q['width']);bottom=max(b['y']+b['height'],q['y']+q['height'])
   b.update(x=x,y=y,width=right-x,height=bottom-y)
  rects.sort(key=lambda b:b['x']);(out/f'editor-regions-{letter}.json').write_text(json.dumps({'method':'canonical component bounds; detached pieces merged, source pixels unchanged','components':len(components),'regions':rects},indent=2)+'\n')
  old=[f for f in project['frames'] if f.get('rawAssetId')==cut_asset['assetId']]
  if old:project=edit([{'type':'setFrameReview','frameVersionId':f['frameVersionId'],'review':'pending','hidden':True} for f in old])
  before={x['frameVersionId'] for x in project['frames']};job('extract',[cut_asset['assetId']],{'mode':'regions','regions':rects});project=load()
  frames=[f for f in project['frames'] if f['frameVersionId'] not in before];frames.sort(key=lambda f:f['sourceRect']['x'])
  if len(frames)!=8:raise RuntimeError(f'{letter}: expected 8 intact components, got {len(frames)}; manual review required')
  group=next(g for g in project['alignmentGroups'] if g['alignmentGroupId']==frames[0]['nativeScaleGroupId'])
  # One neutral contact-pose measurement per source row. Same factor for all 8.
  image=Image.open(store.asset_path(frames[0]['imageAssetId'])).convert('RGBA');bbox=image.getbbox();top,bottom=bbox[1],bbox[3]
  measurement={'topY':top,'bottomY':bottom,'targetHeight':94,'approved':True}
  project=edit([{'type':'setAlignmentGroup','alignmentGroupId':group['alignmentGroupId'],'changes':{'mode':'shared-scale-foot-anchor','bodyMeasurement':measurement,'cell':{'width':64,'height':128,'edge':2},'targetAnchor':{'x':32,'y':118}}},{'type':'createClip','clip':{'name':f'Walk {letter.upper()} · 정렬 후 검수','stateId':f'walk-experiment-{letter}','defaultFps':8,'facing':'right','loop':True}}])
  clip=project['clips'][-1];project=edit([{'type':'addOccurrence','clipId':clip['clipId'],'frameVersionId':frames[i]['frameVersionId']} for i in orders[letter]])
  clip=next(c for c in project['clips'] if c['clipId']==clip['clipId']);dest=out/'editor-aligned'/letter;dest.mkdir(parents=True)
  outputs=[]
  for i,frame in enumerate(frames):
   occ=next(o for o in clip['occurrences'] if o['frameVersionId']==frame['frameVersionId']);im,qa=render_occurrence(project,clip,occ,store.asset_path);im.save(dest/f'frame-{i}.png')
   outputs.append({'index':i,'frameVersionId':frame['frameVersionId'],'imageAssetId':frame['imageAssetId'],'file':str(dest/f'frame-{i}.png'),'bbox':im.getbbox(),'qa':qa})
  reports[letter]={'raw_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'raw_asset_id':raw_id,'group_id':group['alignmentGroupId'],'measurement_source':'first contact-pose raw component; provisional assistant measurement','bodyMeasurement':measurement,'sharedScale':94/(bottom-top),'targetAnchor':{'x':32,'y':118},'source_anchors':'editor automatic bottom-band proposals, pending review','clipId':clip['clipId'],'requested_order':orders[letter],'frames':outputs}
  (out/'editor-alignment.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps({'set':letter,'frames':8,'scale':94/(bottom-top),'heights':[f['bbox'][3]-f['bbox'][1] for f in outputs]}),flush=True)
 project=load();(out/'editor-project-snapshot.json').write_text(json.dumps(project,ensure_ascii=False,indent=2)+'\n')
 original_after=request('GET',f"/v1/projects/{original['projectId']}");assert original_after==original
 record.write_text(json.dumps({'projectId':pid,'originalProjectId':original['projectId'],'originalRevision':original['revision'],'status':'aligned-for-review','revision':project['revision'],'original_unchanged':True,'source':'raw GPT rows imported; no pixel-unfake before editor shared scaling','productionApproved':False},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'projectId':pid,'revision':project['revision'],'original_unchanged':True}),flush=True)
if __name__=='__main__':main()
