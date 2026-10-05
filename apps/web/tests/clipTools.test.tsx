import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import type {ReactElement} from 'react';
import type {Clip, Job, Snapshot} from '../src/types';
import type {Studio} from '../src/useStudio';

// Node-only hook lifecycle and SSR tests; no browser or real worker/media requests.
const hooks = vi.hoisted(() => ({current: null as any}));
vi.mock('react', async original => {
  const actual = await original<typeof import('react')>();
  return {...actual,
    useState: (initial: unknown) => hooks.current ? hooks.current.state(initial) : actual.useState(initial),
    useRef: (initial: unknown) => hooks.current ? hooks.current.ref(initial) : actual.useRef(initial),
    useEffect: (setup: () => unknown, deps: unknown[]) => hooks.current ? hooks.current.effect(setup, deps) : actual.useEffect(setup as any, deps),
    useId: () => hooks.current ? 'clip-test' : actual.useId(),
  };
});
vi.mock('../src/render', async original => ({...await original<typeof import('../src/render')>(), drawOccurrence: vi.fn(), loadImage: vi.fn()}));
import {ClipTools, ClipToolComparison, RegionSelector} from '../src/ClipToolsPanel';
import {drawOccurrence, loadImage} from '../src/render';
import {assetProvenanceLabel} from '../src/assetProvenance';
import {artifactUrl, defaultFollow, defaultHanded, followParams, handedParams, jobSucceeded, previewMatches, readClipToolResult, regionFromDrag, settingsKey, sourceOf, validateClipSource, type ClipToolResult, type FollowFields, type ToolRequest} from '../src/clipTools';

