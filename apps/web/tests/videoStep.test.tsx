import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import type {ReactElement} from 'react';
import type {Job, Snapshot, Video} from '../src/types';
import type {Studio} from '../src/useStudio';

// Component event tests only. No browser, provider request, or media generation.
const hooks = vi.hoisted(() => ({current: null as any}));
vi.mock('react', async original => ({
  ...await original<typeof import('react')>(),
  useState: (initial: unknown) => hooks.current.state(initial),
  useRef: (initial: unknown) => hooks.current.ref(initial),
  useId: () => 'video-test',
  useMemo: (factory: () => unknown) => factory(),
}));
vi.mock('../src/api', async original => ({...await original<typeof import('../src/api')>(), api: vi.fn()}));
import {api, ApiError} from '../src/api';
import {VideoStep} from '../src/VideoStep';
import {JobCard} from '../src/FinishSteps';
import {EditorCanvas} from '../src/Canvas';
import {VideoBatchPlan} from '../src/VideoBatchPlan';
import {VideoBasePreset} from '../src/VideoBasePreset';
import {VideoDiagnostics} from '../src/VideoDiagnostics';
import {defaultVideoProcessing, type VideoGenerationSettings} from '../src/videoWorkflow';

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
class Harness {
  slots: any[] = []; cursor = 0; tree: any;
  constructor(public s: Studio, public onSelectClip = vi.fn(), public customRender?: () => Node) { this.render(); }
  state(initial: unknown) {
    const i = this.cursor++, slot = this.slots[i] ??= {value: typeof initial === 'function' ? initial() : initial};
    return [slot.value, (next: any) => { slot.value = typeof next === 'function' ? next(slot.value) : next; }];
  }
  ref(value: unknown) { return this.slots[this.cursor++] ??= {current: value}; }
  render() { this.cursor = 0; hooks.current = this; this.tree = this.customRender ? this.customRender() : VideoStep({s: this.s, onSelectClip: this.onSelectClip}); hooks.current = null; }
  button(label: string) {
    const node = nodes(this.tree).find(n => n.type === 'button' && text(n) === label);
    if (!node) throw new Error(`No button: ${label}`); return node;
  }
  async click(label: string) { const n = this.button(label); expect(n.props.disabled).not.toBe(true); await n.props.onClick(); this.render(); }
  field(label: string) {
    const node = nodes(this.tree).find(n => n.props.label === label);
    if (!node) throw new Error(`No field: ${label}`); return node;
  }
  change(label: string, value: string) { this.field(label).props.onChange({target: {value}}); this.render(); }
  submit() { return nodes(this.tree).find(n => n.type === 'form')!.props.onSubmit({preventDefault: vi.fn()}); }
  file(file: File) { nodes(this.tree).find(n => n.type === 'input' && n.props.type === 'file')!.props.onChange({target: {files: [file]}}); this.render(); }
}
const video: Video = {videoId: 'video-1', sha256: 'hash', originalFilename: 'walk.mp4', mediaType: 'video/mp4', width: 640, height: 480, fps: 24, frameCount: 73, durationMs: 3042, provenance: {kind: 'imported-video'}, url: '/v1/videos/video-1/content'};
const project = {
  projectId: 'project', revision: 7, assets: [{assetId: 'image-1', originalFilename: 'base.png', url: '/base.png'}],
  activeReferenceRevisionId: 'reference-1', references: [{referenceRevisionId: 'reference-1', identityAssetId: 'image-1', approval: 'approved'}],
  clips: [], frames: [], alignmentGroups: [], alignments: {}, videos: [video],
} as unknown as Snapshot;
let s: Studio;
const mockedApi = vi.mocked(api);
beforeEach(() => {
  mockedApi.mockReset();
  s = {
    snapshot: structuredClone(project), base: structuredClone(project), commands: [], busy: false, conflict: null,
    service: {worker: 'ready'}, jobs: [], providers: [{providerId: 'grok-video', mediaKind: 'video', available: true, loginReady: true}],
    job: vi.fn(async () => ({jobId: 'job-1'})), run: vi.fn(async fn => fn()), load: vi.fn(async () => true),
    setBase: vi.fn(), refreshDetails: vi.fn(async () => undefined), refreshProjects: vi.fn(async () => undefined), setNotice: vi.fn(), setError: vi.fn(), connect: vi.fn(), edit: vi.fn(),
    mutation: vi.fn(async () => ({batchId: 'batch', jobs: []})),
  } as unknown as Studio;
});

