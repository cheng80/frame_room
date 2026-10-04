"""Diagnostic montage from editor-rendered PNGs; no synthesized poses."""
from pathlib import Path
import subprocess
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];r=ROOT/'.data/experiments/walk-candidates-20261004';out=r/'aligned-preview-frames';out.mkdir(exist_ok=True)
base=Image.open(ROOT/'.data/experiments/original-sprite-gen-20261004/idle-base.png').convert('RGBA');orders={'a':list(range(8)),'b':[4,5,6,7,0,1,2,3],'c':[0,4,1,5,2,6,3,7]}
for step in range(8):
 canvas=Image.new('RGBA',(640,320),'#e2e5e9');draw=ImageDraw.Draw(canvas)
 for i,l in enumerate(['idle','a','b','c']):
  im=base if l=='idle' else Image.open(r/f'editor-aligned/{l}/frame-{orders[l][step]}.png').convert('RGBA');im=im.resize((128,256),Image.Resampling.NEAREST);canvas.alpha_composite(im,(i*160+16,38));draw.text((i*160+16,10),'Idle reference' if l=='idle' else f'{l.upper()} aligned / {step+1}',fill='#132033')
 draw.text((16,300),'Diagnostic only - requested order, not an approved walk',fill='#722522');canvas.save(out/f'frame-{step}.png')
subprocess.run([str(ROOT/'engine/sprite-gen/.venv/bin/python'),str(ROOT/'engine/sprite-gen/scripts/compose_sprite_gif.py'),'--frame-dir',str(out),'--frame-order','1,2,3,4,5,6,7,8','--delay-ticks','12','--output',str(r/'editor-aligned-comparison.gif'),'--manifest-output',str(r/'editor-aligned-comparison-gif.json')],check=True,stdout=subprocess.DEVNULL)
print('Updated editor-aligned comparison GIF (120ms per diagnostic frame).')
