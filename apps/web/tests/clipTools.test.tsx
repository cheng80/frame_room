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
    useLayoutEffect: (setup: () => unknown, deps: unknown[]) => hooks.current ? hooks.current.effect(setup, deps) : actual.useLayoutEffect(setup as any, deps),
    useId: () => hooks.current ? 'clip-test' : actual.useId(),
  };
});
vi.mock('../src/render', async original => ({...await original<typeof import('../src/render')>(), drawOccurrence: vi.fn(), loadImage: vi.fn()}));
import {ClipTools, ClipToolComparison, RegionSelector} from '../src/ClipToolsPanel';
import {drawOccurrence, loadImage} from '../src/render';
import {SpriteImage, SpriteViewport, ZoomControls} from '../src/SpriteViewport';
import {AlignmentStep} from '../src/EditSteps';
import {ExtractStep} from '../src/ExtractStep';
import {assetProvenanceLabel} from '../src/assetProvenance';
import {artifactUrl, defaultFollow, defaultHanded, followParams, handedParams, jobSucceeded, previewMatches, readClipToolResult, regionFromDrag, settingsKey, sourceOf, validateClipSource, type ClipToolResult, type FollowFields, type ToolRequest} from '../src/clipTools';

type Node = ReactElement<any>;
function nodes(tree: any): Node[] {
  if (Array.isArray(tree)) return tree.flatMap(nodes);
  if (!tree || typeof tree !== 'object' || !tree.props) return [];
  return [tree, ...nodes(tree.props.children), ...nodes(tree.props.preview), ...nodes(tree.props.settings), ...nodes(tree.props.footer)];
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
      for (const node of nodes(this.tree)) if (node.props.className === 'sprite-stage checker' && node.props.ref) node.props.ref.current = {clientWidth: 320, clientHeight: 160};
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
  vi.stubGlobal('getComputedStyle', () => ({paddingLeft: '0', paddingRight: '0', paddingTop: '0', paddingBottom: '0'}));
  vi.stubGlobal('ResizeObserver', class {observe() {} disconnect() {}});
  vi.mocked(drawOccurrence).mockReset().mockResolvedValue({width: 64, height: 64} as HTMLCanvasElement);
  vi.mocked(loadImage).mockReset().mockImplementation(async url => ({width: 256, height: 64, src: url}) as HTMLImageElement);
  s = {base: structuredClone(project), snapshot: structuredClone(project), commands: [], conflict: null, busy: false, service: {worker: 'ready'}, jobs: [], resolveId: (id: string) => id, job: vi.fn(async () => ({jobId: 'queued', status: 'queued'})), edit: vi.fn()} as unknown as Studio;
});
afterEach(() => {mounted.splice(0).forEach(h => h.unmount()); vi.restoreAllMocks(); vi.unstubAllGlobals();});

describe('saved clip request validation', () => {
  it('invalidates a preview when stretch floor/read-on changes or correspondence is uncertain', async () => {
    const h = studioHarness(); await preview(h);
    expect(h.button('새 동작으로 저장').props.disabled).toBe(false);
    h.change('최소 픽셀 면적 (선택, 0~0.99)', '0.5');
    expect(h.button('새 동작으로 저장').props.disabled).toBe(true);
    h.change('최소 픽셀 면적 (선택, 0~0.99)', '');
    h.change('영역을 읽은 시트 SHA-256 (선택)', '0'.repeat(64));
    expect(h.button('새 동작으로 저장').props.disabled).toBe(true);
    h.change('영역을 읽은 시트 SHA-256 (선택)', '');
    (s.jobs[0].result as any).report.canApply = false;
    (s.jobs[0].result as any).report.readOn = {relation: 'uncertain', reason: 'sample-unverified'};
    h.render(); expect(h.button('새 동작으로 저장').props.disabled).toBe(true);
    expect(text(h.tree)).toContain('영역 대응이 불확실');
  });
  it('requests source restoration and rejects mixed evidence schemas in the result reader', async () => {
    const h = studioHarness(); h.change('보완·검사 도구', 'restore');
    await h.submit();
    expect(s.job).toHaveBeenCalledWith('preview_restore', [], {clipId: 'clip', clipRevisionId: 'clip-r1'});
    const job = resultJob(), result = job.result as any;
    result.tool = 'restore'; result.report = {verdict: 'unknown', reasons: ['source-unknown'], canApply: false,
      metric_version: 'source-restoration-v5', policy_version: 'key-protected-source-copy-one-step-cap-jump-ghost-guard-v1', schema_version: 4, comparison_schema: 6};
    expect(readClipToolResult(job)?.tool).toBe('restore');
    result.report.schema_version = 1; expect(readClipToolResult(job)).toBeUndefined();
    result.report.schema_version = 4; result.report.comparison_schema = 5; expect(readClipToolResult(job)).toBeUndefined();
    result.tool = 'compare'; result.report = {verdict: 'unknown', reasons: [], canApply: false, metric_version: 'same-sample-defects-v1', schema_version: 1};
    expect(readClipToolResult(job)?.tool).toBe('compare');
  });
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
    expect(text(h.tree)).toContain('장비가 반대쪽'); expect(text(h.tree)).toContain('검사하지 못했습니다'); expect(text(h.tree)).toContain('자동 수정 없음');
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
    const images = nodes(h.tree).filter(n => n.type === SpriteImage).map(n => n.props.src); expect(images).toEqual([artifactUrl(job, result.preview.before), artifactUrl(job, result.preview.after)]);
  });
  it('maps the board name to its artifact URL and rejects malformed occurrence mappings', () => {
    const job = resultJob('handed'), result = readClipToolResult(job)!;
    const html = renderToStaticMarkup(<ClipToolComparison job={job} result={result} enabled={false} canNavigate onSelectFrame={vi.fn()}/>);
    expect(html).toContain(`href="${artifactUrl(job, result.preview.board)}"`); expect(html).not.toContain('src="handed-board.png"');
    if (result.tool === 'handed') result.report.suspectFrames[0].occurrenceId = 'other-slot'; expect(readClipToolResult(job)).toBeUndefined();
  });
  it('keeps the panel folded in SSR with Korean labels and keyboard number fields', () => {
    const html = renderToStaticMarkup(<ClipTools s={s} clipId="clip" onClip={vi.fn()} onSelectOccurrence={vi.fn()}/>);
    expect(html).toContain('<summary>동작 보완·검사'); expect(html).toContain('aria-label="동작 보완·검사 도움말"'); expect(html).not.toMatch(/<details[^>]*\bopen/); expect(html).toContain('type="number"'); expect(html).toContain('모든 프레임에서 움직이는 타원');
  });
});

