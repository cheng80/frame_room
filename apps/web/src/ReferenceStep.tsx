import {useEffect,useState} from 'react';
import type {Studio} from './useStudio';
import {referenceLabel,defaultReference} from './referenceLabel';
import {ReferenceNameInput} from './ReferenceNameInput';
import {assetLabel} from './assetProvenance';
import {Field,Input,Select,Check,Empty} from './ui';
import {SourceTool,SourcePane} from './SourceToolLayout';
import {EditorDialog} from './EditorDialog';
import {SpriteImage} from './SpriteViewport';
import type {Reference,Snapshot} from './types';

type ReferenceForm = {name: string; identity: string; styles: string[]; poses: string[]; fixed: string; allowed: string; forbidden: string; facing: string};
const formKey = (projectId: string) => `frame-room-reference-form:${projectId}`;
// Open forms whose unsaved input could not be kept in this browser; the editor blocks leaving while any exist.
let unstoredForms = 0;
export const hasUnstoredReferenceInput = () => unstoredForms > 0;
function referenceForm(p: Snapshot, reference?: Reference): ReferenceForm {
    return {name: reference?.name || '', identity: reference?.identityAssetId || p.assets[0]?.assetId || '', styles: reference?.styleAssetIds || [], poses: reference?.poseAssetIds || [], fixed: reference?.fixedTraits || '', allowed: reference?.allowedChanges || '', forbidden: reference?.forbiddenTransfers || '', facing: reference?.facing || 'right'};
}
/** Unsaved form input this browser kept for this project only; references and assets that no longer exist are dropped. */
function storedForm(p: Snapshot): {editingReferenceId: string; form: ReferenceForm} | null {
    try {
        const value = JSON.parse(localStorage.getItem(formKey(p.projectId)) || 'null');
        if (!value?.form || typeof value.form !== 'object') return null;
        const id = p.references.some(r => r.referenceRevisionId === value.editingReferenceId) ? value.editingReferenceId as string : '';
        const saved = referenceForm(p, p.references.find(r => r.referenceRevisionId === id)), f = value.form;
        const text = (v: unknown, fallback: string) => typeof v === 'string' ? v : fallback;
        const assets = (ids: unknown) => Array.isArray(ids) ? ids.filter(a => p.assets.some(x => x.assetId === a)) : [];
        return {editingReferenceId: id, form: {name: text(f.name, saved.name), identity: p.assets.some(a => a.assetId === f.identity) ? f.identity : saved.identity, styles: assets(f.styles), poses: assets(f.poses), fixed: text(f.fixed, saved.fixed), allowed: text(f.allowed, saved.allowed), forbidden: text(f.forbidden, saved.forbidden), facing: text(f.facing, saved.facing)}};
    } catch { return null; }
}

