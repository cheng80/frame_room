import {beforeEach, describe, expect, it, vi} from 'vitest';
import type {ReactElement} from 'react';
import type {Snapshot} from '../src/types';
import type {Studio} from '../src/useStudio';

// Exercise form events without a browser or a generation provider.
const hooks = vi.hoisted(() => ({current: null as any}));
vi.mock('react', async original => ({
  ...await original<typeof import('react')>(),
  useState: (initial: unknown) => hooks.current.state(initial),
  useEffect: () => undefined,
}));
import {ImageGenerationStep} from '../src/SourceSteps';

type Node = ReactElement<any>;
function nodes(tree: any): Node[] {
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  if (!tree || typeof tree !== 'object' || !tree.props) return [];
  return [tree, ...nodes(tree.props.children), ...nodes(tree.props.settings), ...nodes(tree.props.footer)];
}
function text(tree: any): string {
  if (typeof tree === 'string' || typeof tree === 'number') return String(tree);
  if (Array.isArray(tree)) return tree.map(text).join('');
  return tree?.props ? text(tree.props.children) : '';
}
class Harness {
  slots: any[] = []; cursor = 0; tree: any;
  constructor(public s: Studio) { this.render(); }
  state(initial: unknown) {
    const index = this.cursor++;
    this.slots[index] ??= {value: typeof initial === 'function' ? initial() : initial};
    return [this.slots[index].value, (next: any) => {
      this.slots[index].value = typeof next === 'function' ? next(this.slots[index].value) : next;
    }];
  }
  render() { this.cursor = 0; hooks.current = this; this.tree = ImageGenerationStep({s: this.s}); hooks.current = null; }
  field(label: string) { return nodes(this.tree).find(n => n.props.label === label)!; }
  change(label: string, value: unknown) { this.field(label).props.onChange(value); this.render(); }
  async click(label: string) {
    const button = nodes(this.tree).find(n => n.type === 'button' && text(n) === label)!;
    expect(button.props.disabled).not.toBe(true);
    await button.props.onClick(); this.render();
  }
}
let s: Studio;
beforeEach(() => {
  const snapshot = {projectId: 'project', generationSettings: {prompt: 'Character standing', frameCount: 1, model: 'test-model'},
    activeReferenceRevisionId: 'ref', references: [{referenceRevisionId: 'ref', identityAssetId: 'identity', approval: 'approved'}],
    assets: [{assetId: 'identity', url: '/identity.png'}], frames: [{frameVersionId: 'selected'}],
  } as unknown as Snapshot;
  s = {snapshot, commands: [], busy: false, service: {worker: 'ready'},
    providers: [{providerId: 'codex', available: true, loginReady: true, models: ['test-model'],
      capabilities: {layoutGuide: true, nativeAlphaRequest: true}}],
    job: vi.fn(async () => ({})), edit: vi.fn(), connect: vi.fn(),
  } as unknown as Studio;
});

describe('single-image layout guide', () => {
  it('defaults off and opting in submits once with transparent output request intact', async () => {
    const h = new Harness(s);
    expect(h.field('구도 가이드 사용').props.checked).toBe(false);
    h.change('구도 가이드 사용', true);
    h.change('생성 배경', {target: {value: 'transparent'}});
    expect(s.job).not.toHaveBeenCalled();
    await h.click('새 후보 생성');
    expect(s.job).toHaveBeenCalledExactlyOnceWith('generate', [], expect.objectContaining({layoutGuide: true, frameCount: 1, background: 'transparent'}));
  });
  it('persists the explicit choice in generation settings and restores it', async () => {
    const h = new Harness(s);
    h.change('구도 가이드 사용', true);
    await h.click('설정을 초안에 적용');
    expect(s.edit).toHaveBeenCalledWith({type: 'setGenerationSettings', settings: expect.objectContaining({layoutGuide: true})});
    s.snapshot!.generationSettings = vi.mocked(s.edit).mock.calls[0][0].settings;
    expect(new Harness(s).field('구도 가이드 사용').props.checked).toBe(true);
    expect(s.job).not.toHaveBeenCalled();
  });
  it('disables the one-slot guide for multi-frame sheets without changing frame count', async () => {
    const h = new Harness(s);
    h.change('구도 가이드 사용', true);
    h.change('요청 프레임 수', 8);
    expect(h.field('구도 가이드 사용').props.checked).toBe(false);
    expect(nodes(h.tree).find(n => n.type === 'fieldset')?.props.disabled).toBe(true);
    await h.click('새 후보 생성');
    expect(s.job).toHaveBeenCalledWith('generate', [], expect.objectContaining({layoutGuide: false, frameCount: 8}));
  });
  it('allows a guide for a selected replacement frame while preserving the target', async () => {
    const h = new Harness(s);
    h.change('생성 범위', {target: {value: 'frame'}});
    h.change('재생성할 프레임', {target: {value: 'selected'}});
    h.change('구도 가이드 사용', true);
    await h.click('새 후보 생성');
    expect(s.job).toHaveBeenCalledWith('generate', [], expect.objectContaining({layoutGuide: true, frameCount: 1, scope: 'frame', frameVersionId: 'selected'}));
  });
  it('does not forward a saved guide option to a provider without that capability', async () => {
    s.snapshot!.generationSettings.layoutGuide = true;
    s.providers[0].capabilities!.layoutGuide = false;
    const h = new Harness(s);
    expect(h.field('구도 가이드 사용')).toBeUndefined();
    await h.click('새 후보 생성');
    expect(s.job).toHaveBeenCalledWith('generate', [], expect.objectContaining({layoutGuide: false}));
  });
});
