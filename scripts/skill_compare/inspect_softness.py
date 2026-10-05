"""Inspect alpha and show matching source-frame details. No generation or sharpening."""
from pathlib import Path
import argparse,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
p=argparse.ArgumentParser();p.add_argument('root',type=Path);args=p.parse_args();root=args.root.resolve();results={}
for case,fr in [('existing','frame-room/run-02'),('new','frame-room')]:
 app=root/case/fr;up=root/case/'upstream/fixed';meta=json.loads((up/'walk.strip.json').read_text());strip=Image.open(up/'walk.strip.png').convert('RGBA');n=meta['frames']
 sources={mode:[Image.open(path).convert('RGBA') for path in sorted((app/mode/'finished').glob('frame-*.png'))] for mode in ['default','rgba']}
 sources['latest-fixed']=[strip.crop((i*meta['w'],0,(i+1)*meta['w'],meta['h'])) for i in range(n)]
 facts={}
 for name,frames in sources.items():
  arrays=[np.asarray(im) for im in frames];partial=sum(int(((a[:,:,3]>0)&(a[:,:,3]<255)).sum()) for a in arrays);visible=sum(int((a[:,:,3]>0).sum()) for a in arrays)
  facts[name]={'frames':n,'partialAlphaPixels':partial,'meanPartialAlphaPixels':round(partial/n,1),'visiblePixels':visible,'partialAlphaShare':round(partial/visible,4)}
 changed=visible=0
 for a,b in zip(sources['rgba'],sources['latest-fixed']):
  assert a.size==b.size
  aa=np.asarray(a);bb=np.asarray(b);fg=(aa[:,:,3]>0)|(bb[:,:,3]>0);changed+=int((np.any(aa!=bb,axis=2)&fg).sum());visible+=int(fg.sum())
 facts['rgbaVsLatest']={'changedForegroundPixels':changed,'foregroundPixels':visible,'equalForegroundFraction':1-changed/visible,'note':'Before placement, same selected interval; upstream fixed includes existing speck removal. Not a perceptual sharpness score.'}
 results[case]=facts
 if case=='new':
  index=8;box=(0,36,58,84);zoom=8;w=(box[2]-box[0])*zoom;h=(box[3]-box[1])*zoom;gap=18
  font=ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc',24);small=ImageFont.truetype('/System/Library/Fonts/AppleSDGothicNeo.ttc',19)
  sheet=Image.new('RGB',(3*w+4*gap,h+170),(20,25,33));draw=ImageDraw.Draw(sheet)
  draw.text((gap,14),'같은 원본 프레임 25 · RIFE 끄기 · 손과 칼 주변 8배 확대',font=font,fill='white')
  draw.text((gap,49),'모든 확대는 nearest. 블러·샤프닝 추가 없음. 크기 정규화 후, 앵커 배치 전 픽셀 비교.',font=small,fill='#b8c2d0')
  for j,(key,label) in enumerate([('default','현재 기본 · GIF 마무리'),('rgba','현재 · RGBA 유지'),('latest-fixed','최신 · RGBA 유지')]):
   x=gap+j*(w+gap);draw.text((x,86),label,font=font,fill='white');im=sources[key][index].crop(box);view=Image.new('RGBA',im.size,(216,220,227,255));view.alpha_composite(im);sheet.paste(view.convert('RGB').resize((w,h),Image.Resampling.NEAREST),(x,125))
   draw.text((x,132+h),f"평균 반투명 픽셀 {facts[key]['meanPartialAlphaPixels']}개/프레임",font=small,fill='#b8c2d0')
  sheet.save(root/'softness-8x.png')
(root/'blur-check.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(results,ensure_ascii=False,indent=2))
