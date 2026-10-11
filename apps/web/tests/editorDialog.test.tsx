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
});
