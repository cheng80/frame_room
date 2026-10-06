"""Store concrete ordering hypotheses in the existing editor; preserve source clips."""
import argparse
import base64
import json
import math
import sys
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from alignment.pipeline import render_occurrence
from services.api import store
from sprite_gen.util.gif_utils import save_clean_gif, gif_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--prefix',choices=['reorder','mixed-leg'],default='reorder')
    args=parser.parse_args();out=args.out.resolve();prefix=args.prefix
    plan=json.loads(args.plan.read_text());trials=plan['trials']
    info=json.loads((out/'editor-project.json').read_text())
    alignment=json.loads((out/'editor-alignment.json').read_text())
    candidates={f'{letter.upper()}{f["index"]+1}':f for letter,row in alignment.items() for f in row['frames']}
    assert 1<=len(trials)<=3
    assert len({t['key'] for t in trials})==len(trials)
    for trial in trials:
        assert 2<=len(trial['labels'])<=8 and all(label in candidates for label in trial['labels'])
    record=out/f'{prefix}-results.json'
    if record.exists():raise RuntimeError('Reorder result exists; inspect it instead of duplicating trials')
    c=httpx.Client(base_url='http://127.0.0.1:8765',timeout=30)
    c.headers['X-Session-Token']=c.get('/v1/health').json()['sessionToken']
    base='/v1/projects/'+info['projectId']
    p=c.get(base).raise_for_status().json();before=p
    (out/f'editor-project-before-{prefix}.json').write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n')
    def edit(ops):
        nonlocal p
        response=c.patch(base+'/edits',json={'expectedRevision':p['revision'],'operations':ops})
        response.raise_for_status();p=response.json()['snapshot']
    result={'status':'in_progress','projectId':info['projectId'],'trials':[],
            'method':'Visual ordering hypotheses; no near/far label required to TRY an edit.',
            'new_generation_calls':0,'source_pixel_edits':False}
    record.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for trial in trials:
        state='walk-reorder-'+trial['key']
        if any(cl['stateId']==state for cl in p['clips']):raise RuntimeError('Trial state already exists; do not duplicate')
        edit([{'type':'createClip','clip':{'name':trial['name'],'stateId':state,'defaultFps':trial.get('fps',8),'facing':'right','loop':True}}])
        clip=next(cl for cl in p['clips'] if cl['stateId']==state)
        edit([{'type':'addOccurrence','clipId':clip['clipId'],'frameVersionId':candidates[label]['frameVersionId']} for label in trial['labels']])
        clip=next(cl for cl in p['clips'] if cl['clipId']==clip['clipId'])
        rendered=[];checks=[]
        dest=out/'reorders'/trial['key'];dest.mkdir(parents=True)
        for i,(occ,label) in enumerate(zip(clip['occurrences'],trial['labels'])):
            im,qa=render_occurrence(p,clip,occ,store.asset_path)
            expected=Image.open(candidates[label]['file']).convert('RGBA')
            assert im.tobytes()==expected.tobytes(),'Order trial unexpectedly changed rendered pixels'
            assert not any(qa['overflowPx'].values())
            im.save(dest/f'frame-{i}.png');rendered.append(im)
            checks.append({'label':label,'frameVersionId':occ['frameVersionId'],'render_identical':True,'overflowPx':qa['overflowPx']})
        gif=dest/'preview.gif'
        save_clean_gif([im.resize((256,512),Image.Resampling.NEAREST) for im in rendered],gif,duration_ms=round(1000/trial.get('fps',8)),loop=0,alpha_threshold=8)
        result['trials'].append({**trial,'clipId':clip['clipId'],'durationMs':round(1000/trial.get('fps',8))*len(rendered),
                                 'fps':trial.get('fps',8),'review':'pending','checks':checks,'gif_report':gif_report(gif),'gif':str(gif)})
        record.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    # Existing saved motions and source data must stay byte-for-byte equivalent as JSON values.
    for old in before['clips']:assert next(cl for cl in p['clips'] if cl['clipId']==old['clipId'])==old
    for key in ('assets','frames','alignments','alignmentGroups','references'):assert p[key]==before[key],key
    original=c.get('/v1/projects/'+info['originalProjectId']).raise_for_status().json()
    assert original==json.loads((out/'original-project-before.json').read_text())
    result.update(status='ready_for_playback_comparison',editorRevision=p['revision'],
                  original_project_unchanged=True,existing_clips_unchanged=True)
    record.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (out/f'editor-project-after-{prefix}.json').write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
    info.update(revision=p['revision'],reorder_trials=info.get('reorder_trials',[])+[t['clipId'] for t in result['trials']])
    (out/'editor-project.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
    build_preview(out,result,candidates,prefix)
    print(json.dumps({'revision':p['revision'],'trials':[{k:t[k] for k in ('name','labels','clipId')} for t in result['trials']]},ensure_ascii=False))


def build_preview(out,result,candidates,prefix='reorder'):
    baseline=['B5','B6','B7','B8','B1','B2','B3','B4']
    sequences=[{'name':'기존 B 순서','labels':baseline,'fps':8,'reason':'생성 시 요청한 단계 순서로 배치한 비교 기준.'},*result['trials']]
    images={label:'data:image/png;base64,'+base64.b64encode(Path(f['file']).read_bytes()).decode() for label,f in candidates.items()}
    data=json.dumps({'sequences':sequences,'images':images},ensure_ascii=False).replace('</','<\\/')
    html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>보행 순서 편집 비교</title>
<style>body{margin:0;background:#151b25;color:#e8edf5;font:16px/1.6 system-ui}main{max-width:1300px;margin:auto;padding:28px}h1{font-size:28px}p{color:#bcc9da}button,select{font:inherit;color:inherit;background:#29394d;padding:8px 14px;border:1px solid #68809d;border-radius:6px;margin-right:8px}button:focus-visible,select:focus-visible{outline:3px solid #79dbed}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px}article{border:1px solid #52627a;border-radius:10px;overflow:hidden}h2,article p{margin:12px 16px}h2{font-size:18px}.stage{height:400px;display:flex;justify-content:center;align-items:end;background:repeating-conic-gradient(#e4e7ed 0% 25%,#d1d8e1 0% 50%) 0/20px 20px}.stage img{width:192px;height:384px;image-rendering:pixelated}.order{font:13px/1.7 monospace;color:#9de6d2;overflow-wrap:anywhere}small{display:block;margin:12px 16px;color:#c7d0dc}.controls{margin:20px 0}.note{border-left:4px solid #e6b66c;padding-left:16px}</style>
<main><h1>순서를 바꾸면 어떻게 달라지는가</h1><p>외형을 통과한 기존 후보를 선택·재배열한 편집 시안입니다. 이미지·배율·앵커는 그대로이며 모든 열을 같은 1초 주기로 재생합니다. 8컷은 컷당 125ms, 5컷은 200ms입니다.</p><div class="controls"><button id="play">재생</button><button id="reset">처음</button><button id="step">다음 변화</button><label>속도 <select id="speed"><option value="1">1배속 · 1초 주기</option><option value="2">0.5배속 · 2초 주기</option></select></label></div><div id="grid" class="grid"></div><p class="note">프레임 수가 줄어도 전체 주기는 동일하게 맞췄습니다. 다리 라벨이 미확정이어도 편집은 시도할 수 있습니다. 각 시안의 자연스러움과 반복 이음새를 보고 채택하며, 이 화면 자체가 완성 보행 승인을 뜻하지는 않습니다.</p></main>
<script>const D=__DATA__;let tick=0,playing=false,timer;const get=id=>document.getElementById(id);D.sequences.forEach((s,i)=>{const a=document.createElement('article'),h=document.createElement('h2'),stage=document.createElement('div'),im=document.createElement('img'),order=document.createElement('p'),reason=document.createElement('p'),cap=document.createElement('small');h.textContent=s.name;stage.className='stage';im.id='im'+i;im.alt=s.name;stage.append(im);order.className='order';order.textContent=s.labels.join(' → ');reason.textContent=s.reason||s.hypothesis||'';cap.id='cap'+i;a.append(h,stage,cap,order,reason);get('grid').append(a)});function render(){D.sequences.forEach((s,i)=>{const k=Math.floor(tick/Math.round(1000/s.fps))%s.labels.length;get('im'+i).src=D.images[s.labels[k]];get('cap'+i).textContent=`${k+1}/${s.labels.length} · ${s.labels[k]}`})}function timerUpdate(){clearInterval(timer);if(playing)timer=setInterval(()=>{tick+=25;render()},25*Number(get('speed').value));get('play').textContent=playing?'일시 정지':'재생'}get('play').onclick=()=>{playing=!playing;timerUpdate()};get('reset').onclick=()=>{tick=0;render()};get('step').onclick=()=>{const jump=Math.min(...D.sequences.map(s=>{const d=Math.round(1000/s.fps);return d-tick%d}));tick+=jump;render()};get('speed').onchange=timerUpdate;window.reorderState=()=>({tick,playing,sequences:D.sequences.map(s=>s.labels),loaded:[...document.images].every(im=>im.complete&&im.naturalWidth>0)});render();</script></html>'''
    (out/f'{prefix}-review.html').write_text(html.replace('__DATA__',data))
    # A diagnostic side-by-side GIF from unchanged editor renderings.
    sequences=[s for s in sequences if len(s['labels'])==8]
    count=math.lcm(*(len(s['labels']) for s in sequences));frames=[]
    for step in range(count):
        canvas=Image.new('RGBA',(len(sequences)*192,324),'#e1e5eb');draw=ImageDraw.Draw(canvas)
        for i,seq in enumerate(sequences):
            label=seq['labels'][step%len(seq['labels'])]
            im=Image.open(candidates[label]['file']).convert('RGBA').resize((128,256),Image.Resampling.NEAREST)
            canvas.alpha_composite(im,(i*192+32,40))
            draw.text((i*192+16,10),'B original' if i==0 else 'Order trial '+str(i),fill='#172134')
            draw.text((i*192+16,302),label,fill='#172134')
        frames.append(canvas)
    save_clean_gif(frames,out/f'{prefix}-comparison.gif',duration_ms=125,loop=0,alpha_threshold=8)


if __name__=='__main__':main()
