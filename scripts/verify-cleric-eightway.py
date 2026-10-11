"""Verify an actual delivered atlas against its source receipts and baked cells."""
import hashlib
import json
import sys
from pathlib import Path
from PIL import Image

root = Path(sys.argv[1] if len(sys.argv)>1 else 'output/cleric-quarterview-8way').resolve()
folder = root/'delivery'
atlas = json.loads((folder/'cleric-atlas.json').read_text())
manifest = json.loads((folder/'cleric-manifest.json').read_text())
directions = ['N','NE','E','SE','S','SW','W','NW']
expected = {f'{s}_{d}' for s in ('walk','idle') for d in directions}
assert manifest['directions']==directions and set(atlas['animations'])==expected
assert set(manifest['animations'])==expected and manifest['mirroredDirections']==[]
assert hashlib.sha256((folder/'cleric-atlas.png').read_bytes()).hexdigest()==manifest['atlasSha256']
image = Image.open(folder/'cleric-atlas.png').convert('RGBA')
assert image.size==(atlas['meta']['size']['w'],atlas['meta']['size']['h'])
assert len(atlas['frames'])==manifest['frameCount']==128
evidence={}
requests=set()
for name in sorted(expected):
    clip=manifest['animations'][name]
    source=json.loads((root/'motions'/name/'complete.json').read_text())
    assert source['baseSha256']==clip['baseImageSha256']==hashlib.sha256((root/'bases'/clip['direction']/'anchor.png').read_bytes()).hexdigest(),(name,'outdated base image')
    receipt=json.loads(Path(source.get('generationCheckpoint',root/'motions'/name/'checkpoint.json')).read_text())
    assert receipt['postCount']==1 and receipt['phase']=='downloaded'
    assert source['requestId']==clip['requestId']==receipt['requestId']
    assert clip['requestId'] not in requests
    requests.add(clip['requestId'])
    assert source['selection']['loop'] and len(clip['frameNames'])==len(clip['durationsMs'])==8
    assert sum(clip['durationsMs'])==clip['durationMs'] and min(clip['durationsMs'])>0
    if name.startswith('walk'):
        assert clip['durationMs']==1000 and source['selection']['cycleAlignment']['durationMs']==1000
    anchor=source['normalization']['anchor']
    distinct=set();margins=[]
    for index,key in enumerate(clip['frameNames']):
        entry=atlas['frames'][key]; rect=entry['frame']
        assert rect['w']==128 and rect['h']==160 and entry['duration']==clip['durationsMs'][index]
        cell=image.crop((rect['x'],rect['y'],rect['x']+rect['w'],rect['y']+rect['h']))
        sprite=Image.open(source['frames'][index]['path']).convert('RGBA')
        wanted=Image.new('RGBA',(128,160));wanted.alpha_composite(sprite,(round(64-anchor['x']),round(148-anchor['y'])))
        # Canonical exporter clears RGB underneath alpha zero.
        if cell.tobytes()!=wanted.tobytes():
            import numpy as np
            a,b=np.array(cell),np.array(wanted);b[b[...,3]==0,:3]=0
            assert (a==b).all(),(name,index,'atlas pixels differ from finished source')
        box=cell.getchannel('A').getbbox();assert box
        margin=min(box[0],box[1],128-box[2],160-box[3]);assert margin>=4
        margins.append(margin);distinct.add(hashlib.sha256(cell.tobytes()).hexdigest())
    if name.startswith('walk'): assert len(distinct)>=4,(name,'walk has too few distinct drawings')
    evidence[name]={'frames':8,'uniqueDrawings':len(distinct),'durationMs':clip['durationMs'],
        'minimumMarginPx':min(margins),'pixelParity':True,'sourceFrames':clip['sourceFrameIndices']}
result={'status':'passed','animations':16,'frames':128,'imageSize':image.size,
        'sourceVideoRequests':len(requests),'clips':evidence}
(folder/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
