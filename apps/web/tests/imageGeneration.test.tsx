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
import {ImageGenerationStep} from '../src/GenerationStep';
import {VideoBasePreset} from '../src/VideoBasePreset';

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
  constructor(public s: Studio, public assetMode = false, public initialReferenceRevisionId?: string) { this.render(); }
  state(initial: unknown) {
    const index = this.cursor++;
    this.slots[index] ??= {value: typeof initial === 'function' ? initial() : initial};
    return [this.slots[index].value, (next: any) => {
      this.slots[index].value = typeof next === 'function' ? next(this.slots[index].value) : next;
    }];
  }
  render() { this.cursor = 0; hooks.current = this; this.tree = ImageGenerationStep({s: this.s, assetMode: this.assetMode, initialReferenceRevisionId: this.initialReferenceRevisionId}); hooks.current = null; }
  field(label: string) { return nodes(this.tree).find(n => n.props.label === label)!; }
  change(label: string, value: unknown) { this.field(label).props.onChange(value); this.render(); }
  videoBase(changes: object) {
    const form = nodes(this.tree).find(n => n.type === VideoBasePreset)!;
    form.props.onChange({...form.props.value, ...changes}); this.render();
  }
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
    providers: [{providerId: 'codex', available: true, loginReady: true, defaultModel: 'test-model', models: ['test-model'],
      capabilities: {layoutGuide: true, nativeAlphaRequest: true}}],
    job: vi.fn(async () => ({})), edit: vi.fn(), connect: vi.fn(),
  } as unknown as Studio;
});

