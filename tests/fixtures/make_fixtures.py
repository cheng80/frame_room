"""Original synthetic fixtures: geometric robot, CC0, generator v1 seed 0."""
from PIL import Image,ImageDraw
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
records=[]
for name,crouch,shift in [('robot-idle',False,0),('robot-step',False,3),('robot-crouch',True,0)]:
    im=Image.new('RGBA',(128,128),(0,0,0,0));d=ImageDraw.Draw(im)
    y=22 if not crouch else 42
    # Purpose-made geometric sprite, no third-party character imagery.
    d.rectangle((48,y,77,y+25),fill='#203047');d.rectangle((51,y+3,74,y+20),fill='#53d9bd')
    d.rectangle((68,y+8,73,y+11),fill='#172334');d.rectangle((43,y+26,77,87 if not crouch else 99),fill='#203047')
    d.rectangle((48,y+29,72,85 if not crouch else 97),fill='#49adcc');d.rectangle((75,y+30,96,y+39),fill='#efb85e')
    d.rectangle((49,88 if not crouch else 96,58,110),fill='#203047');d.rectangle((65+shift,88 if not crouch else 96,74+shift,110),fill='#203047')
    d.rectangle((47,109,60,113),fill='#efb85e');d.rectangle((64+shift,109,78+shift,113),fill='#efb85e')
    path=ROOT/(name+'.png');im.save(path)
    records.append({'fixtureId':name,'kind':'SYNTHETIC','sourceUri':'make_fixtures.py','originalSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'decodedFingerprint':hashlib.sha256(im.tobytes()).hexdigest(),'generatorVersion':'1','seed':0,'approvedLandmarks':{'foot':{'x':64,'y':114}},'rightsNote':'Original geometric test fixture; CC0'})
sheet=Image.new('RGBA',(384,128))
for i,name in enumerate(['robot-idle','robot-step','robot-crouch']):sheet.paste(Image.open(ROOT/(name+'.png')),(i*128,0))
sheet.save(ROOT/'robot-sheet.png')
(ROOT/'provenance.json').write_text(json.dumps(records,indent=2))
