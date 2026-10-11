import {useState,useId,type ReactNode} from 'react';
import './source-tools.css';

/** The dialog owns its header; this grid fills only its remaining tool-content. */
export function SourceTool({ name, previewLabel = '미리보기', preview, settings, toolbar }: {
    name: string;
    previewLabel?: string;
    preview: ReactNode;
    settings: ReactNode;
    toolbar?: ReactNode;
}) {
    const [pane, setPane] = useState<'preview' | 'settings'>('preview');
    const id = useId();
    return (<div className="source-tool" data-mobile-pane={pane} aria-label={name}>
      {toolbar && <div className="source-tool-toolbar">{toolbar}</div>}
      <div className="source-tool-switch" role="group" aria-label={`${name} 보기 전환`}>
        <button type="button" aria-pressed={pane === 'preview'} aria-controls={`${id}-preview`} onClick={() => setPane('preview')}>{previewLabel}</button>
        <button type="button" aria-pressed={pane === 'settings'} aria-controls={`${id}-settings`} onClick={() => setPane('settings')}>설정</button>
      </div>
      <div className="source-tool-columns">
        <div id={`${id}-preview`} className="source-tool-preview">{preview}</div>
        <div id={`${id}-settings`} className="source-tool-settings">{settings}</div>
      </div>
    </div>);
}
export function SourcePane({ title, children, footer, className = '' }: {
    title: string;
    children: ReactNode;
    footer?: ReactNode;
    className?: string;
}) {
    const id = useId();
    return (<section className={`source-tool-pane ${className}`} aria-labelledby={id}>
      <h2 className="source-tool-heading" id={id}>{title}</h2>
      <div className="source-tool-scroll" tabIndex={0} role="region" aria-label={`${title} 내용`}>{children}</div>
      {footer && <div className="source-tool-footer">{footer}</div>}
    </section>);
}
