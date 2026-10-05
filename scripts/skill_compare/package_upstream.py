"""Package existing upstream strips for review; pad only, never resample sprite pixels."""
from pathlib import Path
import argparse,json,sys,tempfile,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from PIL import Image,ImageDraw
from alignment.animation_exports import write_animation_formats
p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
for meta_path in a.root.glob('*/upstream/*/walk.strip.json'):
    d=meta_path.parent; meta=json.loads(meta_path.read_text()); strip=Image.open(d/'walk.strip.png').convert('RGBA')
    w,h,n=meta['w'],meta['h'],meta['frames']; assert w<=64 and h<=118,(d,w,h)
    cells=[]; dest=d/'review'; dest.mkdir(exist_ok=True)
    for i in range(n):
        source=strip.crop((i*w,0,(i+1)*w,h)); cell=Image.new('RGBA',(64,128));cell.alpha_composite(source,((64-w)//2,118-h))
        cell.save(dest/f'frame-{i:03d}.png');cells.append(cell)
    total=round(meta['cycle_seconds']*1000);bounds=[round(i*total/n) for i in range(n+1)];durations=[bounds[i+1]-bounds[i] for i in range(n)]
    try:
        with tempfile.TemporaryDirectory(dir=dest) as scratch:
            scratch=Path(scratch)
            try:
                exports=write_animation_formats(cells,durations,True,scratch)
            finally:
                for item in scratch.iterdir():
                    if item.is_file(): shutil.copyfile(item,dest/item.name)
    except Exception as exc:
        exports={'status':'failed','reason':str(exc),'canonicalPngsPreserved':True}
        (dest/'export-failure.json').write_text(json.dumps(exports,ensure_ascii=False,indent=2))
    report=json.loads((d/'walk.loop.report.json').read_text())
    out={'label':'sprite-gen v2.34.0 '+d.name,'source':'upstream video-loop strip cells','displayOnlyPadding':{'cell':[64,128],'offset':[(64-w)//2,118-h],'resized':False},'frames':[str((dest/f'frame-{i:03d}.png').resolve()) for i in range(n)],'durationsMs':durations,'totalMs':total,'sourceStart':report['cycle']['start'],'sourceLength':report['cycle']['length'],'exports':exports}
    (dest/'manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    sheet=Image.new('RGB',(8*192,((n+7)//8)*408),(224,226,231)); draw=ImageDraw.Draw(sheet)
    for i,im in enumerate(cells):
        view=Image.new('RGBA',im.size,(224,226,231,255));view.alpha_composite(im)
        x=(i%8)*192;y=(i//8)*408;sheet.paste(view.convert('RGB').resize((192,384),Image.Resampling.NEAREST),(x,y+24));draw.text((x+6,y+4),f'{i}',fill=(20,20,20))
    sheet.save(dest/'contact.png')
    print(d,n,total,flush=True)