export function ReferenceStep({ s, initialReferenceRevisionId }: {
    s: Studio;
    initialReferenceRevisionId?: string;
}) {
    const p = s.snapshot!;
    const active = p.references.find(r => r.referenceRevisionId === initialReferenceRevisionId) || defaultReference(p);
    const [restored] = useState(() => storedForm(p));
    const initial = restored?.form || referenceForm(p, active);
    const [editingReferenceId, setEditingReferenceId] = useState(restored ? restored.editingReferenceId : active?.referenceRevisionId || '');
    const [name,setName] = useState(initial.name);
    const [identity, setIdentity] = useState(initial.identity);
    const [styles, setStyles] = useState<string[]>(initial.styles);
    const [poses, setPoses] = useState<string[]>(initial.poses);
    const [fixed, setFixed] = useState(initial.fixed);
    const [allowed, setAllowed] = useState(initial.allowed);
    const [forbidden, setForbidden] = useState(initial.forbidden);
    const [facing, setFacing] = useState(initial.facing);
    const form: ReferenceForm = {name, identity, styles, poses, fixed, allowed, forbidden, facing};
    const editing = p.references.find(r => r.referenceRevisionId === editingReferenceId), saved = referenceForm(p, editing);
    // A new form opened before any asset existed has no identity yet; that is not user input.
    if (!editing && !identity) saved.identity = '';
    const dirty = JSON.stringify(form) !== JSON.stringify(saved);
    const draft = dirty ? JSON.stringify({editingReferenceId, form}) : '';
    // Saving a reference is an explicit API call; until then keep the typed input across reloads and project switches.
    const [storeFailed, setStoreFailed] = useState(false);
    useEffect(() => {
        try { if (draft) localStorage.setItem(formKey(p.projectId), draft); else localStorage.removeItem(formKey(p.projectId)); setStoreFailed(false); }
        catch { setStoreFailed(!!draft); }
    }, [draft, p.projectId]);
    const unstored = dirty && storeFailed;
    useEffect(() => {
        if (!unstored) return;
        const leave = (e: BeforeUnloadEvent) => e.preventDefault();
        unstoredForms++; window.addEventListener('beforeunload', leave);
        return () => { unstoredForms--; window.removeEventListener('beforeunload', leave); };
    }, [unstored]);
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
        const saved = await s.mutation(`/projects/${p.projectId}/reference-revisions`, {
            expectedRevision: p.revision,
            reference,
        });
        if (saved?.referenceRevisionId) { setEditingReferenceId(saved.referenceRevisionId); setName(reference.name); }
    }
    const [tab, setTab] = useState<'identity' | 'roles'>('identity');
    function loadReference(id: string) {
        setEditingReferenceId(id);
        if (!id) {
            setName('');
            setIdentity(p.assets[0]?.assetId || '');
            setStyles([]);
            setPoses([]);
            setFixed('');
            setAllowed('');
            setForbidden('');
            setFacing('right');
            return;
        }
        const reference = p.references.find(r => r.referenceRevisionId === id);
        if (!reference) return;
        setName(reference.name || '');
        setIdentity(reference.identityAssetId || '');
        setStyles(reference.styleAssetIds || []);
        setPoses(reference.poseAssetIds || []);
        setFixed(reference.fixedTraits || '');
        setAllowed(reference.allowedChanges || '');
        setForbidden(reference.forbiddenTransfers || '');
        setFacing(reference.facing || 'right');
    }
    useEffect(() => {
        if (dirty) return;
        if (initialReferenceRevisionId && p.references.some(r => r.referenceRevisionId === initialReferenceRevisionId)) loadReference(initialReferenceRevisionId);
    }, [initialReferenceRevisionId]);
    const identityAsset = p.assets.find(a => a.assetId === identity);
    const [previewAssetId,setPreviewAssetId] = useState('');
    const previewAsset = p.assets.find(a => a.assetId === previewAssetId);
    return (<SourceTool name="캐릭터 기준" preview={<SourcePane title="외형 기준 이미지" className="source-tool-visual-pane" footer={<span>{identityAsset ? `${assetLabel(identityAsset)} · ${identityAsset.width} × ${identityAsset.height}` : '외형 기준을 선택해 주세요'}</span>}>
    <div className="source-tool-canvas checker">{identityAsset ? <SpriteImage src={identityAsset.url} alt="선택한 외형 기준" width={identityAsset.width} height={identityAsset.height} className="source-tool-sprite"/> : <Empty title="외형 기준 이미지가 없습니다"/>}</div>
  </SourcePane>} settings={<SourcePane title="기준 편집" footer={<>{dirty && <>{unstored ? <p className="warning" role="alert">저장하지 않은 기준 입력을 이 브라우저에 보관하지 못했습니다. 이 화면을 떠나면 입력이 사라지므로 새 기준 저장 또는 입력 버리기를 먼저 하세요.</p> : <p className="caption" role="status">저장하지 않은 기준 입력이 있습니다. 이 브라우저에 임시 보관되며, 새 기준 저장을 눌러야 프로젝트에 반영됩니다.</p>}<button type="button" onClick={() => loadReference(editingReferenceId)}>입력 버리기</button></>}<button className="primary full" disabled={!identity || s.busy || !!s.commands.length} onClick={saveReference}>새 기준 저장</button></>}>
    <div className="source-tool-segments" role="group" aria-label="기준 설정 분류">
      <button aria-pressed={tab === 'identity'} onClick={() => setTab('identity')}>외형</button>
      <button aria-pressed={tab === 'roles'} onClick={() => setTab('roles')}>참조</button>
    </div>
    {tab === 'identity' && <>
      {p.references.length >  0 && <Select label="편집할 저장 기준" value={editingReferenceId} onChange={e=>loadReference(e.target.value)}><option value="">새 기준 만들기</option>{p.references.map(r=><option key={r.referenceRevisionId} value={r.referenceRevisionId}>{referenceLabel(p,r.referenceRevisionId)}</option>)}</Select>}
      <Input label="기준 그림 이름" value={name} maxLength={200} onChange={e=>setName(e.target.value)} placeholder="예: 효과 없는 오른쪽 측면"/>
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
        <button type="button" className="source-tool-reference-preview checker" aria-label={`참조 이미지 크게 보기 · ${assetLabel(a)}`} onClick={()=>setPreviewAssetId(a.assetId)}><img src={a.url} alt="" loading="lazy"/></button><strong>{assetLabel(a)}</strong>
        <div><Check label="스타일" checked={styles.includes(a.assetId)} onChange={() => setStyles(toggle(styles, a.assetId))}/><Check label="자세" checked={poses.includes(a.assetId)} onChange={() => setPoses(toggle(poses, a.assetId))}/></div>
      </article>)}
      {!p.assets.length && <p className="caption">먼저 참조 이미지를 가져오세요.</p>}
      <EditorDialog open={!!previewAsset} title="참조 이미지 크게 보기" onClose={()=>setPreviewAssetId('')} className="reference-image-dialog">
        {previewAsset&&<figure className="reference-image-full"><SpriteImage src={previewAsset.url} alt={assetLabel(previewAsset)} width={previewAsset.width} height={previewAsset.height}/><figcaption>{assetLabel(previewAsset)} · {previewAsset.width} × {previewAsset.height}</figcaption></figure>}
      </EditorDialog>
    </>}
    {p.references.map(r => <article className="source-tool-version" key={r.referenceRevisionId}>
        <div className="row"><strong>{referenceLabel(p,r.referenceRevisionId)}</strong></div>
        <ReferenceNameInput s={s} reference={r} label={`기준 ${p.references.indexOf(r)+1} 그림 이름`}/>
        <p>{r.fixedTraits || '등록한 외형 이미지 기준'}</p>
      </article>)}
  </SourcePane>}/>);
}
