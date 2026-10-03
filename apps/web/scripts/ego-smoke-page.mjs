// Executed only by the installed ego-browser embedded Node runtime.
// Numeric ID resumes an existing space; no creation, takeover, or finish call.
const task = await taskSpace(smokeConfig.spaceId);
const label = smokeConfig.pageLabel;
const tab = (await task.tabs()).find(item => item.label === label);
if (!tab) throw new Error('지정한 기존 managed 탭이 없습니다. 새 탭은 만들지 않습니다.');
const page = task.page(label);
const expectedOrigin = smokeConfig.origin;
if (new URL(await page.url()).origin !== expectedOrigin) {
  throw new Error('지정 탭이 로컬 앱 origin과 다릅니다. 자동 이동하지 않습니다.');
}
const state = await page.evaluate(async origin => {
  if (location.origin !== origin) throw new Error('검사 중 탭 origin이 변경되었습니다.');
  const mounted = Boolean(document.querySelector('#root main')) && document.title.includes('프레임룸');
  const connected = document.querySelector('.service.online')?.textContent?.trim() === '로컬 서비스 연결됨';
  const response = await fetch('/v1/health', {
    method: 'GET', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error(`앱 API health HTTP ${response.status}`);
  const health = await response.json();
  // Do not return sessionToken or application/project contents to the CLI log.
  return { mounted, connected, api: health.api, worker: health.worker, engineAvailable: health.engine?.available === true };
}, expectedOrigin);
if (!state.mounted || !state.connected || state.api !== 'ready' || state.worker !== 'ready' || !state.engineAvailable) {
  throw new Error(`앱/작업 처리기 연결이 준비되지 않았습니다: ${JSON.stringify(state)}`);
}
console.log(JSON.stringify({ browser: 'ego', taskSpaceId: task.spaceId, page: label, ...state }));
console.log('EGO_SMOKE_PASS');