type Node = ReactElement<any>;
function nodes(tree: any): Node[] {
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  if (!tree || typeof tree !== 'object' || !tree.props) return [];
  return [tree, ...nodes(tree.props.children)];
}
function text(tree: any): string {
  if (typeof tree === 'string' || typeof tree === 'number') return String(tree);
  if (Array.isArray(tree)) return tree.map(text).join('');
  return tree?.props ? text(tree.props.children) : '';
}
const mounted: Harness[] = [];
class Harness {
  slots: any[] = []; cursor = 0; dirty = false; tree: any; effects: (() => void)[] = [];
  context = {clearRect: vi.fn(), drawImage: vi.fn(), imageSmoothingEnabled: true};
  constructor(public component: (props: any) => any, public props: any) {mounted.push(this); this.render();}
  state(initial: unknown) {
    const slot = this.slots[this.cursor++] ??= {value: typeof initial === 'function' ? initial() : initial};
    return [slot.value, (next: any) => {const value = typeof next === 'function' ? next(slot.value) : next; if (!Object.is(value, slot.value)) {slot.value = value; this.dirty = true;}}];
  }
  ref(initial: unknown) {return this.slots[this.cursor++] ??= {current: initial};}
  effect(setup: () => any, deps: unknown[]) {
    const i = this.cursor++, previous = this.slots[i];
    if (previous && deps.length === previous.deps.length && deps.every((dep, j) => Object.is(dep, previous.deps[j]))) return;
    this.effects.push(() => {previous?.cleanup?.(); this.slots[i] = {deps, cleanup: setup()};});
  }
  render(next?: any) {
    if (next) this.props = next;
    let renders = 0;
    do {
      if (++renders > 20) throw new Error('hook render loop');
      this.cursor = 0; this.dirty = false; this.effects = []; hooks.current = this;
      try {this.tree = this.component(this.props);} finally {hooks.current = null;}
      for (const node of nodes(this.tree)) if (node.type === 'canvas' && node.props.ref) node.props.ref.current = {getContext: () => this.context};
      this.effects.forEach(run => run());
    } while (this.dirty);
  }
  field(label: string) {const node = nodes(this.tree).find(n => n.props.label === label); if (!node) throw new Error(`No field: ${label}`); return node;}
  change(label: string, value: string) {this.field(label).props.onChange({target: {value}}); this.render();}
  button(label: string) {const node = nodes(this.tree).find(n => n.type === 'button' && text(n) === label); if (!node) throw new Error(`No button: ${label}`); return node;}
  async click(label: string, force = false) {const node = this.button(label); if (!force) expect(node.props.disabled).not.toBe(true); node.props.onClick(); await this.flush();}
  async submit() {nodes(this.tree).find(n => n.type === 'form')!.props.onSubmit({preventDefault: vi.fn()}); await this.flush();}
  async flush() {for (let i = 0; i < 6; i++) await Promise.resolve(); this.render();}
  unmount() {this.slots.forEach(slot => slot?.cleanup?.());}
}
const clip = {clipId: 'clip', clipRevisionId: 'clip-r1', name: '걷기', loop: true, stateId: 'walk', review: 'pending', occurrences: [80, 120, 100, 200].map((durationMs, i) => ({occurrenceId: `slot-${i}`, frameVersionId: 'frame', durationMs}))} as Clip;
const project = {
  projectId: 'project', revision: 7, clips: [clip],
  frames: [{frameVersionId: 'frame', nativeScaleGroupId: 'group', imageAssetId: 'asset', rawAssetId: 'asset', review: 'pending'}],
  alignmentGroups: [{alignmentGroupId: 'group', frameVersionIds: ['frame'], cell: {width: 64, height: 64}}], alignments: {},
  assets: [{assetId: 'asset', originalFilename: '투명 기준.png', width: 64, height: 64, alphaStats: {transparent: 100}, url: '/original.png'}, {assetId: 'opaque', originalFilename: '불투명.png', alphaStats: {transparent: 0}, url: '/opaque.png'}],
} as unknown as Snapshot;
const validFields = (): FollowFields => ({...defaultFollow(), region: ['32', '32', '10', '12']});
function resultJob(tool: 'follow' | 'handed' = 'follow', snapshot = project): Job {
  const result = {
    version: 'clip-tools-v1', tool, source: sourceOf(snapshot, snapshot.clips[0]),
    settings: tool === 'follow' ? followParams(snapshot, snapshot.clips[0], validFields()) : {...handedParams(snapshot, snapshot.clips[0], {...defaultHanded(), item: '시계'}), state: 'walk'},
    preview: {width: 64, height: 64, frameCount: 4, durationsMs: [80, 120, 100, 200], before: 'before/animation.webp', beforeStrip: 'before/strip.png', firstFrame: 'before/000.png', ...(tool === 'follow' ? {after: 'after/animation.webp', afterStrip: 'after/strip.png'} : {board: 'handed-board.png'})},
    report: tool === 'follow' ? {gainRequested: 2.5, gainApplied: 2.5, foldLimited: false} : {verdict: 'suspect', framesShown: 3, frameCount: 4, suspectFrames: [{index: 2, occurrenceId: 'slot-2', reasons: ['장비가 반대쪽에 보입니다.']}], unchecked: ['가려진 장비의 전체 모양은 검사하지 못했습니다.']},
  } as ClipToolResult;
  return {jobId: tool === 'follow' ? 'preview-1' : 'check-1', status: 'succeeded', operation: tool === 'follow' ? 'preview_follow' : 'check_handed', inputRevision: snapshot.revision, result: result as Job['result'], artifacts: Object.entries(result.preview).filter(([key]) => ['before', 'after', 'beforeStrip', 'afterStrip', 'firstFrame', 'board'].includes(key)).map(([, name], i) => ({artifactId: `artifact-${i}`, name: name as string, url: `/v1/artifacts/${i}`}))};
}
let s: Studio;
function studioHarness() {return new Harness(ClipTools, {s, clipId: 'clip', onClip: vi.fn(), onSelectOccurrence: vi.fn()});}
function setRegion(h: Harness) {['중심 X', '중심 Y', '반지름 X', '반지름 Y'].forEach((label, i) => h.change(label, validFields().region[i]));}
async function preview(h: Harness) {vi.mocked(s.job).mockResolvedValueOnce({jobId: 'preview-1', status: 'queued'}); setRegion(h); await h.submit(); s.jobs = [resultJob()]; h.render();}
function request(job = resultJob()): ToolRequest {return {job, source: sourceOf(project, clip), settingsKey: settingsKey(validFields())};}
beforeEach(() => {
  vi.mocked(drawOccurrence).mockReset().mockResolvedValue({width: 64, height: 64} as HTMLCanvasElement);
  vi.mocked(loadImage).mockReset().mockImplementation(async url => ({width: 256, height: 64, src: url}) as HTMLImageElement);
  s = {base: structuredClone(project), snapshot: structuredClone(project), commands: [], conflict: null, busy: false, service: {worker: 'ready'}, jobs: [], resolveId: (id: string) => id, job: vi.fn(async () => ({jobId: 'queued', status: 'queued'})), edit: vi.fn()} as unknown as Studio;
});
afterEach(() => {mounted.splice(0).forEach(h => h.unmount()); vi.restoreAllMocks();});

