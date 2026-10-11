import {Children, isValidElement, type ReactElement, type ReactNode} from 'react';
import {describe, expect, it, vi} from 'vitest';
import type {Asset} from '../src/types';
import type {Studio} from '../src/useStudio';

vi.mock('react', async original => ({
  ...await original<typeof import('react')>(),
  useState: (value: unknown) => [value, vi.fn()],
}));
import {AssetsStep} from '../src/SourceSteps';

const asset = (assetId: string, kind: string, originalFilename: string): Asset => ({
  assetId,
  projectId: 'project',
  originalFilename,
  url: `/assets/${assetId}.png`,
  width: 64,
  height: 64,
  role: 'source',
  provenance: {kind},
  alphaStats: {transparent: 0, partial: 0, opaque: 4096},
} as Asset);

const elements = (node: ReactNode): ReactElement<any>[] => Children.toArray(node).filter(isValidElement) as ReactElement<any>[];
const text = (node: ReactNode): string => Array.isArray(node) ? node.map(text).join('') : isValidElement(node) ? text(node.props.children) : node == null || typeof node === 'boolean' ? '' : String(node);
const descendants = (node: ReactNode): ReactElement<any>[] => isValidElement(node) ? [node, ...descendants(node.props.children)] : Array.isArray(node) ? node.flatMap(descendants) : [];

function render(assets: Asset[]) {
  const snapshot = {assets, videos: []};
  const mutation = vi.fn(), job = vi.fn(), edit = vi.fn();
  const s = {snapshot, commands: [], mutation, job, edit} as unknown as Studio;
  const tree = AssetsStep({s, onNext: vi.fn(), onGenerate: vi.fn()});
  return {tree, snapshot, mutation, job, edit};
}

function library(tree: ReactElement<any>) {
  const pane = tree.props.preview as ReactElement<any>;
  const content = elements(pane.props.children);
  const grids = content.filter(node => node.type === 'div' && String(node.props.className).includes('source-tool-asset-grid'));
  const details = content.find(node => node.type === 'details');
  return {pane, content, grids, details};
}

describe('asset library', () => {
  it('keeps imported, generated, unknown, and other derived assets in the primary grid regardless of filename', () => {
    const assets = [
      asset('imported', 'imported', '영상원본처럼보이는.png'),
      asset('generated', 'real-provider', 'generated.png'),
      asset('unknown', 'mystery', 'unknownfilenamegenerated.png'),
      asset('derived', 'cutout', 'video-frame.png'),
      asset('other-derived', 'raw-crop', 'extracted.png'),
    ];
    const {tree, snapshot, mutation, job, edit} = render(assets);
    const {pane, content, grids, details} = library(tree);
    const primaryGrid = grids.find(node => node.props.className.includes('source-tool-primary-assets'))!;
    const cards = elements(primaryGrid.props.children);

    expect(pane.props.title).toBe('등록된 자료 5개');
    expect(text(content.find(node => node.type === 'h3')?.props.children)).toBe('자료 이미지 5개');
    expect(cards.map(card => descendants(card).find(node => node.type === 'img')?.props.src)).toEqual(assets.map(item => `/assets/${item.assetId}.png`));
    expect(details).toBeUndefined();
    expect(snapshot.assets).toBe(assets);
    expect({mutation: mutation.mock.calls, job: job.mock.calls, edit: edit.mock.calls}).toEqual({mutation: [], job: [], edit: []});
  });

  it('puts only the three video-processing provenance kinds in a closed details section', () => {
    const assets = [
      asset('imported', 'imported', 'video-input.png'),
      asset('generated', 'real-provider', 'video-frame-raw.png'),
      ...Array.from({length: 65}, (_, index) => asset(`video-${index}`, ['video-input', 'video-frame-raw', 'video-frame'][index % 3], `misleading-${index}.png`)),
      asset('unknown', 'unknown', 'generated.png'),
      asset('derived', 'cutout', 'video-result.png'),
    ];
    const {tree, snapshot, mutation, job, edit} = render(assets);
    const {pane, content, grids, details} = library(tree);
    const primaryGrid = grids.find(node => node.props.className.includes('source-tool-primary-assets'))!;
    const mainCards = elements(primaryGrid.props.children);
    const detailChildren = elements(details!.props.children);
    const summary = detailChildren.find(node => node.type === 'summary');
    const resultGrid = detailChildren.find(node => node.type === 'div' && node.props.className === 'source-tool-asset-grid')!;
    const videoCards = elements(resultGrid.props.children);

    expect(pane.props.title).toBe('등록된 자료 69개');
    expect(text(content.find(node => node.type === 'h3')?.props.children)).toBe('자료 이미지 4개');
    expect(mainCards.map(card => descendants(card).find(node => node.type === 'img')?.props.src)).toEqual(['imported', 'generated', 'unknown', 'derived'].map(id => `/assets/${id}.png`));
    expect(details?.props.className).toBe('source-tool-details source-tool-video-results');
    expect(details?.props.open).toBeUndefined();
    expect(text(summary?.props.children)).toBe('영상 처리 결과 65개');
    expect(videoCards).toHaveLength(65);
    expect(videoCards.every(card => card.props.className === 'source-tool-asset')).toBe(true);
    expect([...mainCards, ...videoCards]).toHaveLength(assets.length);
    expect(new Set([...mainCards, ...videoCards].map(card => descendants(card).find(node => node.type === 'img')?.props.src)).size).toBe(assets.length);
    expect(snapshot.assets).toBe(assets);
    expect({mutation: mutation.mock.calls, job: job.mock.calls, edit: edit.mock.calls}).toEqual({mutation: [], job: [], edit: []});
  });

  it('shows the existing empty state when there are no assets', () => {
    const {tree} = render([]);
    const {pane, content, details} = library(tree);

    expect(pane.props.title).toBe('등록된 자료 0개');
    expect(content.some(node => node.type === 'h3')).toBe(false);
    expect(details).toBeUndefined();
    expect(content.some(node => node.props.title === '등록한 이미지가 없습니다')).toBe(true);
  });

  it('explains that no directly imported or generated images exist when only video results remain', () => {
    const {tree} = render([asset('video', 'video-frame', 'original.png')]);
    const {content, grids, details} = library(tree);
    const primaryGrid = grids.find(node => node.props.className.includes('source-tool-primary-assets'))!;
    const detailChildren = elements(details!.props.children);

    expect(elements(primaryGrid.props.children)).toHaveLength(0);
    expect(content.find(node => node.type === 'p' && String(node.props.children).startsWith('직접 가져오거나'))?.props.children).toBe('직접 가져오거나 생성한 자료 이미지가 없습니다. 영상 처리 결과를 펼쳐 보세요.');
    expect(details?.props.open).toBeUndefined();
    expect(detailChildren.some(node => node.type === 'div' && node.props.className === 'source-tool-asset-grid')).toBe(true);
  });
});
