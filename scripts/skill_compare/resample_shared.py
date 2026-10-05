"""Use each real engine's resampler on byte-identical cycle PNGs. No generation."""
from pathlib import Path
import argparse,json,sys,hashlib
p=argparse.ArgumentParser();p.add_argument('--engine',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--length',type=int,default=32);p.add_argument('--standing-height',type=int,required=True);a=p.parse_args()
sys.path.insert(0,str(a.engine.resolve()))
from PIL import Image
from sprite_gen.video import align,rife,loop
files=sorted(a.input.glob('frame-*.png'));frames=[Image.open(f).convert('RGBA') for f in files]
engine=rife.Rife();out,facts=align.resample(frames,a.length,engine)
a.out.mkdir(parents=True,exist_ok=True)
for i,im in enumerate(out):im.save(a.out/f'frame-{i:03d}.png')
strip,meta=loop.build_strip(out,max_height=128,body_height=94,standing_src=a.standing_height,cycle_seconds=len(frames)/24,anchor='none')
strip.save(a.out/'walk.strip.png');(a.out/'walk.strip.json').write_text(json.dumps(meta,indent=2))
record={'engine':str(a.engine.resolve()),'input':str(a.input.resolve()),'inputSha256':[hashlib.sha256(f.read_bytes()).hexdigest() for f in files],'targetFrames':a.length,'phaseRotated':False,'interpolator':engine.describe(),'facts':facts,'note':'Same full-resolution inputs; actual engine RIFE and resample, no application selection/finishing. Source duration retained for review.'}
(a.out/'resample.json').write_text(json.dumps(record,indent=2));print(json.dumps({k:facts.get(k) for k in ['made_by_rife','made_at','nearest_at','between']}))