describe('saved clip request validation', () => {
  it('sends the four region coordinates and all follow controls from the saved clip', async () => {
    const original = structuredClone(project), h = studioHarness(); setRegion(h);
    s.snapshot!.clips[0].clipRevisionId = 'unsaved-preview';
    h.change('흔들림 강도', '3'); h.change('반응 주파수 (Hz)', '4'); h.change('감쇠', '1'); h.change('과도한 접힘이 생길 때', 'refuse');
    await h.submit();
    expect(s.job).toHaveBeenCalledWith('preview_follow', [], {clipId: 'clip', clipRevisionId: 'clip-r1', region: [32, 32, 10, 12], gain: 3, freq: 4, damping: 1, onFold: 'refuse'});
    expect(s.base).toEqual(original); expect(s.edit).not.toHaveBeenCalled();
  });
  it.each(['dirty', 'conflict', 'busy', 'worker'])('blocks requests while %s, including direct handler invocation', async reason => {
    const h = studioHarness(); setRegion(h);
    if (reason === 'dirty') s.commands = [{operation: {type: 'updateClip'}}];
    if (reason === 'conflict') s.conflict = project;
    if (reason === 'busy') s.busy = true;
    if (reason === 'worker') s.service = null;
    h.render(); expect(h.button('흔들림 미리보기').props.disabled).toBe(true); await h.submit(); expect(s.job).not.toHaveBeenCalled();
  });
  it.each([['region', ['', '32', '10', '10']], ['region', ['32', '32', '0', '10']], ['region', ['63', '32', '10', '10']], ['region', ['NaN', '32', '10', '10']], ['gain', 'Infinity'], ['gain', '8.1'], ['freq', '0.1'], ['damping', ''], ['onFold', 'unknown']])('rejects invalid %s before submission', (key, value) => {
    expect(() => followParams(project, clip, {...validFields(), [key]: value} as FollowFields)).toThrow();
  });
  it('requires explicit region entry rather than selecting the whole sprite by default', async () => {const h = studioHarness(); expect(h.button('흔들림 미리보기').props.disabled).toBe(true); await h.submit(); expect(s.job).not.toHaveBeenCalled();});
  it('enforces loop, frame count, timing, cell and aggregate pixel limits', () => {
    expect(validateClipSource(project, {...clip, loop: false}, true)).toContain('반복');
    expect(validateClipSource(project, {...clip, occurrences: clip.occurrences.slice(0, 3)}, true)).toContain('4~64');
    expect(validateClipSource(project, {...clip, occurrences: Array(65).fill(clip.occurrences[0])}, false)).toContain('1~64');
    expect(validateClipSource(project, {...clip, occurrences: clip.occurrences.map(o => ({...o, durationMs: 16000}))}, true)).toContain('60초');
    const big = structuredClone(project); big.alignmentGroups[0].cell = {width: 1024, height: 1024, edge: 0};
    expect(validateClipSource(big, {...clip, occurrences: Array(17).fill(clip.occurrences[0])}, true)).toContain('16,777,216');
    big.alignmentGroups[0].cell.width = 1025; expect(validateClipSource(big, clip, false)).toContain('1024');
    expect(validateClipSource({...project, alignmentGroups: []}, clip, false)).toContain('정렬 그룹');
  });
  it('includes optional transparent reference, omits empty reference and filters opaque choices', async () => {
    const h = studioHarness(); h.change('보완·검사 도구', 'handed'); h.change('장비 이름', ' 시계 ');
    const options = nodes(h.field('장비가 온전히 보이는 투명 기준 그림 (선택)')).filter(n => n.type === 'option').map(n => n.props.value);
    expect(options).toEqual(['', 'asset']); expect(text(h.tree)).toContain('투명 픽셀이 있는');
    h.change('착용 좌우', 'left'); h.change('착용 부위', 'wrist'); h.change('보는 시점', 'front_diagonal'); h.change('바라보는 방향', 'left'); h.change('표식 색 코드', '#20aaee'); h.change('장비가 온전히 보이는 투명 기준 그림 (선택)', 'asset');
    await h.submit(); expect(s.job).toHaveBeenCalledWith('check_handed', [], {clipId: 'clip', clipRevisionId: 'clip-r1', item: '시계', side: 'left', part: 'wrist', direction: 'front_diagonal', facing: 'left', marker: '#20aaee', referenceAssetId: 'asset'});
    expect(handedParams(project, clip, {...defaultHanded(), item: '시계'})).not.toHaveProperty('referenceAssetId');
  });
  it.each([{item: ''}, {marker: '#eeeeee'}, {marker: '#ff'}, {side: 'screen-left'}, {referenceAssetId: 'opaque'}, {referenceAssetId: 'other-project'}])('rejects handed inputs %j', fields => {expect(() => handedParams(project, clip, {...defaultHanded(), item: '시계', ...fields})).toThrow();});
});

