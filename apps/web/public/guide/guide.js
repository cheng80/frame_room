'use strict';
document.documentElement.classList.add('js');
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
if(location.protocol==='file:') $$('[data-app-link]').forEach(a=>a.href='http://127.0.0.1:8765/'+(a.dataset.example||''));

// Static HTML remains readable without this script. No API calls or project writes.
const mapText=[
 ['라이브러리','프레임 편집 탭 왼쪽입니다. 동작과 추출된 후보를 고릅니다. 후보를 확인한 뒤 ‘선택 후보를 순서에 추가’를 눌러야 재생 순서에 들어갑니다. 자료·AI 생성·추출 버튼은 해당 제작 탭으로 이동만 합니다.'],
 ['캔버스','선택 슬롯의 편집 결과를 봅니다. 재생 순서와 후보 원본을 전환할 수 있고 제목줄의 ‘기준 비교’를 켜면 저장 기준과 나란히 봅니다.'],
 ['재생 순서','재생할 순서와 각 슬롯의 표시 시간을 정합니다. 같은 후보를 여러 번 넣어도 슬롯별 시간과 변형은 따로 편집합니다.'],
 ['속성','슬롯·픽셀·후보 확인·다음 작업 탭으로 위치·크기·픽셀 보정과 후보 비교를 다룹니다. 다음 작업 탭에서 자동 검사 결과와 남은 작업을 확인합니다.'],
 ['저장·내보내기','상단 저장으로 편집 초안을 확정합니다. 내보내기 버튼은 내보내기 탭으로 이동만 합니다. 출력은 저장된 버전으로 만듭니다.'],
 ['6단계 제작 탭','자료 준비 → 캐릭터 기준 → 동작 만들기 → 프레임 편집 → 결과 확인 → 내보내기. 탭 아래 상태는 실제 자료·저장·검사·출력 상태로 표시합니다. 크기·발 정렬, 이력·백업, 작업 센터는 별도 창으로 열립니다.']
];
$$('.hotspot').forEach(button=>button.addEventListener('click',()=>{
 const figure=button.closest('figure'),index=Number(button.dataset.point);$$('.hotspot',figure).forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
 $('.map-caption b',figure).textContent=String(index+1);$('.map-caption strong',figure).textContent=mapText[index][0];$('.map-caption p',figure).textContent=mapText[index][1];
}));
const box=$('#screen-lightbox');let screenTrigger=null;
const closeBox=()=>{box.close();screenTrigger?.focus();};
$$('[data-screen]').forEach(b=>b.addEventListener('click',()=>{
 screenTrigger=b;const figure=b.closest('figure'),image=$('img',figure);$('.lightbox-scroll',box).classList.remove('is-original');$('[data-original]',box).textContent='원본 크기';$('img',box).src=image.src;$('img',box).alt=image.alt;$('strong',box).textContent=image.alt;$('p',box).textContent=$('figcaption',figure).textContent;box.showModal();
}));
$('[data-close]',box).addEventListener('click',closeBox);box.addEventListener('cancel',e=>{e.preventDefault();closeBox();});box.addEventListener('click',e=>{if(e.target===box)closeBox();});
$('[data-original]',box).addEventListener('click',e=>{const original=$('.lightbox-scroll',box).classList.toggle('is-original');e.currentTarget.textContent=original?'화면에 맞추기':'원본 크기';});
let printDetails=[];
$$('[data-print]').forEach(b=>b.addEventListener('click',()=>window.print()));
window.addEventListener('beforeprint',()=>{printDetails=$$('.faq details').filter(d=>!d.open);printDetails.forEach(d=>d.open=true);});
window.addEventListener('afterprint',()=>{printDetails.forEach(d=>d.open=false);});
const chapters=$$('section.chapter');
const tocLinks=$$('.toc nav a, .mobile-toc a'),sections=$$('.toc nav a').map(a=>document.getElementById(a.hash.slice(1))).filter(Boolean);
let jump=null;
// A TOC jump lands a section at scroll-padding-top + its scroll-margin-top, so the active line is read from CSS, not fixed.
function position(){const root=document.documentElement,range=root.scrollHeight-innerHeight,pad=parseFloat(getComputedStyle(root).scrollPaddingTop)||0;let active=sections[0];
 for(const s of sections){if(s.getBoundingClientRect().top<=pad+(parseFloat(getComputedStyle(s).scrollMarginTop)||0)+1)active=s;}
 // At the bottom, later sections cannot reach that line: keep a jumped-to section until the reader scrolls, else the last visible one.
 if(jump&&Math.abs(scrollY-jump.y)>1)jump=null;
 if(range>0&&scrollY>=range-1){const visible=sections.slice(sections.indexOf(active)).filter(s=>s.getBoundingClientRect().top<innerHeight);active=visible.find(s=>'#'+s.id===jump?.hash)||visible.at(-1)||active;}
 tocLinks.forEach(a=>a.hash==='#'+active?.id?a.setAttribute('aria-current','location'):a.removeAttribute('aria-current'));$('.read-progress').style.width=(range>0?100*scrollY/range:0)+'%';}
