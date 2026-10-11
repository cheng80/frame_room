import {useState} from 'react';
import type {Studio} from './useStudio';
import {referenceLabel} from './referenceLabel';
import {ReferenceNameInput} from './ReferenceNameInput';
import {assetLabel} from './assetProvenance';
import {Field,Input,Select,Check,Empty} from './ui';
import {SourceTool,SourcePane} from './SourceToolLayout';

export function ReferenceStep({ s }: {
    s: Studio;
}) {
    const p = s.snapshot!;
    const active = p.references.find(r => r.referenceRevisionId === p.activeReferenceRevisionId);
    const [name,setName] = useState(active?.name || '');
    const [identity, setIdentity] = useState(active?.identityAssetId || p.assets[0]?.assetId || '');
    const [styles, setStyles] = useState<string[]>(active?.styleAssetIds || []);
    const [poses, setPoses] = useState<string[]>(active?.poseAssetIds || []);
    const [fixed, setFixed] = useState(active?.fixedTraits || '');
    const [allowed, setAllowed] = useState(active?.allowedChanges || '');
    const [forbidden, setForbidden] = useState(active?.forbiddenTransfers || '');
    const [facing, setFacing] = useState(active?.facing || 'right');
    const [confirmed, setConfirmed] = useState(false);
    const toggle = (ids: string[], id: string) => ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id];
    async function saveReference() {
        const reference = {
            name: name.trim(),
            identityAssetId: identity,
            styleAssetIds: styles,
            poseAssetIds: poses,
            fixedTraits: fixed,
            allowedChanges: allowed,
            forbiddenTransfers: forbidden,
            facing,
            bodyMeasurement: null,
        };
        await s.mutation(`/projects/${p.projectId}/reference-revisions`, {
            expectedRevision: p.revision,
            reference,
        });
        setConfirmed(false);
    }
    const [tab, setTab] = useState<'identity' | 'roles' | 'approval'>('identity');
    const identityAsset = p.assets.find(a => a.assetId === identity);
    return (<SourceTool name="캐릭터 기준" preview={<SourcePane title="외형 기준 이미지" className="source-tool-visual-pane" footer={<span>{identityAsset ? `${assetLabel(identityAsset)} · ${identityAsset.width} × ${identityAsset.height}` : '외형 기준을 선택해 주세요'}</span>}>
    <div className="source-tool-canvas checker">{identityAsset ? <img src={identityAsset.url} alt="선택한 외형 기준"/> : <Empty title="외형 기준 이미지가 없습니다"/>}</div>
  </SourcePane>} settings={<SourcePane title="기준 편집" footer={tab !== 'approval' ? <button className="primary full" disabled={!identity || s.busy || !!s.commands.length} onClick={saveReference}>새 기준 초안 저장</button> : <p className="caption">이름은 Enter 또는 다른 곳을 눌러 초안에 적용하고 상단 저장으로 확정합니다. 이름만 바꾸면 승인은 유지됩니다. 외형 변경은 새 초안으로 저장하세요.</p>}>
    <div className="source-tool-segments" role="group" aria-label="기준 설정 분류">
      <button aria-pressed={tab === 'identity'} onClick={() => setTab('identity')}>외형</button>
      <button aria-pressed={tab === 'roles'} onClick={() => setTab('roles')}>참조</button>
      <button aria-pressed={tab === 'approval'} onClick={() => setTab('approval')}>승인</button>
    </div>
    {tab === 'identity' && <>
      <Input label="새 기준 그림 이름" value={name} maxLength={200} onChange={e=>setName(e.target.value)} placeholder="예: 효과 없는 오른쪽 측면"/>
      <Select label="외형 기준 이미지" value={identity} onChange={e => setIdentity(e.target.value)}>
        <option value="">이미지 선택</option>{p.assets.map(a => <option key={a.assetId} value={a.assetId}>{assetLabel(a)}</option>)}
      </Select>
      <Field label="고정 특징 · 얼굴 / 의상 / 장비 / 팔레트"><textarea value={fixed} onChange={e => setFixed(e.target.value)} placeholder="예: 짧은 은색 머리, 오른팔의 청색 장갑, 붉은 목도리"/></Field>
      <Field label="변경해도 되는 특징"><textarea value={allowed} onChange={e => setAllowed(e.target.value)} placeholder="예: 자세와 표정, 무기의 각도"/></Field>
      <Field label="스타일에서 가져오면 안 되는 특징"><textarea value={forbidden} onChange={e => setForbidden(e.target.value)} placeholder="예: 다른 캐릭터의 의상이나 장비"/></Field>
      <Select label="기준 방향" value={facing} onChange={e => setFacing(e.target.value)}><option value="right">오른쪽</option><option value="left">왼쪽</option><option value="front">정면</option><option value="back">뒷면</option></Select>
    </>}
    {tab === 'roles' && <>
      <p className="caption">스타일과 자세는 보조 참조입니다. 외형 기준은 유지됩니다.</p>
      {p.assets.map(a => <article className="source-tool-reference" key={a.assetId}>
        <img className="checker" src={a.url} alt="" loading="lazy"/><strong>{assetLabel(a)}</strong>
        <div><Check label="스타일" checked={styles.includes(a.assetId)} onChange={() => setStyles(toggle(styles, a.assetId))}/><Check label="자세" checked={poses.includes(a.assetId)} onChange={() => setPoses(toggle(poses, a.assetId))}/></div>
      </article>)}
      {!p.assets.length && <p className="caption">먼저 참조 이미지를 가져오세요.</p>}
    </>}
    {tab === 'approval' && <>
      {p.references.map(r => <article className="source-tool-version" key={r.referenceRevisionId}>
        <div className="row"><strong>{referenceLabel(p,r.referenceRevisionId)}</strong><span className={`badge ${r.approval === 'approved' ? 'success' : 'warn'}`}>{r.approval === 'approved' ? '승인됨' : '초안'}</span></div>
        <ReferenceNameInput s={s} reference={r} label={`기준 ${p.references.indexOf(r)+1} 그림 이름`}/>
        <p>{r.fixedTraits || '등록한 외형 이미지 기준'}</p>
        {r.approval !== 'approved' && <><Check label="외형·역할·방향을 확인했습니다" checked={confirmed} onChange={setConfirmed}/><button disabled={!confirmed || s.busy || !!s.commands.length} onClick={() => s.mutation(`/reference-revisions/${r.referenceRevisionId}/approve`, { expectedRevision: p.revision, reviewChecks: { identity: true } })}>이 기준 승인</button></>}
      </article>)}
      {!p.references.length && <p className="caption">외형 탭에서 첫 기준 초안을 저장하세요.</p>}
    </>}
  </SourcePane>}/>);
}
