import {describe,expect,it,vi} from 'vitest';

vi.mock('react',async original=>({...await original<typeof import('react')>(),useId:()=> 'property-help-test',useRef:()=>({current:null})}));
import {PropertyHelp,PropertyHeading} from '../src/PropertyHelp';

describe('property context help',()=>{
 it('connects labelled native buttons to a dismissible popover and keeps heading text separate',()=>{
  const tree=PropertyHelp({title:'동작',description:'기준 그림을 선택합니다.'});
  const [button,popup]=tree.props.children;
  expect(button.props.type).toBe('button');expect(button.props['aria-label']).toBe('동작 도움말');
  expect(button.props.popoverTarget).toBe(popup.props.id);expect(popup.props.popover).toBe('auto');
  const close=popup.props.children[0].props.children[1];
  expect(close.props.popoverTarget).toBe(popup.props.id);expect(close.props.popoverTargetAction).toBe('hide');
  const stopPropagation=vi.fn();button.props.onClick({stopPropagation});close.props.onClick({stopPropagation});expect(stopPropagation).toHaveBeenCalledTimes(2);
  const heading=PropertyHeading({title:'동작',description:'설명'});
  expect(heading.props.children[0].type).toBe('h3');expect(heading.props.children[0].props.children).toBe('동작');
 });
 it.each([
  {anchor:{right:398,top:30,bottom:54},expected:{left:'92px',top:'60px'}},
  {anchor:{right:22,top:260,bottom:284},expected:{left:'8px',top:'134px'}},
 ])('keeps help next to its trigger and inside viewport bounds',({anchor,expected})=>{
  vi.stubGlobal('window',{innerWidth:400,innerHeight:300});
  try{
   const tree=PropertyHelp({title:'항목',description:'설명'}),[button,popup]=tree.props.children;
   button.props.ref.current={getBoundingClientRect:()=>anchor};
   const style={},stopPropagation=vi.fn();
   popup.props.onToggle({currentTarget:{matches:()=>true,getBoundingClientRect:()=>({width:300,height:120}),style},stopPropagation});
   expect(style).toEqual(expected);expect(stopPropagation).toHaveBeenCalledOnce();
  }finally{vi.unstubAllGlobals();}
 });
});
