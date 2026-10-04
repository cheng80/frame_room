"""Blind image observation, identity gate and walk phase labels via Codex vision."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tempfile
import time
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
PHASES=['near_contact','near_down','near_passing','near_up','far_contact','far_down','far_passing','far_up','unknown']
STR={'type':'string'}
FRAME_SCHEMA={'type':'object','additionalProperties':False,'properties':{
'id':STR,'observation':STR,'baseline_phase':{'type':'string','enum':PHASES},'baseline_confidence':{'type':'number','minimum':0,'maximum':1},
'leg_identity_observable':{'type':'boolean'},'identity_verdict':{'type':'string','enum':['pass','fail','uncertain']},
'identity_differences':{'type':'array','items':STR},'motion_defects':{'type':'array','items':STR},
'support_leg':{'type':'string','enum':['near','far','both','unknown']},'raised_foot':{'type':'string','enum':['near','far','none','unknown']}
},'required':['id','observation','baseline_phase','baseline_confidence','leg_identity_observable','identity_verdict','identity_differences','motion_defects','support_leg','raised_foot']}
SCHEMA={'type':'object','properties':{'frames':{'type':'array','items':FRAME_SCHEMA}},'required':['frames'],'additionalProperties':False}
PROMPT='''You are an independent pixel-art walk and character-style inspector. Inspect the actual attached images. The first image is the ACCEPTED IDLE reference. Subsequent cards are independent generated candidate poses identified only by the visible candidate ID, in RANDOM order. On each card: LEFT is the canonical engine original-color display (background removed and reprojected to the frame footprint), at a uniform viewing scale, RIGHT is the processed 64x128 sprite enlarged NEAREST. Judge raw evidence as well as processed pixels; report processing-only defects separately. These are observations of independent stills, not a time sequence. Do not infer phase from array order, candidate ID or generation intent.
All candidates should keep the reference's character identity and three-quarter right-facing camera. Camera-near/far leg is a continuous body identity determined by hip connection/occlusion, NEVER screen-left/right. If you cannot follow the leg into its hip, mark leg_identity_observable=false and baseline_phase=unknown. Anatomical left/right cannot be assumed. A single still may not distinguish DOWN versus UP; use unknown unless actual support and bend geometry supports it.
For every card first write observation as neutral English visual evidence only: visible foot positions relative to hip and floor, knee bends, overlap/hip connection and ambiguity, body height impression, and reference identity differences. Do not write the phase name or verdict in observation. Then assign baseline_phase independently:
near_contact: near heel forward touching floor, far toe behind, double support;
near_down: near leg is forward weight-bearing with bent knee, far heel lifting behind;
near_passing: near leg supports under hip, far bent leg swings past it with lifted foot near support horizontally;
near_up: near support leg behind extends/toe support, far knee swings ahead and foot stays airborne;
far_*: same definitions with legs exchanged. If insufficient evidence choose unknown, don't force one of eight.
Identity passes when major character elements are preserved and the overall style is broadly compatible with Idle. Check hair, scarf, shoulder guard, sleeves/vest, sword and holding hand, gloves, trousers and boots. Minor pixel, face-view, shading, detail and natural pose differences are allowed. Fail for a missing or fundamentally changed major element or clearly different art style, not for pixel inequality. Differences in crop footprint or displayed size before editor shared-scale and anchor correction are not evidence of identity failure. Keep static identity separate from readable gait phase; unknown legs do not imply a different character.
Do not claim continuous walk, foot slip or loop quality from isolated stills. Return only the required JSON. Do not use tools, browse, write files, generate images or read other local files.'''

def prepare(out):
    cards=out/'cards';cards.mkdir(exist_ok=True)
    records=[]
    for letter in 'abc':
        run=out/f'set-{letter}'
        for i in range(8):
            frame=run/f'frames/walk/frame-{i}.png';orig=run/f'frames/walk/orig/frame-{i}.png'
            if not frame.exists(): raise ValueError(f'Missing extracted frame {frame}')
            records.append({'source_set':letter,'source_index':i,'frame':str(frame),'original_crop':str(orig)})
    random.Random(20261004).shuffle(records)
    for i,record in enumerate(records):
        record['id']=f'C{i+1:02d}'
        left=Image.open(record['original_crop']).convert('RGBA');right=Image.open(record['frame']).convert('RGBA')
        # Read-only viewing resizes; originals remain untouched.
        scale=min(320/left.width,620/left.height)
        left=left.resize((round(left.width*scale),round(left.height*scale)),Image.Resampling.NEAREST)
        right=right.resize((320,640),Image.Resampling.NEAREST)
        card=Image.new('RGB',(680,700),'#e2e5e9');card.paste(left,(10+(320-left.width)//2,50),left);card.paste(right,(350,50),right)
        ImageDraw.Draw(card).text((12,12),record['id']+' | original-color display / extracted sprite',fill='#172235')
        card.save(cards/(record['id']+'.png'))
        record['card']=str(cards/(record['id']+'.png'))
        record['sha256']=hashlib.sha256(frame.read_bytes()).hexdigest()
    (out/'candidate-map.json').write_text(json.dumps(records,indent=2)+'\n')
    return records

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--batch',type=int,choices=range(1,7));a=p.parse_args();out=a.out.resolve()
    records=json.loads((out/'candidate-map.json').read_text()) if (out/'candidate-map.json').exists() else prepare(out)
    prompt_path=out/'vision-prompt.txt'
    if prompt_path.exists() and prompt_path.read_text()!=PROMPT:
        if a.execute: raise RuntimeError('Stored prompt differs; preserve this audit and use a fresh experiment directory')
    elif not prompt_path.exists(): prompt_path.write_text(PROMPT)
    if not (out/'vision-schema.json').exists(): (out/'vision-schema.json').write_text(json.dumps(SCHEMA))
    if not a.execute: return
    from sprite_gen.gen.base import provider_subprocess_env,provider_binary
    results=[];batches=[]
    for start in range(0,len(records),4):
        if a.batch is not None and start//4+1 != a.batch: continue
        batch=records[start:start+4];answer=out/f'vision-batch-{start//4+1}.json';marker=answer.with_suffix('.started.json')
        if answer.exists():
            data=json.loads(answer.read_text());results+=data['frames'];continue
        if marker.exists(): raise RuntimeError('Prior submission exists; inspect before any additional call')
        with marker.open('x') as marker_file: marker_file.write(json.dumps({'started_at':time.time(),'ids':[r['id'] for r in batch]}))
        with tempfile.TemporaryDirectory(prefix='walk-vision-') as temp:
            cmd=[provider_binary('codex'),'exec','--sandbox','read-only','--skip-git-repo-check','--ephemeral','--color','never','--json','-m','gpt-6-sol','-c','model_reasoning_effort="high"','-C',temp,'--output-schema',str(out/'vision-schema.json'),'-o',str(answer),'-i',str(ROOT/'.data/experiments/threejs-walk-guide-20261004/idle-reference-nearest-x8.png')]
            for rec in batch:cmd+=['-i',rec['card']]
            cmd+=['-'];now=time.monotonic()
            result=subprocess.run(cmd,input=PROMPT,capture_output=True,text=True,timeout=240,env=provider_subprocess_env())
            elapsed=time.monotonic()-now
        events=[]
        for line in result.stdout.splitlines():
            try: events.append(json.loads(line))
            except json.JSONDecodeError:pass
        usage=[e.get('usage') for e in events if e.get('type')=='turn.completed']
        meta={'batch':start//4+1,'elapsed_seconds':elapsed,'exit_code':result.returncode,'usage':usage,'model':'gpt-6-sol'}
        (out/f'vision-meta-{start//4+1}.json').write_text(json.dumps(meta,indent=2))
        if result.returncode: raise RuntimeError(f'Vision exited {result.returncode}; no automatic retry')
        data=json.loads(answer.read_text())
        if {r['id'] for r in data['frames']}!={r['id'] for r in batch}: raise ValueError('Candidate IDs mismatch')
        results+=data['frames'];batches.append(meta)
        print(json.dumps({'batch':start//4+1,'done':len(results),'elapsed':round(elapsed,2)}),flush=True)
        if a.batch is None: (out/'observations.json').write_text(json.dumps({'schema_version':1,'method':'blind independent still observations; not temporal ground truth','frames':results},ensure_ascii=False,indent=2)+'\n')
    if a.batch is None: (out/'observations.json').write_text(json.dumps({'schema_version':1,'method':'blind independent still observations; not temporal ground truth','frames':results},ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__': main()
