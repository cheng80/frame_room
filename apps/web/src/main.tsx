import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import './styles.css';
class ErrorBoundary extends React.Component<{children:React.ReactNode},{error:boolean}>{state={error:false};static getDerivedStateFromError(){return {error:true};}render(){return this.state.error?<main className="page"><h1>화면을 표시하지 못했습니다</h1><p>저장된 프로젝트와 브라우저에 보관된 초안은 유지됩니다.</p><button onClick={()=>location.reload()}>화면 다시 열기</button></main>:this.props.children;}}
createRoot(document.getElementById('root')!).render(<ErrorBoundary><App/></ErrorBoundary>);
