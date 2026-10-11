import {describe,expect,it,vi} from 'vitest';

vi.mock('react',async original=>({...await original<typeof import('react')>(),useEffect:vi.fn(),useId:()=> 'dialog-title',useRef:(value:unknown)=>({current:value})}));
import {EditorDialog} from '../src/EditorDialog';

describe('nested editor dialogs',()=>{
 it('ignores close and cancel events from a child dialog',()=>{
  const onClose=vi.fn(),dialog=EditorDialog({open:true,title:'자료 가져오기',children:null,onClose});
  const currentTarget={},target={},preventDefault=vi.fn();
  dialog.props.onClose({target,currentTarget});
  dialog.props.onCancel({target,currentTarget,preventDefault});
  expect(onClose).not.toHaveBeenCalled();expect(preventDefault).not.toHaveBeenCalled();
 });
 it('closes its own dialog and respects disabled cancellation',()=>{
  const onClose=vi.fn(),target={},preventDefault=vi.fn();
  const props={open:true,title:'자료 이미지 크게 보기',children:null,onClose};
  const dialog=EditorDialog(props);
  dialog.props.onClose({target,currentTarget:target});
  dialog.props.onCancel({target,currentTarget:target,preventDefault});
  expect(onClose).toHaveBeenCalledTimes(2);expect(preventDefault).toHaveBeenCalledOnce();
  EditorDialog({...props,closeDisabled:true}).props.onCancel({target,currentTarget:target,preventDefault});
  expect(onClose).toHaveBeenCalledTimes(2);
 });
 it('cycles keyboard focus past disabled and hidden controls without intercepting nested dialogs',()=>{
  const control=(disabled=false,visible=true)=>({tabIndex:0,matches:()=>disabled,getClientRects:()=>visible?[{}]:[],focus:vi.fn()});
  const first=control(),last=control(),disabled=control(true),hidden=control(false,false);
  const currentTarget={querySelectorAll:()=>[first,disabled,hidden,last]},target={closest:()=>currentTarget},preventDefault=vi.fn();
  const dialog=EditorDialog({open:true,title:'비교',children:null,onClose:vi.fn()});
  const documentState={activeElement:last};vi.stubGlobal('document',documentState);
  try{
   dialog.props.onKeyDown({key:'Tab',currentTarget,target,preventDefault});expect(first.focus).toHaveBeenCalledOnce();expect(preventDefault).toHaveBeenCalledOnce();
   documentState.activeElement=first;
   dialog.props.onKeyDown({key:'Tab',shiftKey:true,currentTarget,target,preventDefault});expect(last.focus).toHaveBeenCalledOnce();
   dialog.props.onKeyDown({key:'Tab',shiftKey:true,currentTarget,target:{closest:()=>({})},preventDefault});expect(last.focus).toHaveBeenCalledOnce();
  }finally{vi.unstubAllGlobals();}
 });
});
