export interface VideoDiagnostic {id: string; level: 'info' | 'warning'; message: string}
const record = (value: unknown): Record<string, unknown> | null => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
const count = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
const indices = (value: unknown): number[] | null => Array.isArray(value) && value.every(item => Number.isSafeInteger(item) && item >= 0) ? value : null;

/** Saved job diagnostics only; tolerate older records and do not infer missing evidence. */
export function videoDiagnostics(processing: unknown): VideoDiagnostic[] {
  const selection = record(record(processing)?.selection);
  if (!selection) return [];
  const rows: VideoDiagnostic[] = [];
  const add = (id: string, level: VideoDiagnostic['level'], message: string) => rows.push({id, level, message});
  const period = record(selection.period);
  if (period?.suspect === true || Array.isArray(period?.suspects) && period.suspects.length > 0) {
    add('period', 'warning', '선택 구간에 여러 주기가 들어 있을 수 있습니다. 왼발·오른발이 한 번씩 돌아오는지 원본을 보고 수동 구간을 확인하세요.');
  }
  const held = record(selection.held);
  const hold = count(held?.hold), rate = count(held?.drawings_per_second);
  if (hold !== null && hold > 1) {
    add('held', 'info', `원본은 같은 자세를 약 ${hold}프레임씩 유지합니다.${rate !== null ? ` 자세 변화는 초당 약 ${rate.toFixed(1)}회입니다.` : ''} 프레임 수를 늘려도 새 동작 디테일이 생기지는 않습니다.`);
  }
  const sizeHold = record(selection.sizeHold);
  if (sizeHold?.applied === true) add('size', 'info', '같은 자세 사이에서 달라진 몸 크기를 보정했습니다. 원본과 결과의 비율을 확인하세요.');
  const alignment = record(selection.alignment) ?? record(selection.cycleAlignment);
  const resample = record(alignment?.resample) ?? alignment;
  if (resample) {
    const made = indices(alignment?.outputMadeAt)?.length ?? indices(resample.made_at)?.length ?? count(resample.made) ?? count(resample.made_by_rife);
    const nearest = indices(alignment?.outputNearestAt)?.length ?? indices(resample.nearest_at)?.length ?? count(resample.nearest);
    if (made !== null || nearest !== null) {
      add('resample', 'info', [made !== null ? `새 보간 ${made}장` : '', nearest !== null ? `가까운 원본 사용 ${nearest}장` : ''].filter(Boolean).join(' · '));
    }
    const smears = Array.isArray(resample.smear) ? resample.smear.map(record).filter(item => item && Array.isArray(item.faults) && item.faults.length > 0) : [];
    const replaced = smears.filter(item => item?.method === 'nearest').length;
    const retained = smears.filter(item => item?.method === 'rife').length;
    if (replaced) add('protected', 'info', `번짐·윤곽 손상이 감지된 보간 ${replaced}장을 가까운 원본으로 대체했습니다.`);
    if (retained) add('smear', 'warning', `번짐·윤곽 손상이 감지된 보간 ${retained}장이 남아 있습니다. 주기 보간을 자동으로 바꾸거나 해당 프레임을 확인하세요.`);
  }
  const outputPhase = record(selection.outputPhase);
  const manualPhase = outputPhase?.manual === true || alignment?.phase === 'manual';
  if (manualPhase) {
    const index = count(outputPhase?.turnedBy ?? alignment?.turnedBy);
    add('phase', 'info', `수동 시작 위치 적용${index !== null ? ` · 결과 ${index}번 (0부터)` : ''}`);
  }
  const foot = manualPhase ? null : record(alignment?.footStrike) ?? record(outputPhase?.footStrike) ?? record(selection.footStrike);
  if (foot) {
    const named = foot.start_foot ?? foot.startFoot;
    const candidates = indices(foot.candidates) ?? indices(foot.strikes);
    const manual = foot.by === 'manual' || foot.start_foot_source === 'manual' || foot.source === 'manual';
    if (manual) {
      add('foot', 'info', `수동 시작 위치 적용${count(foot.start) !== null ? ` · ${foot.start}번 (0부터)` : ''}`);
    } else if (named === 'left' || named === 'right') {
      const applied = !!alignment || !!outputPhase || foot.indexSpace !== 'selected-source-cycle';
      add('foot', 'info', `${applied ? '시작 발' : '원본의 발 디딤 판정'} · 캐릭터의 ${named === 'left' ? '왼발' : '오른발'}${foot.start_foot_source === 'given' ? ' · 수동 지정' : ''}${!applied ? ' · 결과 시작은 유지' : ''}`);
    } else if ('start_foot' in foot || 'startFoot' in foot || foot.foot_why || foot.reason) {
      add('foot', 'warning', `시작 발의 좌우를 확정하지 못했습니다.${candidates?.length ? ` 발 디딤 후보: ${candidates.join(', ')}번 (${foot.indexSpace === 'selected-source-cycle' ? '선택한 원본 구간에서 ' : ''}0부터).` : ''} 원본을 확인한 뒤 필요하면 결과의 수동 시작 위치를 지정하세요.`);
    }
  }
  const retake = record(selection.retake);
  if (retake?.suggested === true) {
    const reasons = Array.isArray(retake.reasons) ? retake.reasons : [];
    const heldReason = reasons.some(reason => reason === 'held-drawings' || record(reason)?.reason === 'held-drawings');
    add('retake', 'warning', `${heldReason ? '원본의 자세 변화가 부족해 보간으로 채우기 어렵습니다.' : '이 원본은 새 촬영 검토 대상으로 표시됐습니다.'} 먼저 기존 영상의 다른 구간을 확인하세요. 새 영상은 자동 생성하지 않습니다.`);
  }
  return rows;
}