describe('job lifecycle and stale selections', () => {
  it('prevents double submission before the next React render', async () => {
    let finish!: (value: unknown) => void; vi.mocked(s.job).mockImplementation(() => new Promise(resolve => {finish = resolve;}));
    const h = studioHarness(); setRegion(h); const submit = nodes(h.tree).find(n => n.type === 'form')!.props.onSubmit;
    submit({preventDefault: vi.fn()}); submit({preventDefault: vi.fn()}); expect(s.job).toHaveBeenCalledOnce();
    finish({jobId: 'preview-1', status: 'queued'}); await h.flush();
  });
  it.each(['clip', 'project'])('resets fields and discards async response after %s selection changes', async change => {
    let finish!: (value: unknown) => void; vi.mocked(s.job).mockImplementation(() => new Promise(resolve => {finish = resolve;}));
    const h = studioHarness(); setRegion(h); const pending = h.submit();
    if (change === 'clip') {s.base!.clips.push({...structuredClone(clip), clipId: 'other'}); h.render({...h.props, clipId: 'other'});}
    else {s.base = {...structuredClone(project), projectId: 'other'}; h.render();}
    expect(h.field('중심 X').props.value).toBe('');
    finish(resultJob()); await pending; await h.flush(); expect(nodes(h.tree).some(n => n.type === ClipToolComparison)).toBe(false); expect(h.props.onClip).not.toHaveBeenCalled();
    setRegion(h); expect(h.button('흔들림 미리보기').props.disabled).toBe(false);
  });
  it('discards an accepted request after unmount', async () => {
    let finish!: (value: unknown) => void; vi.mocked(s.job).mockImplementation(() => new Promise(resolve => {finish = resolve;}));
    const h = studioHarness(); setRegion(h); const pending = h.submit(); h.unmount(); finish(resultJob()); await pending;
    expect(h.props.onClip).not.toHaveBeenCalled(); expect(nodes(h.tree).some(n => n.type === ClipToolComparison)).toBe(false);
  });
  it.each(['settings', 'revision', 'clipRevision', 'order'])('blocks apply when %s changes after preview', async change => {
    const h = studioHarness(); await preview(h); expect(h.button('새 동작으로 저장').props.disabled).toBe(false);
    if (change === 'settings') h.change('흔들림 강도', '4');
    if (change === 'revision') s.base = {...s.base!, revision: 8};
    if (change === 'clipRevision') s.base!.clips[0].clipRevisionId = 'r2';
    if (change === 'order') s.base!.clips[0].occurrences.reverse();
    h.render(); expect(h.button('새 동작으로 저장').props.disabled).toBe(true); await h.click('새 동작으로 저장', true); expect(s.job).toHaveBeenCalledOnce();
    expect(text(h.tree)).toContain('다시 실행하세요');
  });
  it('accepts only succeeded preview jobs and matching normalized settings/artifact names', () => {
    const job = resultJob(), source = sourceOf(project, clip);
    expect(previewMatches(request(job), job, source, validFields())).toBe(true);
    for (const status of ['needs_review', 'completed', 'failed']) expect(previewMatches(request(job), {...job, status}, source, validFields())).toBe(false);
    const wrong = structuredClone(job); readClipToolResult(wrong)!.settings.gain = 7; expect(previewMatches(request(wrong), wrong, source, validFields())).toBe(false);
    expect(previewMatches(request(job), {...job, artifacts: []}, source, validFields())).toBe(false);
    expect(artifactUrl(job, '/fake.png')).toBeUndefined();
  });
  it('publishes needs_review apply as success, opens the new clip after refresh and prevents duplicate save', async () => {
    const h = studioHarness(); await preview(h);
    vi.mocked(s.job).mockResolvedValueOnce({jobId: 'apply-1', status: 'queued'});
    await h.click('새 동작으로 저장'); expect(s.job).toHaveBeenLastCalledWith('apply_follow', [], {previewJobId: 'preview-1'});
    s.jobs.push({jobId: 'apply-1', operation: 'apply_follow', status: 'needs_review', inputRevision: 7, result: {clipId: 'new-clip'}});
    h.render(); expect(h.props.onClip).not.toHaveBeenCalled(); expect(h.button('새 동작으로 저장').props.disabled).toBe(true);
    const next = {...structuredClone(project), revision: 8, clips: [clip, {...clip, clipId: 'new-clip'}]}; s.base = next; s.snapshot = next; h.render();
    expect(h.props.onClip).toHaveBeenCalledExactlyOnceWith('new-clip'); h.render(); expect(h.props.onClip).toHaveBeenCalledOnce();
    expect(text(h.tree)).not.toContain('작업이 완료되지 않았습니다'); expect(text(h.tree)).toContain('새 동작을 저장했습니다');
    await h.click('새 동작으로 저장', true); expect(s.job).toHaveBeenCalledTimes(2); expect(s.edit).not.toHaveBeenCalled();
  });
  it('never opens a completed apply after choosing another clip', async () => {
    const h = studioHarness(); await preview(h); vi.mocked(s.job).mockResolvedValueOnce({jobId: 'apply-1', status: 'queued'}); await h.click('새 동작으로 저장');
    s.base!.clips.push({...clip, clipId: 'other'}, {...clip, clipId: 'new-clip'}); h.render({...h.props, clipId: 'other'});
    s.jobs.push({jobId: 'apply-1', operation: 'apply_follow', status: 'needs_review', inputRevision: 7, result: {clipId: 'new-clip'}}); h.render(); expect(h.props.onClip).not.toHaveBeenCalled();
  });
  it('shows fold limiting and region-overflow worker errors without approval changes', async () => {
    const h = studioHarness(); await preview(h); const result = readClipToolResult(s.jobs[0])!;
    if (result.tool === 'follow') {result.report.foldLimited = true; result.report.gainApplied = 1.2;}
    h.render(); expect(text(h.tree)).toContain('요청 2.5 → 적용 1.2');
    s.jobs[0] = {...s.jobs[0], status: 'failed', errors: [{code: 'CLIP_TOOL_REGION', message: '움직이는 타원이 셀 밖으로 나갑니다. 영역을 줄이거나 위치를 옮겨 주세요.'}]}; h.render();
    const status = nodes(h.tree).find(n => typeof n.type === 'function' && n.type.name === 'ToolJobStatus')!;
    expect(text((status.type as Function)(status.props))).toContain('영역을 줄이거나'); expect(h.button('새 동작으로 저장').props.disabled).toBe(true);
  });
});

