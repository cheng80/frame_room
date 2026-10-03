// Historical tests remain in tests/journey.e2e.ts. Browser testing is ego-only.
// Fail during config loading, before Playwright can launch a browser.
throw new Error('Playwright 브라우저 실행은 비활성화되었습니다. 기존 ego 탭을 지정하고 npm run test:e2e를 사용하세요. apps/web/README.md 참고.');
export default {};
