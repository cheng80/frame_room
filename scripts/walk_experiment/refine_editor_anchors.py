"""Refine horizontal root placement through the editor without per-pose scaling."""
import sys,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
import httpx
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from services.api import store
from alignment.pipeline import render_occurrence
r=ROOT/'.data/experiments/walk-candidates-20261004';info=json.loads((r/'editor-project.json').read_text());pid=info['projectId'];c=httpx.Client(base_url='http://127.0.0.1:8765');c.headers['X-Session-Token']=c.get('/v1/health').json()['sessionToken'];p=c.get('/v1/projects/'+pid).json();d=json.loads((r/'editor-alignment.json').read_text());ops=[]
for letter,v in d.items():
 for record in v['frames']:
  im=Image.open(store.asset_path(record['imageAssetId'])).convert('RGBA');alpha=np.asarray(im)[...,3]
  # Central torso band, above hip swing and below scarf; explicit provisional landmark.
  y0,y1=round(im.height*.34),round(im.height*.48);ys,xs=np.where(alpha[y0:y1]>=128);x=float(np.median(xs));fid=record['frameVersionId'];a=p['alignments'][fid]
  ops.append({'type':'setAlignment','frameVersionId':fid,'alignment':{'sourceAnchor':{'x':x,'y':a['sourceAnchor']['y']},'method':'manual','approval':'pending'}})
  record['torso_landmark']={'x':x,'bandY':[y0,y1],'method':'median occupied torso-band x; assistant proposal, not human approval'}
response=c.patch('/v1/projects/'+pid+'/edits',json={'expectedRevision':p['revision'],'operations':ops});response.raise_for_status();p=response.json()['snapshot']
for letter,v in d.items():
 clip=next(x for x in p['clips'] if x['clipId']==v['clipId']);v['source_anchors']='ground projection of torso-band horizontal median; pending review'
 for record in v['frames']:
  occ=next(x for x in clip['occurrences'] if x['frameVersionId']==record['frameVersionId']);im,qa=render_occurrence(p,clip,occ,store.asset_path)
  if any(qa['overflowPx'].values()):raise RuntimeError('Editor crop overflow remains')
  im.save(record['file']);record['bbox']=im.getbbox();record['qa']=qa
(r/'editor-alignment.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');(r/'editor-project-snapshot.json').write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n');info.update(revision=p['revision'],anchors='torso-band ground projection, pending approval');(r/'editor-project.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
base=Image.open(ROOT/'.data/experiments/original-sprite-gen-20261004/idle-base.png').convert('RGBA')
for l in 'abc':
 sheet=Image.new('RGB',(9*256,552),'#e2e5e9');draw=ImageDraw.Draw(sheet)
 for i in range(9):
  im=base if i==0 else Image.open(r/f'editor-aligned/{l}/frame-{i-1}.png').convert('RGBA');im=im.resize((256,512),Image.Resampling.NEAREST);sheet.paste(im,(i*256,40),im);draw.text((i*256+12,10),'Idle' if i==0 else f'{l.upper()}{i}',fill='#132033')
 sheet.save(r/f'editor-aligned-contact-{l}.png')
canvas=Image.new('RGB',(1280,700),'#e2e5e9');draw=ImageDraw.Draw(canvas)
for i,path in enumerate([None,*[r/f'editor-aligned/{l}/frame-0.png' for l in 'abc']]):
 im=base if path is None else Image.open(path).convert('RGBA');im=im.resize((256,512),Image.Resampling.NEAREST);canvas.paste(im,(i*320+32,70),im);draw.text((i*320+32,20),['Accepted Idle','Editor aligned A1','Editor aligned B1','Editor aligned C1'][i],fill='#132033')
canvas.save(r/'editor-aligned-comparison.png');print(json.dumps({'revision':p['revision'],'frames':24,'overflow':0}))