describe('diagnostic output and exact frame navigation', () => {
  async function checked() {const h = studioHarness(); h.change('보완·검사 도구', 'handed'); h.change('장비 이름', '시계'); vi.mocked(s.job).mockResolvedValueOnce({jobId: 'check-1'}); await h.submit(); s.jobs = [resultJob('handed')]; h.render(); return h;}
  it('uses report occurrence IDs for suspect navigation and renders Korean unchecked reasons', async () => {
    const h = await checked(); await h.click('슬롯 3 선택'); expect(h.props.onSelectOccurrence).toHaveBeenCalledWith('slot-2');
    expect(text(h.tree)).toContain('장비가 반대쪽'); expect(text(h.tree)).toContain('검사하지 못했습니다'); expect(text(h.tree)).toContain('자동 수정·승인 없음');
    const comparison = nodes(h.tree).find(n => n.type === ClipToolComparison)!; comparison.props.onSelectFrame(1); expect(h.props.onSelectOccurrence).toHaveBeenLastCalledWith('slot-1');
    s.base!.revision++; h.render(); await h.click('슬롯 3 선택', true); expect(h.props.onSelectOccurrence).toHaveBeenCalledTimes(2);
  });
  it('warns when zero markers were found even if an upstream verdict says clear', async () => {
    const h = await checked(), result = readClipToolResult(s.jobs[0])!;
    if (result.tool === 'handed') {result.report.framesShown = 0; result.report.verdict = 'clear'; result.report.suspectFrames = [];}
    h.render(); expect(text(h.tree)).toContain('표식을 충분히 찾지 못해 판단할 수 없습니다'); expect(text(h.tree)).not.toContain('의심 항목이 없습니다'); expect(s.edit).not.toHaveBeenCalled();
  });
  it('crops both PNG strips at the same frame and shows source timing', async () => {
    const job = resultJob(), result = readClipToolResult(job)!;
    const h = new Harness(ClipToolComparison, {job, result, enabled: true, canNavigate: true, onSelectFrame: vi.fn()}); await h.flush();
    nodes(h.tree).find(n => n.type === 'input')!.props.onChange({target: {value: '2'}}); h.render(); await h.flush();
    const calls = h.context.drawImage.mock.calls.slice(-2);
    expect(calls[0].slice(1)).toEqual([128, 0, 64, 64, 0, 0, 64, 64]); expect(calls[1].slice(1)).toEqual([128, 0, 64, 64, 64, 0, 64, 64]);
    expect(text(h.tree)).toContain('원본 시점 200ms · 이 슬롯 100ms · 전체 500ms');
    await h.click('이 프레임을 재생 순서에서 선택'); expect(h.props.onSelectFrame).toHaveBeenCalledWith(2);
    const images = nodes(h.tree).filter(n => n.type === 'img').map(n => n.props.src); expect(images).toEqual([artifactUrl(job, result.preview.before), artifactUrl(job, result.preview.after)]);
  });
  it('maps the board name to its artifact URL and rejects malformed occurrence mappings', () => {
    const job = resultJob('handed'), result = readClipToolResult(job)!;
    const html = renderToStaticMarkup(<ClipToolComparison job={job} result={result} enabled={false} canNavigate onSelectFrame={vi.fn()}/>);
    expect(html).toContain(`href="${artifactUrl(job, result.preview.board)}"`); expect(html).not.toContain('src="handed-board.png"');
    if (result.tool === 'handed') result.report.suspectFrames[0].occurrenceId = 'other-slot'; expect(readClipToolResult(job)).toBeUndefined();
  });
  it('keeps the panel folded in SSR with Korean labels and keyboard number fields', () => {
    const html = renderToStaticMarkup(<ClipTools s={s} clipId="clip" onClip={vi.fn()} onSelectOccurrence={vi.fn()}/>);
    expect(html).toContain('<summary>동작 보완·검사</summary>'); expect(html).not.toMatch(/<details[^>]*\bopen/); expect(html).toContain('type="number"'); expect(html).toContain('모든 프레임에서 움직이는 타원');
  });
});