describe('first-slot region selection and provenance', () => {
  it.each([0.5, 1, 2, 4])('draws the saved first occurrence and maps a %sx scrolled view to cell coordinates', async scale => {
    const selected = vi.fn(), h = new Harness(RegionSelector, {snapshot: project, clip, fields: defaultFollow(), enabled: true, disabled: false, onRegion: selected}); await h.flush();
    expect(drawOccurrence).toHaveBeenCalledWith(project, clip.occurrences[0], false);
    const viewport = nodes(h.tree).find(n => n.type === SpriteViewport)!;
    expect(viewport.props).toMatchObject({width: 64, height: 64});
    expect(viewport.props.children.props.style?.aspectRatio).toBeUndefined();
    const svg = nodes(h.tree).find(n => n.type === 'svg')!, target = {getBoundingClientRect: () => ({left: -30, top: -50, width: 64 * scale, height: 64 * scale}), setPointerCapture: vi.fn(), releasePointerCapture: vi.fn()};
    svg.props.onPointerDown({pointerId: 1, button: 0, clientX: -30 + 16 * scale, clientY: -50 + 16 * scale, currentTarget: target, preventDefault: vi.fn()});
    svg.props.onPointerUp({pointerId: 1, clientX: -30 + 48 * scale, clientY: -50 + 48 * scale, currentTarget: target});
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

// Exercise the real shared zoom controls with source-coordinate consumers.
function viewportHarness(tree: any) {return new Harness(SpriteViewport, nodes(tree).find(n => n.type === SpriteViewport)!.props);}
function zoom(h: Harness, label: string) {
  const controls = nodes(h.tree).find(n => n.type === ZoomControls)!;
  const button = nodes(ZoomControls(controls.props)).find(n => n.type === 'button' && (n.props['aria-label'] === label || text(n) === label))!;
  expect(button.props.type).toBe('button'); expect(button.props.disabled).not.toBe(true); button.props.onClick(); h.render();
  return nodes(h.tree).find(n => n.props.className === 'sprite-frame')!.props.style;
}

describe('source-coordinate zoom integration', () => {
  it('keeps zoom outside the disabled fieldset for unsaved drafts while blocking region edits', async () => {
    s.commands = [{operation: {type: 'updateClip'}}];
    const panel = studioHarness();
    panel.tree.props.onToggle({currentTarget: {open: true}}); panel.render();
    const form = nodes(panel.tree).find(n => n.type === 'form')!;
    const fieldset = nodes(form).find(n => n.type === 'fieldset')!;
    const selector = nodes(form).find(n => n.type === RegionSelector)!;
    expect(fieldset.props.disabled).toBe(true);
    expect(nodes(fieldset).some(n => n.type === RegionSelector)).toBe(false);
    expect(form.props.children.indexOf(selector)).toBeLessThan(form.props.children.indexOf(fieldset));
    expect(selector.props.disabled).toBe(true);
    const onRegion = vi.fn(), region = new Harness(RegionSelector, {...selector.props, onRegion}); await region.flush();
    const view = viewportHarness(region.tree);
    zoom(view, '1:1'); expect(zoom(view, '확대')).toEqual({width: 128, height: 128});
    expect(zoom(view, '축소')).toEqual({width: 64, height: 64}); zoom(view, '맞춤');
    const svg = nodes(region.tree).find(n => n.type === 'svg')!;
    expect(svg.props['aria-disabled']).toBe(true);
    const target = {setPointerCapture: vi.fn()};
    const event = {pointerId: 1, button: 0, currentTarget: target, preventDefault: vi.fn()};
    svg.props.onPointerDown(event); svg.props.onPointerMove(event); svg.props.onPointerUp(event);
    expect(target.setPointerCapture).not.toHaveBeenCalled(); expect(onRegion).not.toHaveBeenCalled();
    expect(s.edit).not.toHaveBeenCalled(); expect(s.job).not.toHaveBeenCalled();
  });
  it('keeps anchor clicks in original pixels through zoom, 1:1, fit and scroll', () => {
    const snapshot = structuredClone(project);
    Object.assign(snapshot.assets[0], {width: 128, height: 64});
    Object.assign(snapshot.alignmentGroups[0], {sharedScale: 1, targetAnchor: {x: 32, y: 60}});
    s.snapshot = snapshot;
    const before = structuredClone(snapshot), h = new Harness(AlignmentStep, {s}), view = viewportHarness(h.tree);
    const source = nodes(h.tree).find(n => n.props.className === 'alignment-source-image')!;
    for (const label of ['1:1', '확대', '확대', '축소', '맞춤']) {
      vi.mocked(s.edit).mockClear();
      const size = zoom(view, label);
      expect(s.edit).not.toHaveBeenCalled(); expect(s.job).not.toHaveBeenCalled();
      const bounds = {left: -85, top: -42, ...size};
      source.props.onPointerDown({currentTarget: {getBoundingClientRect: () => bounds}, clientX: bounds.left + size.width * .25, clientY: bounds.top + size.height * .75});
      expect(s.edit).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({type: 'setAlignment', alignment: expect.objectContaining({sourceAnchor: {x: 32, y: 48}})}));
      expect(nodes(source).find(n => n.type === 'svg')!.props.viewBox).toBe('0 0 128 64');
      expect(snapshot).toEqual(before);
    }
  });
  it('applies anchor edits without approval and calculates group scale from valid body coordinates', async () => {
    const snapshot = structuredClone(project);
    Object.assign(snapshot.alignmentGroups[0], {mode: 'shared-scale-foot-anchor', sharedScale: 1, targetAnchor: {x: 32, y: 60}, cell: {width: 64, height: 64, edge: 2}, bodyMeasurement: {topY: 10, bottomY: 50, targetHeight: 80, approved: false}});
    snapshot.alignments = {frame: {frameVersionId: 'frame', groupRevisionId: 'group-r1', sourceAnchor: {x: 32, y: 48}, anchorSpace: 'crop', method: 'manual', contactMode: 'grounded', authoredOffsetPx: {x: 0, y: 0}, approval: 'approved'}} as any;
    s.snapshot = snapshot;
    const h = new Harness(AlignmentStep, {s});
    const anchorX = nodes(h.tree).find(n => n.type.name === 'Num' && n.props.label === '앵커 X (px)')!;
    anchorX.props.onChange(24); h.render();
    expect(s.edit).toHaveBeenCalledWith(expect.objectContaining({type: 'setAlignment', alignment: expect.objectContaining({sourceAnchor: {x: 24, y: 48}, approval: 'approved'})}));
    expect(nodes(h.tree).some(n => n.type === 'button' && text(n) === '이 후보 앵커 승인')).toBe(false);
    expect(nodes(h.tree).some(n => n.type === 'input' && n.props.type === 'checkbox')).toBe(false);
    await h.click('공통 배율·셀');
    expect(h.button('공통 배율 계산·적용').props.disabled).toBe(false);
    await h.click('공통 배율 계산·적용');
    expect(s.edit).toHaveBeenLastCalledWith({type: 'setAlignmentGroup', alignmentGroupId: 'group', changes: {mode: 'shared-scale-foot-anchor', bodyMeasurement: {topY: 10, bottomY: 50, targetHeight: 80, approved: true}}});

    snapshot.alignmentGroups[0].bodyMeasurement = {topY: 50, bottomY: 10, targetHeight: 0, approved: true};
    s.snapshot = snapshot;
    const invalid = new Harness(AlignmentStep, {s});
    await invalid.click('공통 배율·셀');
    expect(invalid.button('공통 배율 계산·적용').props.disabled).toBe(true);
  });
  it('zooms the ellipse hit area with its frame while keeping the saved cell and drag coordinates', async () => {
    const selected = vi.fn(), before = structuredClone(project);
    const h = new Harness(RegionSelector, {snapshot: project, clip, fields: validFields(), enabled: true, disabled: false, onRegion: selected}); await h.flush();
    const view = viewportHarness(h.tree), svg = nodes(h.tree).find(n => n.type === 'svg')!;
    zoom(view, '1:1'); const size = zoom(view, '확대');
    expect(size).toEqual({width: 128, height: 128}); expect(selected).not.toHaveBeenCalled();
    const target = {getBoundingClientRect: () => ({left: -40, top: -60, ...size}), setPointerCapture: vi.fn(), releasePointerCapture: vi.fn()};
    svg.props.onPointerDown({pointerId: 3, button: 0, clientX: -8, clientY: -28, currentTarget: target, preventDefault: vi.fn()});
    svg.props.onPointerMove({pointerId: 3, clientX: 56, clientY: 36, currentTarget: target});
    svg.props.onPointerUp({pointerId: 3, clientX: 56, clientY: 36, currentTarget: target});
    expect(selected).toHaveBeenLastCalledWith(['32', '32', '16', '16']);
    expect(target.releasePointerCapture).toHaveBeenCalledWith(3);
    expect(nodes(h.tree).find(n => n.type === 'canvas')!.props).toMatchObject({width: 64, height: 64});
    expect(nodes(svg).find(n => n.type === 'ellipse')!.props).toMatchObject({cx: 32, cy: 32, rx: 10, ry: 12});
    expect(project).toEqual(before); expect(s.edit).not.toHaveBeenCalled(); expect(s.job).not.toHaveBeenCalled();
  });
  it('keeps extraction SVG regions and job parameters in original coordinates after zoom', () => {
    const before = structuredClone(s.snapshot), h = new Harness(ExtractStep, {s, initialAssetId: 'asset'});
    h.change('추출 방식', 'regions');
    h.field('왼쪽 X').props.onChange(8); h.render();
    h.field('위쪽 Y').props.onChange(12); h.render();
    h.field('너비').props.onChange(24); h.render();
    h.field('높이').props.onChange(16); h.render();
    h.button('영역 추가').props.onClick(); h.render();
    const view = viewportHarness(h.tree);
    zoom(view, '1:1'); expect(zoom(view, '확대')).toEqual({width: 128, height: 128});
    const svg = nodes(view.tree).find(n => n.type === 'svg')!;
    expect(svg.props.viewBox).toBe('0 0 64 64');
    expect(nodes(svg).find(n => n.type === 'rect')!.props).toMatchObject({x: 8, y: 12, width: 24, height: 16});
    expect(s.edit).not.toHaveBeenCalled(); expect(s.job).not.toHaveBeenCalled(); expect(s.snapshot).toEqual(before);
    h.button('프레임 후보 추출').props.onClick();
    expect(s.job).toHaveBeenCalledExactlyOnceWith('extract', ['asset'], {mode: 'regions', rows: 1, columns: 1, regions: [{x: 8, y: 12, width: 24, height: 16}], minArea: 4});
  });
  it.each(['follow', 'handed'] as const)('makes %s comparison media zoomable without changing frame pixels', async tool => {
    const job = resultJob(tool), result = readClipToolResult(job)!;
    const h = new Harness(ClipToolComparison, {job, result, enabled: true, canNavigate: true, onSelectFrame: vi.fn()}); await h.flush();
    const view = viewportHarness(h.tree), originalDraws = h.context.drawImage.mock.calls.length;
    zoom(view, '1:1'); const size = zoom(view, '확대');
    expect(size).toEqual({width: tool === 'follow' ? 256 : 128, height: 128});
    expect(h.context.drawImage).toHaveBeenCalledTimes(originalDraws); expect(h.props.onSelectFrame).not.toHaveBeenCalled();
    const images = nodes(h.tree).filter(n => n.type === SpriteImage);
    expect(images[0].props).toMatchObject({width: 64, height: 64, src: artifactUrl(job, result.preview.before)});
    if (tool === 'handed') {
      expect(images[1].props).toMatchObject({src: artifactUrl(job, result.preview.board)});
      expect(images[1].props.width).toBeUndefined();
      expect(nodes(h.tree).filter(n => n.type === 'a').every(a => !nodes(a).some(n => n.type === SpriteImage))).toBe(true);
    } else expect(images[1].props).toMatchObject({width: 64, height: 64, src: artifactUrl(job, result.preview.after)});
    expect(s.edit).not.toHaveBeenCalled(); expect(s.job).not.toHaveBeenCalled();
  });
});
