"""Build a self-contained, read-only candidate comparison; never edits app state."""
import argparse
import base64
import json
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
PHASES=['near_contact','near_down','near_passing','near_up','far_contact','far_down','far_passing','far_up']

def review_inputs(out):
    """Do not mix superseded observations with corrected editor renderings."""
    aligned=(out/'editor-aligned').exists()
    observation_path=out/('observations-aligned.json' if aligned else 'observations.json')
    observations=json.loads(observation_path.read_text())['frames'] if observation_path.exists() else []
    return observations,observation_path.name

def selection(frames):
    groups={p:[] for p in PHASES}
    for f in frames:
        # Confidence cannot override failed identity or unobserved leg identity.
        if f.get('identity_verdict')!='pass' or not f.get('leg_identity_observable'): continue
        if f.get('motion_defects'): continue
        phase=f.get('baseline_phase','unknown');confidence=f.get('baseline_confidence',0)
        if phase not in groups or confidence<0.8: continue
        groups[phase].append(f)
    missing=[p for p,v in groups.items() if not v]
    order=[] if missing else [max(groups[p],key=lambda f:f['baseline_confidence'])['id'] for p in PHASES]
    return {'candidate_counts':{p:len(v) for p,v in groups.items()},'missing_phases':missing,'proposed_order':order,'production_approved':False,'note':'Uncalibrated automatic phase-label diagnostic only. Unknown labels do not block visually proposed ordering trials. Any order still requires playback review.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve()
    mapping=json.loads((out/'candidate-map.json').read_text())
    observations,observation_source=review_inputs(out)
    byid={f['id']:f for f in observations};data=[];measurements={}
    for item in mapping:
        aligned=out/'editor-aligned'/item['source_set']/f"frame-{item['source_index']}.png"
        display=aligned if aligned.exists() else Path(item['frame'])
        im=Image.open(display).convert('RGBA');bbox=im.getbbox();height=bbox[3]-bbox[1]
        data.append({**item,**byid.get(item['id'],{}),'image':'data:image/png;base64,'+base64.b64encode(display.read_bytes()).decode(),'bbox':bbox,'visible_height':height})
        measurements.setdefault(item['source_set'],[]).append(height)
    ref=ROOT/'.data/experiments/original-sprite-gen-20261004/idle-base.png';idle=Image.open(ref).convert('RGBA');box=idle.getbbox()
    result={'schema_version':1,'candidate_count':len(data),'observed_count':len(observations),'identity_verdicts':{key:sum(f['identity_verdict']==key for f in observations) for key in ['pass','fail','uncertain']},'leg_identity_observable':sum(f['leg_identity_observable'] for f in observations),'baseline_phase_counts':{k:sum(f['baseline_phase']==k for f in observations) for k in PHASES+['unknown']},'reference_visible_height':box[3]-box[1],'set_visible_heights':{k:{'min':min(v),'max':max(v)} for k,v in measurements.items()},'baseline_selection':selection(observations),'temporal_qa_passed':False}
    result.update(observation_source=observation_source,
                  identity_criterion='Major elements preserved and broadly similar style after editor alignment. Minor pixels, shading and pose differences are allowed.',
                  unconfirmed_phases_are_not_proven_missing=True)
    if (out/'reorder-results.json').exists():
        reordered=json.loads((out/'reorder-results.json').read_text())
        result['ordering_trials']=[{k:t[k] for k in ['name','labels','clipId','durationMs']} for t in reordered['trials']]
        result['ordering_trial_viewer']='reorder-review.html'
    if (out/'opposite-leg-audit.json').exists():
        result['leg_reinspection']={'source':'opposite-leg-audit.json','opposite_swing_candidates':['A4','A8'],
                                   'comparison_swing_candidates':['B3','B4'],'confidence':'medium',
                                   'opposite_landing_verified':False,
                                   'note':'Raw hip/thigh occlusion review found opposite swing evidence. Earlier unknown labels did not establish absence.'}
    if (out/'mixed-leg-results.json').exists():
        mixed=json.loads((out/'mixed-leg-results.json').read_text())
        result.setdefault('ordering_trials',[]).extend({k:t[k] for k in ['name','labels','clipId','durationMs']} for t in mixed['trials'])
        result['ordering_trial_viewer']='mixed-leg-review.html'
    (out/'comparison-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    embedded=json.dumps({'frames':data,'idle':'data:image/png;base64,'+base64.b64encode(ref.read_bytes()).decode(),'results':result},ensure_ascii=False).replace('</','<\\/')
    html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Idle · 보행 후보 검수</title>
<style>*{box-sizing:border-box}body{margin:0;background:#11151d;color:#e6e9f1;font:16px/1.6 system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:32px}h1{font-size:30px;line-height:1.3;margin:0 0 12px}h2{font-size:20px}p{max-width:900px;color:#bbc4d4}.status{padding:14px 20px;border:1px solid #745841;border-radius:12px;background:#292218;color:#ffcf95}.controls{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:20px 0}button,select,input{font:inherit}button,select{background:#263141;color:white;border:1px solid #4a5870;border-radius:7px;padding:8px 12px;cursor:pointer}button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid #6ed8e9;outline-offset:3px}.stages{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}article{border:1px solid #394557;border-radius:12px;overflow:hidden;background:#1b2330}article h3{padding:10px 14px;margin:0;font-size:16px}.stage{height:400px;display:flex;justify-content:center;align-items:flex-end;background:repeating-conic-gradient(#e1e4e8 0% 25%,#d2d7df 0% 50%) 50%/20px 20px}.stage img{width:192px;height:384px;image-rendering:pixelated}small{display:block;padding:10px 14px;color:#bac6d9}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.grid .stage{height:272px}.grid .stage img{width:128px;height:256px}.bad{color:#ffbd9d}.good{color:#9ce0ce}details{padding:10px 14px;font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#192130;padding:20px;border-radius:10px}@media(max-width:850px){.stages,.grid{grid-template-columns:repeat(2,1fr)}main{padding:20px}.stage{height:272px}.stage img{width:128px;height:256px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}</style>
<main><h1>Idle 기준 · 보행 후보 검수</h1><p>실제 GPT 원본 3장 → 기존 에디터에서 정렬한 24후보. 외형은 주요 요소와 비슷한 스타일이 유지되면 통과하며, 미세한 픽셀·명암 차이는 탈락 사유가 아닙니다.</p><div id="status" class="status"></div>
<div class="controls"><button id="play" aria-pressed="false">재생</button><button id="prev">이전 프레임</button><button id="next">다음 프레임</button><label>프레임 <input id="frame" type="range" min="0" max="7" value="0"></label><label>재생 속도 <select id="speed"><option value="125">8 fps</option><option value="250">4 fps · 느리게</option></select></label><span id="counter"></span></div>
<p>에디터의 공통 배율과 발 앵커를 적용한 64×128 결과입니다. 각 묶음의 첫 접촉 자세를 Idle의 94px에 맞추고 묶음 전체에 같은 배율을 썼습니다. 재생은 <strong>요청한 단계 순서</strong>이며 관측으로 승인한 보행이 아닙니다. B·C는 원본 후보를 요청했던 단계 순서로 되돌려 비교합니다. 자세별로 키를 같게 만드는 개별 리사이징이나 포즈 합성은 하지 않았습니다. 수평 위치는 몸통 중심의 지면 투영으로 보정했습니다. 실제 지지발과 재생 중 미끄럼은 별도 확인이 필요합니다.</p><div id="stages" class="stages"></div>
<h2>24개 후보 · 원본 출처와 관측</h2><div id="grid" class="grid"></div><p>카드의 라벨은 에디터 보정 후 다시 검수한 결과입니다. unknown은 세부 보행 단계를 확정하지 못했다는 뜻이며, 외형 불합격이나 필요한 자세가 아예 없다는 뜻은 아닙니다.</p><h2>판정 기록</h2><pre id="metrics"></pre><p>저장된 시각 관측과 원본 후보로 비교합니다. 외형 실패나 다리 식별 불가는 신뢰도 점수만으로 합격 처리하지 않으며, 최종 채택에는 재생 검수가 필요합니다.</p></main>
<script>const D=__DATA__;let step=0,playing=false,timer=null;const phases=['near_contact','near_down','near_passing','near_up','far_contact','far_down','far_passing','far_up'];const orders={a:[0,1,2,3,4,5,6,7],b:[4,5,6,7,0,1,2,3],c:[0,4,1,5,2,6,3,7]};const el=id=>document.getElementById(id);const art=(name,img,id)=>{let a=document.createElement('article'),h=document.createElement('h3'),s=document.createElement('div'),im=document.createElement('img'),cap=document.createElement('small');h.textContent=name;s.className='stage';im.src=img;im.alt=name;im.id=id;s.append(im);cap.id=id+'-caption';a.append(h,s,cap);return a};el('stages').append(art('승인된 Idle',D.idle,'idle'));for(let l of 'abc')el('stages').append(art('후보 '+l.toUpperCase(),'','set-'+l));function render(){for(let l of 'abc'){let f=D.frames.find(f=>f.source_set===l&&f.source_index===orders[l][step]);el('set-'+l).src=f.image;el('set-'+l+'-caption').textContent=`${f.id} · 원본 ${l.toUpperCase()}${f.source_index+1} · 높이 ${f.visible_height}px · ${f.identity_verdict||'검수 중'}`;}el('counter').textContent=`${step+1} / 8`;el('frame').value=step;}function start(){clearInterval(timer);if(playing)timer=setInterval(()=>{step=(step+1)%8;render()},Number(el('speed').value));el('play').textContent=playing?'일시정지':'재생';el('play').setAttribute('aria-pressed',String(playing))}el('play').onclick=()=>{playing=!playing;start()};el('prev').onclick=()=>{step=(step+7)%8;render()};el('next').onclick=()=>{step=(step+1)%8;render()};el('frame').oninput=e=>{step=Number(e.target.value);render()};el('speed').onchange=start;for(let f of [...D.frames].sort((a,b)=>(a.source_set+a.source_index).localeCompare(b.source_set+b.source_index))){let a=art(`${f.id} · ${f.source_set.toUpperCase()}${f.source_index+1}`,f.image,'card-'+f.id),cap=a.querySelector('small');cap.textContent=`외형: ${f.identity_verdict||'검수 중'} · 단계: ${f.baseline_phase||'검수 중'}`;let det=document.createElement('details'),sum=document.createElement('summary'),p=document.createElement('p');sum.textContent='관측 근거';p.textContent=f.observation||'비전 검수 진행 중';det.append(sum,p);a.append(det);el('grid').append(a)}const r=D.results;el('status').textContent=r.observed_count<24?`검수 진행 중 (${r.observed_count}/24). 아직 사용 승인하지 않았습니다.`:`외형 통과 ${r.identity_verdicts.pass}/24 · ${r.leg_reinspection?"반대발 스윙 후보 A4·A8 확인(확신 중간)":"정지 단계 확정 전"} · 보행 편집 시안 검수 중`;el('metrics').textContent=JSON.stringify(r,null,2);render();window.reviewState=()=>({step,playing,images:document.images.length,loaded:[...document.images].every(x=>x.complete&&x.naturalWidth>0),results:r});</script></html>'''
    (out/'review.html').write_text(html.replace('__DATA__',embedded))
    print(json.dumps({'viewer':str(out/'review.html'),'observed':len(observations),'identity':result['identity_verdicts']},ensure_ascii=False))
if __name__=='__main__':main()