const markJump=()=>{jump=location.hash?{hash:location.hash,y:scrollY}:null;position();};
window.addEventListener('scroll',position,{passive:true});window.addEventListener('resize',position);window.addEventListener('hashchange',markJump);window.addEventListener('load',markJump);markJump();
$$('.mobile-toc a').forEach(a=>a.addEventListener('click',()=>a.closest('details').open=false));
const search=$('#manual-search');
if(search){const result=$('.search-results');const index=chapters.map(c=>({id:c.id,title:$('h2',c).textContent,summary:$('.section-heading p',c)?.textContent||'',text:c.textContent.toLocaleLowerCase()}));
 const run=()=>{result.replaceChildren();const q=search.value.trim().toLocaleLowerCase();if(!q)return;const found=index.filter(c=>c.text.includes(q));const status=document.createElement('p');status.setAttribute('role','status');status.textContent=`‘${search.value}’ 검색 결과 ${found.length}개`;result.append(status);for(const c of found){const a=document.createElement('a'),strong=document.createElement('strong'),small=document.createElement('small');a.href='#'+c.id;strong.textContent=c.title;small.textContent=c.summary;a.append(strong,small);a.addEventListener('click',()=>{search.value='';result.replaceChildren();});result.append(a);}if(!found.length){const p=document.createElement('p');p.textContent='예: 후보, 검수, 앵커, 프레임, 백업으로 검색해 보세요.';result.append(p);}};
 search.addEventListener('input',run);$('[data-clear-search]').addEventListener('click',()=>{search.value='';run();search.focus();});
}
const done=new Set();$$('input[data-step]').forEach(input=>input.addEventListener('change',()=>{input.checked?done.add(input.dataset.step):done.delete(input.dataset.step);$$('input[data-step]').forEach(i=>i.checked=done.has(i.dataset.step));$('#completion-count').textContent=done.size+' / 6';$('#completion-progress').value=done.size;$('#completion-title').textContent=done.size===6?'첫 동작, 끝까지 따라왔습니다.':'한 단계씩 확인하며 마무리하세요.';}));
const recipes={
 walk:'저장한 기준 캐릭터의 오른쪽 방향 걷기 한 사이클을 8프레임으로 만들어 주세요. 한 PNG 시트에 4열×2행으로 배치하고 왼쪽 위부터 순서대로 읽습니다. 왼발 접지·내려감·통과·올라감, 오른발 접지·내려감·통과·올라감을 서로 다른 자세로 표현하세요. 처음과 끝에 같은 그림을 중복하지 마세요. 얼굴·의상·장비·색과 몸 크기, 카메라를 유지하세요. 발과 장비 전체가 셀 안에 들어오도록 여백을 두고, 프레임끼리 겹치지 않게 하세요. 실제 알파가 있는 투명 배경, 글자·격자선·바닥 그림자 없음.',
 idle:'저장한 기준 캐릭터의 대기 동작을 4프레임으로 만들어 주세요. 한 PNG 시트에 4열×1행으로 왼쪽부터 순서대로 배치합니다. 제자리에서 미세한 호흡과 스카프 움직임이 보이게 하세요. 얼굴·의상·장비·팔레트·몸 크기와 발 위치는 유지합니다. 각 프레임에 전신과 장비가 잘리지 않도록 여백을 두세요. 실제 알파가 있는 투명 배경, 글자·격자·다른 인물 없음.',
 jump:'저장한 기준 캐릭터의 점프 동작을 6프레임으로 만들어 주세요. 한 PNG 시트에 3열×2행으로 준비·도약·상승·정점·하강·착지 순서로 배치합니다. 얼굴·의상·장비·카메라·몸 크기를 유지하고 팔다리 자세만 바꾸세요. 몸을 셀마다 다른 크기로 확대하지 마세요. 전신과 장비 주변에 넉넉한 여백을 두세요. 실제 알파가 있는 투명 배경, 글자·격자선 없음. 실제 점프 높이와 루트 궤적은 에디터에서 별도로 확인합니다.'
};
$$('.prompt-demo').forEach(demo=>{const area=$('textarea',demo),status=$('[role=status]',demo);$$('[data-recipe]',demo).forEach(b=>b.addEventListener('click',()=>{$$('[data-recipe]',demo).forEach(t=>t.setAttribute('aria-pressed',String(t===b)));area.value=recipes[b.dataset.recipe];status.textContent='';}));$('[data-copy]',demo).addEventListener('click',async()=>{try{await navigator.clipboard.writeText(area.value);status.textContent='문구를 복사했습니다. 동작 만들기 → 이미지로 만들기의 동작과 포즈 설명에 붙여넣고 요청 프레임 수도 맞추세요.';}catch{area.focus();area.select();status.textContent='문구를 선택했습니다. 복사 단축키를 눌러 복사하세요.';}});});

