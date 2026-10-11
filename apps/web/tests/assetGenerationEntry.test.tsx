import {Children, isValidElement, type ReactElement} from 'react';
import {describe, expect, it, vi} from 'vitest';
import type {Studio} from '../src/useStudio';

vi.mock('react', async original => ({
  ...await original<typeof import('react')>(),
  useState: (value: unknown) => [value, vi.fn()],
}));
import {AssetsStep} from '../src/SourceSteps';

it('opens image generation from the asset toolbar without submitting or changing a draft', () => {
  const onGenerate = vi.fn(), onNext = vi.fn();
  const s = {snapshot: {assets: [], videos: []}, commands: [], job: vi.fn(), edit: vi.fn()} as unknown as Studio;
  const tree = AssetsStep({s, onNext, onGenerate});
  const buttons = Children.toArray(tree.props.toolbar.props.children).filter(isValidElement) as ReactElement<any>[];
  const button = buttons.find(node => node.type === 'button' && node.props.children === 'AI로 이미지 생성')!;
  expect(button.props.type).toBe('button');
  button.props.onClick();
  expect(onGenerate).toHaveBeenCalledExactlyOnceWith();
  expect(onNext).not.toHaveBeenCalled();
  expect(s.job).not.toHaveBeenCalled();
  expect(s.edit).not.toHaveBeenCalled();
  expect(button.props.disabled).not.toBe(true);
});
