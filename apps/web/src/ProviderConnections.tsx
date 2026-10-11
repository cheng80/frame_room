import {useState} from 'react';
import {EditorDialog} from './EditorDialog';
import type {Health,Provider} from './types';

const entries=[['codex','GPT 이미지'],['grok-video','Grok 영상']] as const;
type Status='ready'|'warning'|'unknown'|'checking';

export function ProviderConnections({providers,service,checking,error,onCheck}:{providers:Provider[];service:Health|null;checking:boolean;error:string;onCheck:()=>void}) {
 const [open,setOpen]=useState(false);
 const byId=new Map((providers||[]).map(provider=>[provider.providerId,provider]));
 const status=(provider?:Provider):Status=>checking?'checking':!provider||service?.api!=='ready'||!!error?'unknown':provider.available===true&&provider.loginReady===true?'ready':provider.available===false||provider.loginReady===false?'warning':'unknown';
 const label=(value:Status)=>({ready:'연결 준비됨',warning:'연결 확인 필요',unknown:'확인 불가',checking:'확인 중'}[value]);
 const login=(provider:Provider|undefined,value:Status)=>value==='checking'||value==='unknown'?'확인 불가':provider?.loginReady===true?'확인됨':provider?.loginReady===false?'확인 필요':'확인 불가';
 return <section className="provider-connections" aria-label="생성 제공자 연결 상태">
  {entries.map(([id,name])=>{const provider=byId.get(id),value=status(provider);return <button key={id} type="button" className={`provider-connection ${value}`} onClick={()=>setOpen(true)}>{name} · {label(value)}</button>;})}
  <EditorDialog open={open} title="모델 연결 확인" onClose={()=>setOpen(false)} className="provider-connection-dialog" actions={<button type="button" disabled={checking} onClick={onCheck}>연결 다시 확인</button>}>
   <div className="provider-connection-details">
    {entries.map(([id,name])=>{const provider=byId.get(id),value=status(provider),models=[provider?.defaultModel,provider?.model,...(provider?.models||[]).map(model=>typeof model==='string'?model:model.name?`${model.name} (${model.id})`:model.id)].filter((model,index,list):model is string=>!!model&&list.indexOf(model)===index);return <section className="provider-connection-card" key={id}>
     <h3>{name}</h3><dl className="facts">
      <dt>준비 상태</dt><dd><span className={`provider-connection ${value}`}>{label(value)}</span></dd>
      <dt>로그인 상태</dt><dd>{login(provider,value)}</dd>
      <dt>최근 실제 생성 이력</dt><dd>{provider?.lastSuccess?'성공 이력 있음':'확인된 이력 없음'}</dd>
      {provider?.reason||provider?.disabledReason?<><dt>안내</dt><dd>{provider.reason||provider.disabledReason}</dd></>:null}
      <dt>모델</dt><dd>{models.length?models.join(', '):'확인 불가'}</dd>
     </dl>
    </section>;})}
    <p>로그인 확인은 실제 생성 성공이나 남은 사용량을 보장하지 않습니다.</p>
    {error?<p role="alert">{error}</p>:null}
   </div>
  </EditorDialog>
 </section>;
}