const runtime=JSON.parse($('#guide-runtime').textContent),atlas=new Image(),players=[];
$$('canvas[data-player]').forEach(canvas=>{const name=canvas.dataset.player,button=$(`[data-play="${name}"]`),ctx=canvas.getContext('2d'),player={name,canvas,button,ctx,playing:false,index:0,start:0,raf:0,durations:[100,100,100,100,100,100]};players.push(player);
 const draw=index=>{const f=runtime[index];if(!atlas.complete||!atlas.naturalWidth)return;ctx.clearRect(0,0,512,512);ctx.imageSmoothingEnabled=false;ctx.drawImage(atlas,f.x,f.y,f.width,f.height,0,0,512,512);if(name==='timing')$('.frame-indicator').textContent=`${index+1} / 6 · ${player.durations[index]}ms`;};player.draw=draw;
 const stop=()=>{player.playing=false;cancelAnimationFrame(player.raf);button.textContent=name==='hero'?'예제 재생':'재생';button.setAttribute('aria-pressed','false');};player.stop=stop;
 const tick=now=>{if(!player.playing)return;const total=player.durations.reduce((a,b)=>a+b,0);let t=(now-player.start)%total,index=0;while(index<5&&t>=player.durations[index]){t-=player.durations[index];index++;}if(index!==player.index){player.index=index;draw(index);}player.raf=requestAnimationFrame(tick);};
 button.addEventListener('click',()=>{if(player.playing){stop();return;}player.playing=true;player.start=performance.now()-player.durations.slice(0,player.index).reduce((a,b)=>a+b,0);button.textContent='일시 정지';button.setAttribute('aria-pressed','true');player.raf=requestAnimationFrame(tick);});
});
atlas.onload=()=>players.forEach(p=>p.draw(0));atlas.onerror=()=>{players.forEach(p=>{p.button.disabled=true;});$$('.demo-error').forEach(e=>e.textContent='예제 이미지를 읽지 못했습니다. media/atlas.png가 HTML과 함께 있는지 확인하세요.');};atlas.src='media/atlas.png';
const timing=players.find(p=>p.name==='timing');
if(timing){const input=$('#durations'),fps=$('#fps'),result=$('#timing-result'),error=$('#timing-error');
 const update=values=>{timing.stop();timing.durations=values;timing.index=0;timing.draw(0);result.textContent=(values.reduce((a,b)=>a+b,0)/1000).toFixed(2)+'초';const strip=$('.timing-strip');strip.replaceChildren();values.forEach((v,i)=>{const span=document.createElement('span');span.textContent=`${i+1} · ${v}`;span.style.flex=String(v);strip.append(span);});input.value=values.join(', ');error.textContent='';};
 fps.addEventListener('input',()=>{$('#fps-value').textContent=fps.value;update(Array(6).fill(Math.round(1000/Number(fps.value))));});
 $('[data-apply-timing]').addEventListener('click',()=>{const parts=input.value.split(',').map(v=>v.trim()),values=parts.map(Number);if(parts.length!==6||parts.some(v=>!v)||values.some(v=>!Number.isInteger(v)||v<1||v>60000)){error.textContent='쉼표로 구분한 1~60000ms 정수 6개를 입력하세요.';return;}update(values);});
 $('[data-hold]').addEventListener('click',()=>update([250,100,100,100,100,250]));update([100,100,100,100,100,100]);
}
const followStops=[];
$$('.follow-demo').forEach(demo=>{
 const button=$('[data-follow-play]',demo),images=$$('img[data-animation]',demo);
 const show=playing=>{images.forEach(image=>image.src=playing?image.dataset.animation:image.dataset.still);button.setAttribute('aria-pressed',String(playing));button.textContent=playing?'첫 프레임 보기':'전후 비교 재생';};
 button.addEventListener('click',()=>show(button.getAttribute('aria-pressed')!=='true'));
 followStops.push(()=>show(false));
});
window.addEventListener('beforeprint',()=>followStops.forEach(stop=>stop()));
document.addEventListener('visibilitychange',()=>{if(document.hidden){players.forEach(p=>p.stop());followStops.forEach(stop=>stop());}});
