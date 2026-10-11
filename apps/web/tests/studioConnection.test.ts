import {beforeEach,describe,expect,it,vi} from 'vitest';
import type {Health,Provider} from '../src/types';

const hooks=vi.hoisted(()=>({current:null as any}));
vi.mock('react',async original=>({...await original<typeof import('react')>(),
 useState:(initial:unknown)=>hooks.current.state(initial),
 useRef:(initial:unknown)=>hooks.current.ref(initial),
 useMemo:(compute:()=>unknown)=>compute(),useEffect:vi.fn(),
}));
vi.mock('../src/api',async original=>({...await original<typeof import('../src/api')>(),health:vi.fn(),api:vi.fn()}));
import {useStudio,type Studio} from '../src/useStudio';
import {api,health} from '../src/api';

class Harness {
 slots:any[]=[];cursor=0;s!:Studio;
 state(initial:unknown){const slot=this.slots[this.cursor++]??={value:initial};return [slot.value,(next:any)=>{slot.value=typeof next==='function'?next(slot.value):next;}];}
 ref(initial:unknown){return this.slots[this.cursor++]??={current:initial};}
 render(){this.cursor=0;hooks.current=this;try{this.s=useStudio();}finally{hooks.current=null;}}
 constructor(){this.render();}
}
const ready:Health={api:'ready',worker:'ready',sessionToken:'test'};
const providers:Provider[]=[{providerId:'codex',available:true,loginReady:true},{providerId:'grok-video',available:false,loginReady:false}];
beforeEach(()=>{
 vi.mocked(health).mockReset().mockResolvedValue(ready);
 vi.mocked(api).mockReset().mockImplementation(async path=>path==='/projects'?{projects:[]}:{providers});
});

describe('connection refresh',()=>{
 it('tracks checking and fetches independent provider states without editing drafts',async()=>{
  const h=new Harness();const commands=[{operation:{type:'updateCharacter',name:'초안'}}];h.s.setCommands(commands);h.render();
  const request=h.s.connect();h.render();expect(h.s.providersChecking).toBe(true);
  await request;h.render();expect(h.s.providersChecking).toBe(false);expect(h.s.providersError).toBe('');
  expect(h.s.service).toEqual(ready);expect(h.s.providers).toEqual(providers);expect(h.s.commands).toBe(commands);
  expect(api).toHaveBeenCalledWith('/providers');
 });
 it('clears cached provider readiness on lookup failure while retaining the healthy local server',async()=>{
  const h=new Harness();await h.s.connect();h.render();
  vi.mocked(api).mockImplementation(async path=>{if(path==='/providers')throw new Error('probe unavailable');return {projects:[]};});
  await h.s.connect();h.render();expect(h.s.service).toEqual(ready);expect(h.s.providers).toEqual([]);
  expect(h.s.providersError).toContain('모델');expect(h.s.providersChecking).toBe(false);
 });
 it('clears cached readiness after server failure and recovers on the next check',async()=>{
  const h=new Harness();await h.s.connect();h.render();vi.mocked(health).mockRejectedValueOnce(new Error('offline'));
  await h.s.connect();h.render();expect(h.s.service).toBeNull();expect(h.s.providers).toEqual([]);expect(h.s.providersError).toContain('로컬 서버');
  await h.s.connect();h.render();expect(h.s.providersError).toBe('');expect(h.s.providers).toEqual(providers);
 });
 it('does not duplicate checks while a check is pending',async()=>{
  let finish!:(value:Health)=>void;vi.mocked(health).mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
  const h=new Harness();const first=h.s.connect();const second=h.s.connect();await second;
  expect(health).toHaveBeenCalledTimes(1);finish(ready);await first;h.render();expect(h.s.providersChecking).toBe(false);
 });
 it('still checks providers when only the project list fails',async()=>{
  vi.mocked(api).mockImplementation(async path=>{if(path==='/projects')throw new Error('list unavailable');return {providers};});
  const h=new Harness();await h.s.connect();h.render();expect(h.s.service).toEqual(ready);expect(h.s.providers).toEqual(providers);expect(h.s.providersError).toBe('');
 });
});
