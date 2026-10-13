import {describe,expect,it} from 'vitest';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

// Runs the shipped guide.js against a tiny stub page: only the TOC, sections and CSS offsets are real.
const source=readFileSync(new URL('../public/guide/guide.js',import.meta.url),'utf8');
const any:any=new Proxy(function(){},{get:(_,k)=>k===Symbol.toPrimitive?()=>'':any,apply:()=>any,construct:()=>any});

function load(ids:string[],{tops,margin=92,scrollY=1000,hash=''}:{tops:number[],margin?:number,scrollY?:number,hash?:string}){
 const sections=ids.map((id,i)=>({id,top:tops[i],getBoundingClientRect(){return {top:this.top};}}));
 const link=(id:string)=>{const attrs:Record<string,string>={};return {hash:'#'+id,attrs,setAttribute:(k:string,v:string)=>{attrs[k]=v;},removeAttribute:(k:string)=>{delete attrs[k];}};};
 const toc=ids.map(link),mobile=ids.map(link),progress={style:{width:''}},listeners:Record<string,()=>void>={};
 const root={scrollHeight:4800,classList:any};
 const document={documentElement:root,addEventListener:any,getElementById:(id:string)=>sections.find(s=>s.id===id)??null,
  querySelectorAll:(s:string)=>s==='.toc nav a'?toc:s==='.toc nav a, .mobile-toc a'?[...toc,...mobile]:[],
  querySelector:(s:string)=>s==='.read-progress'?progress:s==='#manual-search'?null:s==='#guide-runtime'?{textContent:'[]'}:any};
 const page:any={document,location:{protocol:'http:',hash},innerHeight:800,scrollY,Image:any,navigator:any,performance:any,requestAnimationFrame:any,cancelAnimationFrame:any,
  getComputedStyle:(el:unknown)=>el===root?{scrollPaddingTop:'100px'}:{scrollMarginTop:margin+'px'},
  addEventListener:(type:string,fn:()=>void)=>{listeners[type]=fn;}};
 page.window=page;
 runInNewContext(source,page);
 const current=()=>({toc:toc.find(a=>a.attrs['aria-current']==='location')?.hash,mobile:mobile.find(a=>a.attrs['aria-current']==='location')?.hash});
 return {page,sections,listeners,progress,current};
}

describe('guide TOC highlight',()=>{
 it('highlights the jumped-to chapter where scroll-padding + scroll-margin lands it',()=>{
  // 100px padding + 92px margin = 192px, below the old fixed 170px line.
  const g=load(['a','b','c'],{tops:[-600,192,900]});
  expect(g.current()).toEqual({toc:'#b',mobile:'#b'});
  expect(g.progress.style.width).toBe('25%');
  g.sections[1].top=194;g.listeners.scroll();
  expect(g.current().toc).toBe('#a');
 });
 it('reads the wider mobile scroll-margin',()=>{
  const g=load(['a','b'],{tops:[-600,204],margin:104});
  expect(g.current().toc).toBe('#b');
 });
 it('at the document end keeps a jumped-to section only until the reader scrolls',()=>{
  // b and c cannot reach the 192px line at the bottom; the page was opened or jumped to #b.
  const g=load(['a','b','c'],{tops:[-900,250,600],scrollY:4000,hash:'#b'});
  expect(g.current().toc).toBe('#b');
  const scroll=(y:number)=>{g.page.scrollY=y;g.sections.forEach((s,i)=>s.top=[-900,250,600][i]+4000-y);g.listeners.scroll();};
  scroll(3800);expect(g.current().toc).toBe('#a');
  scroll(4000);expect(g.current().toc).toBe('#c'); // the stale #b no longer wins
  g.page.location.hash='#c';g.listeners.hashchange();expect(g.current().toc).toBe('#c');
  g.page.location.hash='#b';g.listeners.hashchange();expect(g.current().toc).toBe('#b');
 });
});