describe('video batch controls', () => {
  const submissions = () => mockedApi.mock.calls.filter(([path, method]) => path.endsWith('/video-batches') && method === 'POST');
  function batchHarness() {
    mockedApi.mockImplementation(async (_path, method) => method === 'POST' ? {batchId: 'batch', jobs: []} : structuredClone(s.snapshot));
    let inRun = false;
    vi.mocked(s.run).mockImplementation(async fn => {inRun = true; try {return await fn();} finally {inRun = false;}});
    vi.mocked(s.setBase).mockImplementation(next => {expect(inRun).toBe(true); s.snapshot = next as Snapshot;});
    const generation: VideoGenerationSettings = {assetId: 'image-1', model: 'grok-imagine-video-1.5', durationSeconds: '3', resolution: '480p', direction: 'side', facing: 'right', motionPrompt: '', bodyPlan: '', equipment: ''};
    const processing = defaultVideoProcessing(), onSubmitted = vi.fn();
    const options = {s, generation, processing, available: true, active: false, visible: true, onSubmitted};
    const h = new Harness(s, vi.fn(), () => VideoBatchPlan(options));
    return {h, generation, processing, options, onSubmitted};
  }
  it('keeps one generation separate and reveals the whole job list for a batch', async () => {
    const h = new Harness(s);
    expect(nodes(h.tree).find(n => n.type === VideoBatchPlan)?.props.visible).toBe(true);
    await h.click('기존 영상 처리');
    expect(nodes(h.tree).find(n => n.type === VideoBatchPlan)?.props.visible).toBe(false);
    s.jobs = Array.from({length: 6}, (_, i) => ({jobId: String(i), operation: 'generate_video', status: 'queued'})) as Job[];
    h.render(); await h.click('영상 작업 모두 보기 (6건)');
    expect(nodes(h.tree).filter(n => n.type === JobCard)).toHaveLength(6);
  });
  it('adds coherent settings without any request and submits an explicitly counted batch', async () => {
    const {h, generation, processing, onSubmitted} = batchHarness();
    await h.click('현재 설정을 묶음에 추가');
    generation.direction = 'front_diagonal'; generation.durationSeconds = '2'; processing.finishMode = 'rgba'; h.render();
    await h.click('현재 설정을 묶음에 추가');
    expect(text(h.tree)).toContain('총 5초');
    expect(mockedApi).not.toHaveBeenCalled(); expect(s.job).not.toHaveBeenCalled();
    await h.click('영상 2건 생성');
    expect(submissions()).toHaveLength(1);
    expect(s.mutation).not.toHaveBeenCalled();
    const [path, , body] = submissions()[0];
    expect(path).toBe('/projects/project/video-batches');
    expect(body).toMatchObject({inputRevision: 7, items: [
      {assetId: 'image-1', params: {direction: 'side', durationSeconds: 3, finishMode: 'gif'}},
      {assetId: 'image-1', params: {direction: 'front_diagonal', durationSeconds: 2, finishMode: 'rgba'}},
    ]});
    expect((body as any).idempotencyKey).toEqual(expect.any(String));
    expect(onSubmitted).toHaveBeenCalledOnce();
    expect(s.refreshDetails).toHaveBeenCalledWith('project');
    expect(s.refreshProjects).toHaveBeenCalledOnce();
    expect(nodes(h.tree).filter(n => n.type === 'li')).toHaveLength(0);
  });
  it('caps at 16 entries and allows removing a planned row before submit', async () => {
    const {h} = batchHarness();
    for (let i = 0; i < 16; i++) await h.click('현재 설정을 묶음에 추가');
    expect(h.button('현재 설정을 묶음에 추가').props.disabled).toBe(true);
    h.button('현재 설정을 묶음에 추가').props.onClick(); h.render();
    expect(nodes(h.tree).filter(n => n.type === 'li')).toHaveLength(16);
    nodes(h.tree).find(n => n.props['aria-label'] === '묶음 1번 제거')!.props.onClick(); h.render();
    expect(nodes(h.tree).filter(n => n.type === 'li')).toHaveLength(15);
    expect(h.button('현재 설정을 묶음에 추가').props.disabled).toBe(false);
    expect(mockedApi).not.toHaveBeenCalled();
  });
  it.each([0, 408, 503, 'malformed'])('retains the exact first body and key for uncertain response %s despite later settings/revision changes', async status => {
    const {h, generation, options} = batchHarness();
    if (typeof status === 'number') mockedApi.mockRejectedValueOnce(new ApiError(status, 'UNKNOWN', '접수 여부 불명'));
    else mockedApi.mockResolvedValueOnce({});
    await h.click('현재 설정을 묶음에 추가'); await h.click('영상 1건 생성');
    const first = submissions()[0][2];
    expect(submissions()).toHaveLength(1); // No automatic resubmission.
    expect(text(h.tree)).toContain('접수 결과를 확인하지 못했습니다.');
    s.snapshot = {...s.snapshot!, revision: 99}; generation.direction = 'back'; options.active = true; h.render();
    expect(h.button('현재 설정을 묶음에 추가').props.disabled).toBe(true);
    expect(nodes(h.tree).find(n => n.props['aria-label'] === '묶음 1번 제거')!.props.disabled).toBe(true);
    await h.click('같은 묶음의 접수 결과 다시 확인');
    expect(submissions()[1][2]).toBe(first);
    expect(submissions()[1][2]).toMatchObject({inputRevision: 7, items: [{params: {direction: 'side'}}]});
    expect(nodes(h.tree).filter(n => n.type === 'li')).toHaveLength(0);
  });
  it.each([404, 409, 422])('unlocks a definitively rejected %s plan, refreshes, and allows an edited request with a fresh revision', async status => {
    const {h, generation, onSubmitted} = batchHarness();
    mockedApi.mockRejectedValueOnce(new ApiError(status, status === 409 ? 'REVISION_CONFLICT' : 'INVALID_BATCH', '서버 거절'));
    mockedApi.mockResolvedValueOnce({...project, revision: 12});
    await h.click('현재 설정을 묶음에 추가'); await h.click('영상 1건 생성');
    const first = submissions()[0][2];
    expect(submissions()).toHaveLength(1); expect(onSubmitted).not.toHaveBeenCalled();
    expect(s.snapshot?.revision).toBe(12);
    expect(text(h.tree)).toContain('묶음은 접수되지 않았습니다.');
    expect(h.button('현재 설정을 묶음에 추가').props.disabled).toBe(false);
    const remove = nodes(h.tree).find(n => n.props['aria-label'] === '묶음 1번 제거')!;
    expect(remove.props.disabled).toBe(false); remove.props.onClick(); h.render();
    generation.direction = 'back';
    await h.click('현재 설정을 묶음에 추가'); await h.click('영상 1건 생성');
    expect(submissions()).toHaveLength(2);
    expect(submissions()[1][2]).toMatchObject({inputRevision: 12, items: [{params: {direction: 'back'}}]});
    expect((submissions()[1][2] as any).idempotencyKey).not.toBe((first as any).idempotencyKey);
    expect(onSubmitted).toHaveBeenCalledOnce();
  });
  it('keeps an accepted ACK successful even if its subsequent refresh fails with 404', async () => {
    const {h, onSubmitted} = batchHarness();
    mockedApi.mockResolvedValueOnce({batchId: 'accepted', jobs: []});
    mockedApi.mockRejectedValueOnce(new ApiError(404, 'REFRESH_FAILED', '조회 실패'));
    await h.click('현재 설정을 묶음에 추가'); await h.click('영상 1건 생성');
    expect(submissions()).toHaveLength(1);
    expect(nodes(h.tree).filter(n => n.type === 'li')).toHaveLength(0);
    expect(onSubmitted).toHaveBeenCalledOnce();
    expect(text(h.tree)).toContain('묶음은 접수됐지만 화면을 갱신하지 못했습니다.');
    expect(text(h.tree)).not.toContain('묶음은 접수되지 않았습니다.');
  });
  it('does not submit twice while acknowledgement is pending', async () => {
    const {h} = batchHarness(); let resolve!: (value: unknown) => void;
    mockedApi.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
    await h.click('현재 설정을 묶음에 추가');
    const button = h.button('영상 1건 생성');
    const first = button.props.onClick(); await button.props.onClick();
    expect(submissions()).toHaveLength(1);
    resolve({batchId: 'batch', jobs: []}); await first;
  });
});
afterEach(() => vi.restoreAllMocks());

