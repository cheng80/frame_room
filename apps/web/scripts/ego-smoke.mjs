import { accessSync, constants, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { delimiter, join } from 'node:path';
import { spawnSync } from 'node:child_process';

// Local launcher only. Never install, start, navigate, or close a browser.
try {
  if (process.argv.length > 2) throw new Error('Playwright 옵션은 지원하지 않습니다. apps/web/README.md의 ego smoke 설정을 사용하세요.');
  if (!/^[1-9]\d*$/.test(process.env.EGO_TASK_SPACE_ID || '') ||
      !Number.isSafeInteger(Number(process.env.EGO_TASK_SPACE_ID)) ||
      !/^p[1-9]\d*$/.test(process.env.EGO_PAGE_LABEL || '')) {
    throw new Error('사용 허가된 기존 탭의 EGO_TASK_SPACE_ID와 EGO_PAGE_LABEL을 지정하세요. 다른 작업의 TaskSpace를 자동 선택하지 않습니다.');
  }
  const expected = new URL(process.env.SPRITE_TEST_URL || 'http://127.0.0.1:5173');
  if (expected.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(expected.hostname) ||
      expected.username || expected.password || expected.pathname !== '/' || expected.search || expected.hash) {
    throw new Error('SPRITE_TEST_URL은 로컬 앱 origin이어야 합니다 (예: http://127.0.0.1:5173).');
  }
  const candidates = process.env.EGO_BROWSER_BIN ? [process.env.EGO_BROWSER_BIN] : [
    ...(process.env.PATH || '').split(delimiter).filter(Boolean).map(dir => join(dir, 'ego-browser')),
    join(homedir(), '.local/bin/ego-browser'),
  ];
  const executable = candidates.find(path => {
    try { accessSync(path, constants.X_OK); return true; } catch { return false; }
  });
  if (!executable) throw new Error('설치된 ego-browser CLI가 없습니다. 자동 설치하지 않습니다. EGO_BROWSER_BIN 또는 PATH를 확인하세요.');
  // This installed CLI/browser is macOS-only. Check without opening any app.
  if (process.platform !== 'darwin' || spawnSync('/usr/bin/pgrep', ['-x', 'ego lite'], { timeout: 3000 }).status !== 0) {
    throw new Error('실행 중인 macOS ego lite 브라우저가 없습니다. 자동 실행하지 않습니다.');
  }
  const serverName = process.env.EGO_SERVER_NAME;
  if (serverName && !/^[A-Za-z0-9_-]{1,64}$/.test(serverName)) throw new Error('EGO_SERVER_NAME 형식이 올바르지 않습니다.');
  const args = serverName ? [`--ego-server-name=${serverName}`, 'nodejs'] : ['nodejs'];
  const result = spawnSync(executable, args, {
    input: `const smokeConfig = ${JSON.stringify({spaceId:Number(process.env.EGO_TASK_SPACE_ID),pageLabel:process.env.EGO_PAGE_LABEL,origin:expected.origin})};\n` + readFileSync(new URL('./ego-smoke-page.mjs', import.meta.url), 'utf8'),
    encoding: 'utf8', timeout: 20000, killSignal: 'SIGKILL', maxBuffer: 1024 * 1024,
    env: { ...process.env, SPRITE_TEST_URL: expected.origin },
  });
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  const messages = `${result.stdout || ''}\n${result.stderr || ''}`.split(/\r?\n/).map(line=>line.trim());
  if (result.error || result.status !== 0 || !messages.includes('EGO_SMOKE_PASS')) {
    throw new Error(`ego 연결 또는 앱 smoke 실패 (exit ${result.status}${result.error ? `, ${result.error.code}` : ''}). 자동 재시도·브라우저 실행은 하지 않습니다.`);
  }
} catch (error) {
  console.error(`[ego-smoke] ${error.message}`);
  process.exitCode = 1;
}
