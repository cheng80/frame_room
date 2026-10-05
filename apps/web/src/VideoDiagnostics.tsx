import {videoDiagnostics} from './videoDiagnosticMessages';

export function VideoDiagnostics({processing}: {processing: unknown}) {
  const rows = videoDiagnostics(processing);
  if (!rows.length) return null;
  return <section className="video-diagnostics" aria-label="영상 처리 진단">
    <strong>영상 처리 진단</strong>
    {rows.map(row => <p key={row.id} className={row.level === 'warning' ? 'warning' : 'caption'}>{row.message}</p>)}
  </section>;
}
