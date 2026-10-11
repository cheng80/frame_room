import {describe,expect,it,vi} from 'vitest';
import {ReferenceNameInput} from '../src/ReferenceNameInput';
import type {Studio} from '../src/useStudio';
import type {Reference} from '../src/types';

const reference={referenceRevisionId:'r',name:'기존 이름'} as Reference;
function setup(options={}){const s={edit:vi.fn(),busy:false,conflict:null,...options} as unknown as Studio;return {s,input:ReferenceNameInput({s,reference})};}
describe('reference name input',()=>{
 it('commits one trimmed edit on blur, preserving spaces typed within the name',()=>{
  const {s,input}=setup(),target={value:'  효과 없는 오른쪽 측면  '};
  expect(s.edit).not.toHaveBeenCalled();input.props.onBlur({currentTarget:target});
  expect(s.edit).toHaveBeenCalledExactlyOnceWith({type:'renameReference',referenceRevisionId:'r',name:'효과 없는 오른쪽 측면'});
  expect(target.value).toBe('효과 없는 오른쪽 측면');expect(input.props.maxLength).toBe(200);
 });
 it('ignores unchanged names and clears names explicitly',()=>{
  const {s,input}=setup();input.props.onBlur({currentTarget:{value:'기존 이름'}});expect(s.edit).not.toHaveBeenCalled();
  input.props.onBlur({currentTarget:{value:'  '}});expect(s.edit).toHaveBeenCalledExactlyOnceWith({type:'renameReference',referenceRevisionId:'r',name:''});
 });
 it('commits with Enter after Korean composition and cancels with Escape',()=>{
  const {input}=setup(),target={value:'새 이름',blur:vi.fn()},preventDefault=vi.fn();
  input.props.onKeyDown({key:'Enter',nativeEvent:{isComposing:true},currentTarget:target,preventDefault});expect(target.blur).not.toHaveBeenCalled();
  input.props.onKeyDown({key:'Enter',nativeEvent:{isComposing:false},currentTarget:target,preventDefault});expect(target.blur).toHaveBeenCalledOnce();expect(preventDefault).toHaveBeenCalledOnce();
  input.props.onKeyDown({key:'Escape',currentTarget:target});expect(target.value).toBe('기존 이름');
 });
 it.each([{busy:true},{conflict:{}}])('blocks editing when busy or conflicted: %j',options=>{
  const {s,input}=setup(options);expect(input.props.disabled).toBe(true);input.props.onBlur({currentTarget:{value:'변경'}});expect(s.edit).not.toHaveBeenCalled();
 });
});