describe('image preparation for Grok video', () => {
  it('generates one new asset without an approved reference or changing animation settings', async () => {
    s.snapshot!.references = [];
    s.snapshot!.activeReferenceRevisionId = null;
    s.snapshot!.generationSettings = {prompt: '기존 동작 설명', frameCount: 8, imageUse: 'grok-video', videoBase: {bodyPlan: 'biped'}};
    const before = structuredClone(s.snapshot);
    const h = new Harness(s, true);
    expect(h.field('만들 이미지 설명').props.children.props.value).toBe('');
    expect(h.field('Grok 영상 사용')).toBeUndefined();
    expect(h.field('구도 가이드 사용')).toBeUndefined();
    expect(h.field('요청 프레임 수')).toBeUndefined();
    h.field('만들 이미지 설명').props.children.props.onChange({target: {value: '여덟 다리 거미, 선명한 픽셀 아트'}});
    h.render();
    expect(s.job).not.toHaveBeenCalled();
    await h.click('자료 이미지 1장 생성');
    expect(s.job).toHaveBeenCalledExactlyOnceWith('generate', [], {
      providerId: 'codex', model: 'test-model', prompt: '여덟 다리 거미, 선명한 픽셀 아트',
      background: 'transparent', frameCount: 1, layoutGuide: false, scope: 'asset',
    });
    expect(s.edit).not.toHaveBeenCalled();
    expect(s.snapshot).toEqual(before);
  });
  it.each(['side', 'front', 'back', 'front_diagonal', 'back_diagonal'])('replaces legacy side directives for %s while keeping the source description', async direction => {
    const original = '오른손에 황금 스태프. 오른쪽을 보는 정확한 측면의 이동 중간 자세. 광채와 입자는 제외한다.';
    s.snapshot!.generationSettings.prompt = original;
    const h = new Harness(s);
    h.change('Grok 영상 사용', {target: {value: 'grok-video'}});
    h.videoBase({direction, facing: 'left', equipment: 'staff:right', bodyPlan: 'biped'});
    const preview = h.field('방향이 반영된 생성 설명').props.children.props.value;
    expect(preview.split('영상 시작용')[0]).not.toContain('측면');
    expect(preview).toContain('오른손에 황금 스태프');
    expect(preview).toContain('이동 중간 자세');
    expect(preview).toContain('광채와 입자는 제외한다');
    expect(h.field('동작과 포즈 설명').props.children.props.value).toBe(original);
    await h.click('새 후보 생성');
    expect(vi.mocked(s.job).mock.calls[0][2]).toMatchObject({viewDirection: direction, viewFacing: 'left', equipment: 'staff:right', bodyPlan: 'biped', frameCount: 1});
    await h.click('설정을 초안에 적용');
    const saved = vi.mocked(s.edit).mock.calls[0][0].settings;
    expect(saved.prompt).toBe(original);
    for (const field of ['viewDirection', 'viewFacing', 'bodyPlan', 'equipment']) expect(saved).not.toHaveProperty(field);
    expect(saved.videoBase.direction).toBe(direction);
  });
  it('keeps image-only generation unchanged by default', async () => {
    s.snapshot!.generationSettings.frameCount = 8;
    const h = new Harness(s);
    expect(h.field('Grok 영상 사용').props.value).toBe('frames');
    await h.click('새 후보 생성');
    expect(s.job).toHaveBeenCalledExactlyOnceWith('generate', [], expect.objectContaining({prompt: 'Character standing', frameCount: 8, scope: 'states'}));
  });
  it('uses a selected saved draft reference for generation without creating approval records', async () => {
    s.snapshot!.references = [
      {referenceRevisionId: 'ref', identityAssetId: 'identity', approval: 'draft'},
      {referenceRevisionId: 'saved', identityAssetId: 'identity', approval: 'draft'},
    ] as any;
    s.snapshot!.activeReferenceRevisionId = 'ref';
    const h = new Harness(s);
    h.change('이번 생성에 사용할 저장 기준', {target: {value: 'saved'}});
    await h.click('새 후보 생성');
    expect(s.job).toHaveBeenCalledExactlyOnceWith('generate', [], expect.objectContaining({referenceRevisionId: 'saved'}));
    expect(s.edit).not.toHaveBeenCalled();
  });
  it('uses the selected clip reference before the project active reference', async () => {
    s.snapshot!.references.push({referenceRevisionId: 'clip-reference', identityAssetId: 'clip-identity', approval: 'draft'} as any);
    s.snapshot!.assets.push({assetId: 'clip-identity', url: '/clip.png'} as any);
    const h = new Harness(s, false, 'clip-reference');
    expect(h.field('이번 생성에 사용할 저장 기준').props.value).toBe('clip-reference');
    await h.click('새 후보 생성');
    expect(s.job).toHaveBeenCalledWith('generate', [], expect.objectContaining({referenceRevisionId: 'clip-reference'}));
  });
  it('submits one base picture with selected view, equipment and no effects, without a Grok request', async () => {
    const h = new Harness(s);
    h.change('요청 프레임 수', 8);
    h.change('Grok 영상 사용', {target: {value: 'grok-video'}});
    h.videoBase({direction: 'side', facing: 'left', equipment: 'staff:right'});
    h.change('구도 가이드 사용', true);
    expect(s.job).not.toHaveBeenCalled();
    expect(s.edit).not.toHaveBeenCalled();
    expect(h.field('요청 프레임 수')).toBeUndefined();
    await h.click('새 후보 생성');
    expect(s.job).toHaveBeenCalledExactlyOnceWith('generate', [], expect.objectContaining({frameCount: 1, scope: 'states', layoutGuide: true}));
    const params = vi.mocked(s.job).mock.calls[0][2];
    expect(params.prompt).toContain('Character standing');
    expect(params.prompt).toContain('왼쪽을 향한다');
    expect(params.prompt).toContain('staff:right');
    expect(params.prompt).toContain('광채·후광·입자·마법 효과·잔상·바닥 그림자를 제외');
    expect(params).not.toHaveProperty('imageUse');
    expect(params).not.toHaveProperty('videoBase');
    expect(params).not.toHaveProperty('frameVersionId');
  });
  it('restores the sheet settings and original prompt when switching back', async () => {
    const h = new Harness(s);
    h.change('생성 범위', {target: {value: 'sheet'}});
    h.change('요청 프레임 수', 8);
    h.change('Grok 영상 사용', {target: {value: 'grok-video'}});
    h.change('Grok 영상 사용', {target: {value: 'frames'}});
    expect(h.field('생성 범위').props.value).toBe('sheet');
    expect(h.field('요청 프레임 수').props.value).toBe(8);
    await h.click('새 후보 생성');
    expect(s.job).toHaveBeenCalledWith('generate', [], expect.objectContaining({frameCount: 8, scope: 'sheet', prompt: 'Character standing'}));
  });
  it('saves raw settings and restores video guidance without duplicating it', async () => {
    const h = new Harness(s);
    h.change('요청 프레임 수', 8);
    h.change('Grok 영상 사용', {target: {value: 'grok-video'}});
    h.videoBase({direction: 'back', pose: 'idle'});
    await h.click('설정을 초안에 적용');
    const saved = vi.mocked(s.edit).mock.calls[0][0].settings;
    expect(saved).toMatchObject({prompt: 'Character standing', frameCount: 8, imageUse: 'grok-video', videoBase: {direction: 'back', pose: 'idle'}});
    s.snapshot!.generationSettings = saved;
    const restored = new Harness(s);
    expect(restored.field('Grok 영상 사용').props.value).toBe('grok-video');
    await restored.click('새 후보 생성');
    expect(vi.mocked(s.job).mock.calls[0][2].prompt.match(/영상 시작용/g)).toHaveLength(1);
    restored.change('Grok 영상 사용', {target: {value: 'frames'}});
    expect(restored.field('요청 프레임 수').props.value).toBe(8);
  });
  it('replaces frame regeneration only for the video request and restores its target', async () => {
    const h = new Harness(s);
    h.change('생성 범위', {target: {value: 'frame'}});
    h.change('재생성할 프레임', {target: {value: 'selected'}});
    h.change('Grok 영상 사용', {target: {value: 'grok-video'}});
    await h.click('새 후보 생성');
    expect(vi.mocked(s.job).mock.calls[0][2]).toMatchObject({scope: 'states', frameCount: 1});
    expect(vi.mocked(s.job).mock.calls[0][2]).not.toHaveProperty('frameVersionId');
    h.change('Grok 영상 사용', {target: {value: 'frames'}});
    expect(h.field('재생성할 프레임').props.value).toBe('selected');
  });
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