describe('first-slot region selection and provenance', () => {
  it('draws the saved first occurrence without outline and converts pointer bounds to cell coordinates', async () => {
    const selected = vi.fn(), h = new Harness(RegionSelector, {snapshot: project, clip, fields: defaultFollow(), enabled: true, disabled: false, onRegion: selected}); await h.flush();
    expect(drawOccurrence).toHaveBeenCalledWith(project, clip.occurrences[0], false);
    const svg = nodes(h.tree).find(n => n.type === 'svg')!, target = {getBoundingClientRect: () => ({left: 10, top: 20, width: 128, height: 128}), setPointerCapture: vi.fn(), releasePointerCapture: vi.fn()};
    svg.props.onPointerDown({pointerId: 1, button: 0, clientX: 42, clientY: 52, currentTarget: target, preventDefault: vi.fn()});
    svg.props.onPointerUp({pointerId: 1, clientX: 106, clientY: 116, currentTarget: target});
    expect(selected).toHaveBeenLastCalledWith(['32', '32', '16', '16']); expect(regionFromDrag([50, 60], [-10, 90], 64, 64)).toEqual([25, 62, 25, 2]);
  });
  it('cancels old image draws when the input changes', async () => {
    let finish!: (value: HTMLCanvasElement) => void; vi.mocked(drawOccurrence).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    const h = new Harness(RegionSelector, {snapshot: project, clip, fields: defaultFollow(), enabled: true, disabled: false, onRegion: vi.fn()});
    h.render({...h.props, enabled: false}); finish({} as HTMLCanvasElement); await h.flush(); expect(h.context.drawImage).not.toHaveBeenCalled();
  });
  it('labels derived clip frames without calling them AI-generated originals', () => {
    for (const [kind, label] of [['clip-follow', '동작 부위 흔들림 결과'], ['clip-render', '저장된 동작 렌더 결과']]) {
      const asset = {...project.assets[0], provenance: {kind}}; expect(assetProvenanceLabel(asset, new Map()).label).toBe(label);
    }
    expect(jobSucceeded({operation: 'apply_follow', status: 'needs_review'} as Job)).toBe(true); expect(jobSucceeded({operation: 'preview_follow', status: 'needs_review'} as Job)).toBe(false);
  });
});
