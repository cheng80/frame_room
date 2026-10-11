import {describe,expect,it} from 'vitest';
import {referenceLabel} from '../src/referenceLabel';
import type {Snapshot} from '../src/types';

const project={references:[{referenceRevisionId:'r1',identityAssetId:'a',approval:'pending',fixedTraits:'여성 힐러, 금발'},{referenceRevisionId:'r2',identityAssetId:'b',approval:'approved',fixedTraits:'여성 힐러, 오른쪽 측면'}],assets:[{assetId:'a',originalFilename:'generated.png'},{assetId:'b',originalFilename:'generated.png'}]} as Snapshot;
describe('reference labels',()=>{
 it('distinguishes duplicate filenames with stable numbers including pending versions',()=>{
  expect(referenceLabel(project,'r1')).toBe('기준 1 · 여성 힐러 · generated.png');
  expect(referenceLabel(project,'r2')).toBe('기준 2 · 여성 힐러 · generated.png');
 });
 it('handles missing references and unavailable image metadata',()=>{
  expect(referenceLabel(project,null)).toBe('기준 연결 필요');
  expect(referenceLabel(project,'missing')).toBe('기준 연결 필요');
  expect(referenceLabel({...project,assets:[],references:[{referenceRevisionId:'r',fixedTraits:''} as any]},'r')).toBe('기준 1');
 });
 it('prefers user names and falls back when a name is cleared',()=>{
  const named={...project,references:project.references.map(r=>({...r,name:'  효과 없는 오른쪽 측면  '}))};
  expect(referenceLabel(named,'r2')).toBe('기준 2 · 효과 없는 오른쪽 측면');
  named.references[1].name='  ';
  expect(referenceLabel(named,'r2')).toBe('기준 2 · 여성 힐러 · generated.png');
 });
});
