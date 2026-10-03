import type {Health} from './types';
export class ApiError extends Error {constructor(public status:number,public code:string,message:string,public details:unknown=null){super(message)}}
let token='';
export async function api<T>(path:string,method='GET',body?:unknown):Promise<T>{
 const headers:Record<string,string>={}; if(method!=='GET')headers['X-Session-Token']=token;
 if(body!==undefined && !(body instanceof FormData))headers['Content-Type']='application/json';
 let r:Response;try{r=await fetch(`/v1${path}`,{method,headers,body:body instanceof FormData?body:body===undefined?undefined:JSON.stringify(body)});}catch{throw new ApiError(0,'OFFLINE','서버에 연결할 수 없습니다. 편집 초안은 이 브라우저에 보존됩니다.');}
 const data=await r.json().catch(()=>({}));
 if(!r.ok){const e=data.detail&&typeof data.detail==='object'&&!Array.isArray(data.detail)?data.detail:data;throw new ApiError(r.status,e.code||`HTTP_${r.status}`,e.message||({409:'다른 변경 또는 처리 중인 작업이 있습니다.',413:'업로드 크기 한도를 초과했습니다.',422:'입력값을 확인해 주세요.',424:'먼저 필요한 자료를 준비해 주세요.'}[r.status]??'요청을 완료하지 못했습니다.'),e.details||data.detail);}
 return data as T;
}
export async function health(){const h=await api<Health>('/health');token=h.sessionToken;return h;}
export function downloadJson(name:string,value:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),500);}