describe('video source tool events', () => {
  it('prominently defaults to eight and lets twelve or a manual count replace only the next request', async () => {
    const original = structuredClone(s.snapshot), h = new Harness(s);
    expect(text(h.tree)).toContain('한 주기 기본 8장');
    expect(h.field('최대 후보 수').props.value).toBe('8');
    await h.click('12장'); expect(h.field('최대 후보 수').props.value).toBe('12');
    await h.submit(); expect(s.job).toHaveBeenLastCalledWith('generate_video', ['image-1'], expect.objectContaining({maxFrames: 12}));
    h.change('최대 후보 수', '24'); await h.submit();
    expect(s.job).toHaveBeenLastCalledWith('generate_video', ['image-1'], expect.objectContaining({maxFrames: 24}));
    await h.click('8장 · 기본'); expect(h.field('최대 후보 수').props.value).toBe('8');
    expect(s.snapshot).toEqual(original); expect(s.edit).not.toHaveBeenCalled();
  });
  it('sends structured subject and independent phase controls without generating on change', async () => {
    const h = new Harness(s);
    h.change('신체 구조', 'quadruped'); h.change('장비와 손', 'sword:right; shield:left');
    h.change('주기 보간', 'off'); h.change('시작 발', 'left');
    expect(s.job).not.toHaveBeenCalled();
    await h.submit();
    expect(s.job).toHaveBeenLastCalledWith('generate_video', ['image-1'], expect.objectContaining({bodyPlan: 'quadruped', equipment: 'sword:right; shield:left', between: 'off', startFoot: 'left', repairMode: 'off'}));
    await h.click('기존 영상 처리'); h.change('수동 시작 위치 · 선택', '3');
    expect(h.field('시작 발').props.disabled).toBe(true);
    await h.submit();
    const params = vi.mocked(s.job).mock.calls[1][2];
    expect(params).toMatchObject({between: 'off', startFoot: 'left', startIndex: 3});
    expect(params).not.toHaveProperty('bodyPlan'); expect(params).not.toHaveProperty('equipment');
    await h.click('새 영상 생성'); await h.submit();
    expect(vi.mocked(s.job).mock.calls[2][2]).not.toHaveProperty('startIndex');
  });
  it('allows matching without RIFE when interpolation is explicitly off', async () => {
    s.providers[0].capabilities = {rife: {available: false}};
    s.snapshot!.clips = [{clipId: 'target', name: '걷기', loop: true, occurrences: Array.from({length: 8}, () => ({durationMs: 125}))}] as any;
    const h = new Harness(s); h.change('주기 보간', 'off'); h.change('주기를 맞출 동작', 'target');
    await h.submit();
    expect(s.job).toHaveBeenCalledWith('generate_video', ['image-1'], expect.objectContaining({between: 'off', matchClipId: 'target'}));
  });
  it('uses saved VFR timing in range marking and labels average-FPS fallback honestly', async () => {
    const h = new Harness(s); await h.click('기존 영상 처리');
    expect(text(h.tree)).toContain('평균 fps로 환산한 예상값');
    s.snapshot!.videos = [{...video, frameCount: 3, durationMs: 400}];
    s.jobs = [{operation: 'process_video', result: {videoId: 'video-1', processing: {source: {timesMs: [0, 100, 125, 400]}}}}] as Job[];
    h.render();
    expect(text(h.tree)).toContain('저장된 원본 프레임 시각');
    nodes(h.tree).find(n => n.type === 'video')!.props.ref.current = {currentTime: .12};
    await h.click('현재 위치를 시작으로'); expect(h.field('시작 프레임 · 포함').props.value).toBe('1');
    expect(s.job).not.toHaveBeenCalled();
  });
  it('shows cost-sensitive choices before one generation and supplies its approved base image', async () => {
    const h = new Harness(s);
    expect(text(h.tree)).toContain('Grok Pro · 3초 · 480p · 생성 1회');
    expect(h.field('기준 이미지').props.value).toBe('image-1');
    await h.submit();
    expect(s.job).toHaveBeenCalledOnce();
    expect(s.job).toHaveBeenCalledWith('generate_video', ['image-1'], expect.objectContaining({referenceRevisionId: 'reference-1', durationSeconds: 3, resolution: '480p', maxFrames: 8, bodyHeight: 94, cellWidth: 64, cellHeight: 128, finishMode: 'gif'}));
  });
  it('defaults to GIF-equivalent PNG colors and sends RGBA only when selected', async () => {
    const h = new Harness(s);
    expect(h.field('색상 마무리').props.value).toBe('gif');
    expect(text(h.tree)).toContain('실제 PNG 후보에 저장');
    h.change('색상 마무리', 'rgba');
    await h.click('기존 영상 처리');
    await h.submit();
    expect(s.job).toHaveBeenCalledWith('process_video', [], expect.objectContaining({finishMode: 'rgba'}));
  });
  it('shows Lite guidance without silently changing the requested resolution', () => {
    const h = new Harness(s);
    h.change('해상도', '720p'); h.change('영상 모델', 'grok-imagine-video-1.5-lite');
    expect(text(h.tree)).toContain('480p로 먼저 확인');
    expect(h.field('해상도').props.value).toBe('720p');
  });
  it('uses actual RIFE capability, keeps repair off by default, and does not promise an unavailable repair', async () => {
    s.providers[0].capabilities = {rife: {available: false, reason: '로컬 RIFE 없음'}};
    const h = new Harness(s);
    expect(h.field('동작 흔들림 보정').props.value).toBe('off');
    expect(text(h.tree)).toContain('로컬 RIFE 없음');
    expect(nodes(h.field('동작 흔들림 보정')).find(n => n.type === 'option' && n.props.value === 'on')!.props.disabled).toBe(true);
    h.change('동작 흔들림 보정', 'on'); await h.submit(); h.render();
    expect(s.job).not.toHaveBeenCalled();
    s.providers[0].capabilities = {rife: {available: true}}; h.render();
    expect(nodes(h.field('동작 흔들림 보정')).find(n => n.type === 'option' && n.props.value === 'on')!.props.disabled).toBe(false);
    await h.submit();
    expect(s.job).toHaveBeenCalledWith('generate_video', ['image-1'], expect.objectContaining({repairMode: 'on'}));
  });
  it('offers eligible match targets, sends the common setting, and clears it for a full-video range', async () => {
    s.providers[0].capabilities = {rife: {available: true}};
    s.snapshot!.clips = [
      {clipId: 'target', name: '기존 보행', loop: true, occurrences: Array.from({length: 4}, () => ({durationMs: 100}))},
      {clipId: 'once', name: '단발 공격', loop: false, occurrences: Array.from({length: 4}, () => ({durationMs: 100}))},
    ] as any;
    const h = new Harness(s);
    expect(text(h.field('주기를 맞출 동작'))).toContain('기존 보행');
    expect(text(h.field('주기를 맞출 동작'))).not.toContain('단발 공격');
    h.change('주기를 맞출 동작', 'target'); await h.submit();
    expect(s.job).toHaveBeenLastCalledWith('generate_video', ['image-1'], expect.objectContaining({matchClipId: 'target'}));
    await h.click('기존 영상 처리'); h.change('추출 구간', 'full');
    expect(h.field('주기를 맞출 동작').props.value).toBe('');
    expect(h.field('주기를 맞출 동작').props.disabled).toBe(true);
    await h.submit();
    expect(vi.mocked(s.job).mock.calls[1][2]).not.toHaveProperty('matchClipId');
  });
  it('marks a manual range from the original player and never generates during selection', async () => {
    const h = new Harness(s); await h.click('기존 영상 처리');
    const player = nodes(h.tree).find(n => n.type === 'video')!;
    player.props.ref.current = {currentTime: 1};
    await h.click('현재 위치를 시작으로');
    expect(h.field('추출 구간').props.value).toBe('manual');
    expect(h.field('시작 프레임 · 포함').props.value).toBe('24');
    player.props.ref.current.currentTime = 2;
    await h.click('현재 위치 다음까지');
    expect(h.field('끝 프레임 · 미포함').props.value).toBe('49');
    expect(s.job).not.toHaveBeenCalled();
  });
  it('renders actual clip PNGs, compares normalization parents read-only, and separates new request settings', async () => {
    s.snapshot = {...project,
      assets: [{assetId: 'finished', width: 40, height: 94, provenance: {processing: 'video-finish', finish: {mode: 'gif'}, parentAssetId: 'normalized'}}, {assetId: 'normalized', width: 40, height: 94}] as any,
      frames: [{frameVersionId: 'frame', imageAssetId: 'finished'}] as any,
      clips: [{clipId: 'clip', sourceVideoId: 'video-1', name: '완성 걷기', loop: true, occurrences: [{occurrenceId: 'slot', frameVersionId: 'frame', durationMs: 42}]}] as any,
    };
    s.jobs = [{operation: 'process_video', status: 'needs_review', result: {clipId: 'clip', videoId: 'video-1', processing: {preview: {gif: '/interim.gif'}}}} as Job];
    const original = structuredClone(s.snapshot), h = new Harness(s);
    const canvas = () => nodes(h.tree).find(n => n.type === EditorCanvas)!;
    expect(canvas().props.snapshot).toBe(s.snapshot);
    expect(canvas().props.clip).toBe(s.snapshot.clips[0]);
    expect(nodes(h.tree).some(n => n.props.src === '/interim.gif')).toBe(false);
    expect(nodes(h.tree).some(n => n.type === 'video' && n.props.src === video.url)).toBe(true);
    h.change('색상 마무리', 'rgba');
    expect(text(h.tree)).toContain('최대 255색 · 투명/불투명 PNG');
    await h.click('마무리 전 · 비교용');
    expect(canvas().props.snapshot.frames[0].imageAssetId).toBe('normalized');
    expect(canvas().props.clip).toBe(s.snapshot.clips[0]);
    await h.click('마무리 후 · 편집 결과');
    expect(canvas().props.snapshot).toBe(s.snapshot);
    expect(s.snapshot).toEqual(original); expect(s.edit).not.toHaveBeenCalled(); expect(s.job).not.toHaveBeenCalled();
    h.change('결과 동작의 재생 종료', 'once');
    expect(s.edit).toHaveBeenCalledWith({type: 'updateClip', clipId: 'clip', changes: {loop: false, endBehavior: 'hold-last'}});
  });
  it('suppresses duplicate submits while the first job acknowledgement is pending', async () => {
    let finish!: (v: any) => void;
    vi.mocked(s.job).mockImplementation(() => new Promise(resolve => {finish = resolve;}));
    const h = new Harness(s), pending = h.submit();
    await h.submit(); expect(s.job).toHaveBeenCalledOnce();
    finish({jobId: 'one'}); await pending;
  });
  it('supports existing-video processing without a logged-in provider and does not send a generation operation', async () => {
    s.providers = [];
    const h = new Harness(s);
    expect(h.button('영상 1회 생성하고 후보 추출').props.disabled).toBe(true);
    await h.click('기존 영상 처리');
    h.change('추출 구간', 'manual'); h.change('시작 프레임 · 포함', '8'); h.change('끝 프레임 · 미포함', '36');
    await h.submit();
    expect(s.job).toHaveBeenCalledOnce();
    expect(s.job).toHaveBeenCalledWith('process_video', [], expect.objectContaining({videoId: 'video-1', loopMode: 'manual', startFrame: 8, endFrame: 36}));
    const player = nodes(h.tree).find(n => n.type === 'video')!;
    expect(player.props).toMatchObject({src: video.url, controls: true, preload: 'metadata'});
    expect(player.props.autoPlay).toBeUndefined();
    expect(nodes(h.tree).some(n => n.type === 'a' && n.props.href === video.url && n.props.download === 'walk.mp4')).toBe(true);
  });
  it('rejects a reversed manual range before enqueue, and clears manual mode when returning to generation', async () => {
    const h = new Harness(s); await h.click('기존 영상 처리');
    h.change('추출 구간', 'manual'); h.change('시작 프레임 · 포함', '40'); h.change('끝 프레임 · 미포함', '20');
    await h.submit(); h.render(); expect(s.job).not.toHaveBeenCalled(); expect(text(h.tree)).toContain('끝 프레임은 시작 프레임보다 커야');
    await h.click('새 영상 생성'); expect(h.field('추출 구간').props.value).toBe('auto');
  });
  it.each([false, true])('keeps spill reference optional without auto-selecting an image (video reference: %s)', async hasReference => {
    if (hasReference) s.snapshot = {...s.snapshot!, videos: [{...video, provenance: {kind: 'real-provider-video', referenceAssetId: 'image-1'}}]};
    const h = new Harness(s); await h.click('기존 영상 처리');
    const field = h.field('색 번짐 판정 기준');
    expect(field.props.value).toBe('');
    expect(text(field)).toContain(hasReference ? '영상 생성 기준 사용' : '기준 없음 · 약한 보정');
    expect(text(h.tree).includes('칼·손 안쪽에 배경색이 남을 수 있습니다.')).toBe(!hasReference);
    if (!hasReference) expect(text(h.tree)).toContain('영상 제작에 쓴 원본 그림을 선택해 주세요.');
    await h.submit();
    expect(vi.mocked(s.job).mock.calls[0][2]).not.toHaveProperty('spillReferenceAssetId');
  });
  it('sends the explicit spill reference for existing video and clears it when returning to the default option', async () => {
    const h = new Harness(s); await h.click('기존 영상 처리');
    h.change('색 번짐 판정 기준', 'image-1');
    expect(text(h.tree)).not.toContain('칼·손 안쪽에 배경색이 남을 수 있습니다.');
    await h.submit();
    expect(s.job).toHaveBeenLastCalledWith('process_video', [], expect.objectContaining({videoId: 'video-1', spillReferenceAssetId: 'image-1'}));
    h.change('색 번짐 판정 기준', '');
    await h.submit();
    expect(vi.mocked(s.job).mock.calls[1][2]).not.toHaveProperty('spillReferenceAssetId');
  });
  it('uses the generation image after a mode change without leaking the processing spill reference', async () => {
    s.snapshot!.assets.push({...s.snapshot!.assets[0], assetId: 'image-2', originalFilename: 'original.png'});
    const h = new Harness(s); await h.click('기존 영상 처리');
    h.change('색 번짐 판정 기준', 'image-2');
    await h.click('새 영상 생성');
    expect(nodes(h.tree).some(n => n.props.label === '색 번짐 판정 기준')).toBe(false);
    await h.submit();
    expect(s.job).toHaveBeenLastCalledWith('generate_video', ['image-1'], expect.objectContaining({referenceRevisionId: 'reference-1'}));
    expect(vi.mocked(s.job).mock.calls[0][2]).not.toHaveProperty('spillReferenceAssetId');
    await h.click('기존 영상 처리');
    expect(h.field('색 번짐 판정 기준').props.value).toBe('image-2');
    await h.submit();
    expect(s.job).toHaveBeenLastCalledWith('process_video', [], expect.objectContaining({spillReferenceAssetId: 'image-2'}));
  });
  it('resets the previous video spill reference and manual range when a different video is selected', async () => {
    s.snapshot!.videos!.unshift({...video, videoId: 'video-2', originalFilename: 'other.mp4', provenance: {referenceAssetId: 'image-1'}});
    const h = new Harness(s); await h.click('기존 영상 처리');
    h.change('색 번짐 판정 기준', 'image-1');
    h.change('추출 구간', 'manual'); h.change('시작 프레임 · 포함', '8'); h.change('끝 프레임 · 미포함', '36');
    h.change('처리할 원본 영상', 'video-2');
    expect(h.field('색 번짐 판정 기준').props.value).toBe('');
    expect(text(h.field('색 번짐 판정 기준'))).toContain('영상 생성 기준 사용');
    expect(h.field('시작 프레임 · 포함').props.value).toBe('0');
    await h.submit();
    expect(s.job).toHaveBeenLastCalledWith('process_video', [], expect.objectContaining({videoId: 'video-2', startFrame: 0, endFrame: 73}));
    expect(vi.mocked(s.job).mock.calls[0][2]).not.toHaveProperty('spillReferenceAssetId');
    h.change('처리할 원본 영상', 'video-1');
    expect(h.field('색 번짐 판정 기준').props.value).toBe('');
  });
  it('rejects a selected reference removed from the latest snapshot before enqueue', async () => {
    const h = new Harness(s); await h.click('기존 영상 처리'); h.change('색 번짐 판정 기준', 'image-1');
    s.snapshot = {...s.snapshot!, assets: []}; h.render();
    expect(text(h.field('색 번짐 판정 기준'))).toContain('기준 이미지 없음 · 다시 선택');
    await h.submit(); h.render();
    expect(s.job).not.toHaveBeenCalled();
    expect(text(nodes(h.tree).find(n => n.props.role === 'alert'))).toContain('색 번짐 판정 기준 이미지가 현재 프로젝트에 없습니다.');
  });
  it('does not reuse the previous reference when a snapshot refresh changes the displayed fallback video', async () => {
    const h = new Harness(s); await h.click('기존 영상 처리'); h.change('색 번짐 판정 기준', 'image-1');
    s.snapshot = {...s.snapshot!, videos: [video, {...video, videoId: 'video-2', originalFilename: 'new.mp4'}]};
    h.render();
    expect(h.field('처리할 원본 영상').props.value).toBe('video-2');
    expect(h.field('색 번짐 판정 기준').props.value).toBe('');
    await h.submit();
    expect(s.job).toHaveBeenLastCalledWith('process_video', [], expect.objectContaining({videoId: 'video-2'}));
    expect(vi.mocked(s.job).mock.calls[0][2]).not.toHaveProperty('spillReferenceAssetId');
  });
  it.each(['draft', 'conflict', 'worker', 'active'])('blocks job requests while %s is unresolved', async reason => {
    if (reason === 'draft') s.commands = [{operation: {type: 'noop'}}];
    if (reason === 'conflict') s.conflict = project;
    if (reason === 'worker') s.service = null;
    if (reason === 'active') s.jobs = [{operation: 'generate_video', status: 'running'} as Job];
    const h = new Harness(s); expect(h.button('영상 1회 생성하고 후보 추출').props.disabled).toBe(true);
    await h.submit(); expect(s.job).not.toHaveBeenCalled();
  });
  it('uploads multipart MP4 with the current revision and applies the acknowledged snapshot inside run', async () => {
    const saved = {...project, revision: 8, videos: [video]};
    mockedApi.mockResolvedValue({snapshot: saved, video});
    let inRun = false;
    vi.mocked(s.run).mockImplementation(async fn => {inRun = true; try {return await fn();} finally {inRun = false;}});
    vi.mocked(s.setBase).mockImplementation(next => {expect(inRun).toBe(true); s.snapshot = next as Snapshot;});
    const h = new Harness(s), file = new File(['sample fixture bytes'], 'walk.mp4', {type: 'video/mp4'});
    h.file(file); await h.click('원본 영상 등록');
    expect(mockedApi).toHaveBeenCalledOnce();
    const [path, method, body] = mockedApi.mock.calls[0];
    expect(path).toBe('/projects/project/videos'); expect(method).toBe('POST');
    expect((body as FormData).get('file')).toBe(file); expect((body as FormData).get('expectedRevision')).toBe('7');
    expect(s.setBase).toHaveBeenCalledWith(saved); expect(s.refreshDetails).toHaveBeenCalledWith('project');
    expect(s.load).not.toHaveBeenCalled(); expect(s.job).not.toHaveBeenCalled();
    expect(h.field('처리할 원본 영상').props.value).toBe('video-1');
  });
  it('rejects a non-MP4 file locally without uploading or generating', async () => {
    const h = new Harness(s); h.file(new File(['fixture'], 'wrong.png', {type: 'image/png'}));
    await h.click('원본 영상 등록'); expect(mockedApi).not.toHaveBeenCalled(); expect(s.job).not.toHaveBeenCalled();
    expect(text(h.tree)).toContain('MP4 영상만');
  });
  it('lets users select a resulting clip through the parent callback without editing original data', async () => {
    s.snapshot = {...project, clips: [{clipId: 'clip', sourceVideoId: 'video-1', name: '영상 걷기', occurrences: [{durationMs: 100}]} as any]};
    const h = new Harness(s); await h.click('이 동작 편집하기'); expect(h.onSelectClip).toHaveBeenCalledWith('clip');
    expect(s.job).not.toHaveBeenCalled();
  });
  it('keeps the newest running job visible when older video jobs exceed the four-card limit', () => {
    // The jobs endpoint supplies newest-first order, including image jobs.
    s.jobs = [
      {jobId: 'latest', operation: 'process_video', status: 'running'},
      {jobId: 'image', operation: 'generate', status: 'succeeded'},
      ...[4, 3, 2, 1, 0].map(n => ({jobId: `older-${n}`, operation: 'process_video', status: 'needs_review'})),
    ] as Job[];
    const h = new Harness(s);
    expect(nodes(h.tree).filter(n => n.type === JobCard).map(n => n.props.job.jobId))
      .toEqual(['latest', 'older-4', 'older-3', 'older-2']);
    expect(h.button('영상 1회 생성하고 후보 추출').props.disabled).toBe(true);
  });
  it('opens old projects with no video array and shows a disabled process action', async () => {
    s.snapshot = {...project, videos: undefined}; const h = new Harness(s); await h.click('기존 영상 처리');
    expect(h.button('이 영상에서 새 후보 추출').props.disabled).toBe(true);
  });
});

