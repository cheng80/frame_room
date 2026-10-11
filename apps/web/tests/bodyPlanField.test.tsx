import {Children, isValidElement, type ReactElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {BodyPlanField, bodyPlanLabel} from '../src/BodyPlanField';
import {Select} from '../src/ui';

function field(value: string) {
  const onChange = vi.fn();
  const props = {label: '기준 그림의 신체 구조', value, onChange};
  const tree = BodyPlanField(props);
  const select = Children.toArray(tree.props.children).find(child => isValidElement(child) && child.type === Select) as ReactElement<any>;
  const options = Children.toArray(select.props.children).filter(isValidElement) as ReactElement<any>[];
  return {onChange, select, options, html: renderToStaticMarkup(<BodyPlanField {...props}/>)};
}

describe('Korean body plan dropdown', () => {
  it('offers only the supported shapes with Korean names and no text input', () => {
    const {options, html} = field('biped');
    expect(options.map(option => [option.props.value, option.props.children])).toEqual([
      ['reference', '기준 그림의 구조 그대로 유지'],
      ['biped', '두 발형 · 인간·두 발 몬스터'],
      ['quadruped', '네 발형 · 동물·네 발 몬스터'],
      ['legless', '다리 없는 형태 · 슬라임·뱀'],
      ['arachnid', '여덟 다리형 · 거미'],
      ['winged_biped', '두 발·날개형 · 새·와이번'],
      ['winged_quadruped', '네 발·날개형 · 드래곤'],
    ]);
    expect(html).toContain('<select');
    expect(html).not.toMatch(/<input|<textarea|<details/);
  });
  it.each(['reference', 'biped', 'quadruped', 'legless', 'arachnid', 'winged_biped', 'winged_quadruped'])('emits the %s value only when selected', value => {
    const {select, onChange} = field('');
    expect(onChange).not.toHaveBeenCalled();
    select.props.onChange({target: {value}});
    expect(onChange).toHaveBeenCalledExactlyOnceWith(value);
    expect(bodyPlanLabel(value)).not.toMatch(/[a-z]/i);
  });
  it.each(['', '  ', ' BIPED ', ' QUADRUPED '])('shows a known legacy value without rewriting it: %j', value => {
    const {onChange, select} = field(value);
    expect(select.props.value).toBe(value.trim().toLowerCase() || 'biped');
    expect(onChange).not.toHaveBeenCalled();
  });
  it.each(['the rider=biped; the horse=quadruped', 'legacy-unknown'])('preserves legacy %j without allowing direct entry', value => {
    const {onChange, select, options, html} = field(value);
    expect(select.props.value).toBe(value);
    expect(options.at(-1)?.props).toMatchObject({value, disabled: true, children: '기존 복합 설정 · 유지 중'});
    expect(html).not.toMatch(/<input|<textarea|<details/);
    expect(onChange).not.toHaveBeenCalled();
    select.props.onChange({target: {value: 'quadruped'}});
    expect(onChange).toHaveBeenCalledExactlyOnceWith('quadruped');
  });
});
