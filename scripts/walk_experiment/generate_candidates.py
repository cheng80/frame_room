"""Generate three preserved GPT rows through the project engine; no app/DB writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/sprite-gen'
CLI = ENGINE / '.venv/bin/sprite-gen'
PHASES = [
    'NEAR CONTACT: camera-near leg reaches forward (screen right), heel touching the floor; far leg extends behind, toe touching floor.',
    'NEAR DOWN: weight over forward camera-near foot, that knee flexed, body lower; far heel lifts behind to begin swing.',
    'NEAR PASSING: camera-near leg supports underneath the hip; far knee swings forward past it, far foot lifted and both feet close horizontally.',
    'NEAR UP: camera-near support leg extends behind onto toe, body higher; far thigh advances in front with knee bent and foot above floor.',
    'FAR CONTACT: camera-far leg reaches forward (screen right), heel touching floor; near leg extends behind, toe touching floor. The overlap order must reverse from NEAR CONTACT.',
    'FAR DOWN: weight over forward camera-far foot, that knee flexed, body lower; near heel lifts behind to begin swing.',
    'FAR PASSING: camera-far leg supports underneath hip; near knee swings forward past it, near foot lifted and feet close horizontally.',
    'FAR UP: camera-far support leg extends behind onto toe, body higher; near thigh advances in front with knee bent and foot above floor.',
]

def main():
    p=argparse.ArgumentParser(); p.add_argument('--out',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    base=ROOT/'.data/experiments/original-sprite-gen-20261004/idle-base.png'
    orders={'a':list(range(8)), 'b':[4,5,6,7,0,1,2,3], 'c':[0,2,4,6,1,3,5,7]}
    request_template=json.loads((ROOT/'.data/experiments/threejs-walk-guide-20261004/request-explicit.json').read_text())
    plan={'schema_version':1,'base':str(base),'base_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),'provider':'codex','billing':'chatgpt-subscription','requested_images':3,'requested_candidates':24,'request_order_is_not_observation':True,'sets':{}}
    for name,order in orders.items():
        run=out/f'set-{name}'
        req=json.loads(json.dumps(request_template));req['character']['id']='swordsman-walk-candidates-'+name
        action=('Create a POSE CANDIDATE BANK of the exact attached accepted swordsman, in a single horizontal strip of 8 full-body separated sprites. '
                'Use the same three-quarter side view facing screen RIGHT as the identity image. This is a relaxed natural in-place two-legged WALK, not running, skating, marching or jumping. '
                'Keep brown hair, navy scarf, one silver shoulder guard, cream sleeves, brown leather vest, navy trousers, brown boots, gloves, and the sword in the SAME hand. '
                'Keep identical head, torso, limb lengths, pixel density and palette in all slots. No redesign or enlargement of the head. '
                'The camera-near leg is the leg nearer to the viewer; the far leg is occluded by it where they cross. Keep this same identity through all poses, not just whichever foot is on screen left. '
                'Render subtle existing lighting to distinguish the two trouser legs; do not add colored leg markers. '
                'Keep the torso horizontally anchored. Keep a common ground line and image scale; allow natural roughly 1-2 logical pixel body rise/fall. '
                'The complete silhouette should be about 94 logical pixels tall in a 64x128 cell, with full sword and boots visible. '
                'Each requested pose below is independent; DO NOT replace later slots with repeats of the first half-cycle. '
                'For each slot, follow the actual support-leg identity and raised foot, making leg crossing visibly legible. '
                + '\n'.join(f'Slot {i+1}: {PHASES[j]}' for i,j in enumerate(order))
                + '\nOutput only the eight character candidates on the requested flat cyan background. No labels, arrows, floor lines, shadows, grid, or guide figures.')
        req['states']={'walk':{'frames':8,'fps':8,'loop':True,'action':action}}
        reqpath=out/f'request-{name}.json'
        if not reqpath.exists(): reqpath.write_text(json.dumps(req,ensure_ascii=False,indent=2)+'\n')
        if not run.exists(): subprocess.run([str(CLI),'prepare','--out-dir',str(run),'--character-id',req['character']['id'],'--base-image',str(base),'--request',str(reqpath)],check=True)
        plan['sets'][name]={'run':str(run),'requested_phase_indices':order}
    (out/'generation-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    if not a.execute: print(json.dumps({'prepared':str(out),'calls':0}));return
    # Sequential requests: each distinct row once; accepted or failed submissions never auto-retry.
    for name in orders:
        run=out/f'set-{name}';marker=run/'generation-started.json'
        if marker.exists(): print(f'skip existing submission {name}',flush=True);continue
        marker.write_text(json.dumps({'started_at':time.time(),'automatic_retry':False}))
        log=run/'generation.log'
        with log.open('w') as stream:
            result=subprocess.run([str(CLI),'gen-set','--run-dir',str(run),'--provider','codex','--model','gpt-6-sol','--concurrency','1'],stdout=stream,stderr=subprocess.STDOUT)
        print(json.dumps({'set':name,'exit_code':result.returncode,'raw_exists':(run/'raw/walk.png').exists()}),flush=True)
        if result.returncode: sys.exit(result.returncode)

if __name__=='__main__':main()