describe('video job recovery actions', () => {
  it('renders diagnostics from the stored job record without adding a regeneration button', () => {
    const processing = {selection: {retake: {suggested: true, reasons: ['held-drawings']}}};
    const tree = JobCard({s, job: {operation: 'process_video', status: 'needs_review', result: {processing}} as Job});
    expect(nodes(tree).find(node => node.type === VideoDiagnostics)?.props.processing).toBe(processing);
    expect(nodes(tree).filter(node => node.type === 'button')).toHaveLength(0);
  });
  it('never presents a retry button for an unknown or unmarked generation receipt', () => {
    for (const job of [{status: 'provider_outcome_unknown', resumable: true}, {status: 'failed'}, {status: 'interrupted', resumable: false}]) {
      const tree = JobCard({s, job: {operation: 'generate_video', ...job} as Job});
      expect(nodes(tree).filter(n => n.type === 'button')).toHaveLength(0);
    }
  });
  it('resumes only the existing job endpoint with a checkpoint and Korean labels', async () => {
    const job = {jobId: 'old', operation: 'generate_video', status: 'failed', step: 'poll', resumable: true} as Job;
    const tree = JobCard({s, job}), button = nodes(tree).find(n => n.type === 'button')!;
    expect(text(tree)).toContain('접수한 영상 생성 결과 조회'); expect(text(button)).toBe('접수한 요청 조회 재개');
    await button.props.onClick();
    expect(mockedApi).toHaveBeenCalledWith('/jobs/old/retry', 'POST', expect.objectContaining({reuseCheckpoint: true, failedStep: 'poll'}));
    expect(s.job).not.toHaveBeenCalled();
  });
});

describe('video base subject guidance', () => {
  it('does not impose biped body parts on quadruped or legless base prompts', async () => {
    const onApply = vi.fn(), h = new Harness(s, vi.fn(), () => VideoBasePreset({onApply}));
    h.change('기준 그림의 신체 구조', 'quadruped');
    h.change('기준 그림의 장비와 손', 'sword:right; shield:left');
    await h.click('기준 그림 설명 추가');
    expect(onApply.mock.calls[0][0]).toContain('신체 구조: quadruped');
    expect(onApply.mock.calls[0][0]).toContain('sword:right; shield:left');
    expect(onApply.mock.calls[0][0]).not.toContain('한 발은 자기 골반');
    expect(onApply.mock.calls[0][0]).not.toContain('양발 끝');
    h.change('기준 그림의 신체 구조', 'legless'); h.change('기준 그림의 장비와 손', '');
    await h.click('기준 그림 설명 추가');
    expect(onApply.mock.calls[1][0]).not.toContain('두 발');
    expect(s.job).not.toHaveBeenCalled();
  });
});
