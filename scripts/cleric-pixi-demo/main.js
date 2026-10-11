import { createInputState, setKey, stepInput, clampPosition as clampCoordinates, DIRECTIONS } from './controls.js';

const $ = (id) => document.getElementById(id);
const status = { loaded: false, direction: 'S', action: 'idle', frame: 0, x: 0, y: 0 };
window.__clericDemo = {
  getState: () => ({ ...status, loadedClips: status.loaded ? 16 : 0 }),
};

function fail(error) {
  $('load-state').textContent = '불러오기 실패';
  $('error').style.display = 'block';
  $('error').textContent = `리소스를 읽지 못했습니다. 같은 폴더에 atlas JSON·manifest JSON·PNG를 두고 로컬 HTTP 서버로 열어 주세요.\n${error.message}`;
}

try {
  if (!window.PIXI) throw new Error('PixiJS 로컬 번들을 찾지 못했습니다.');
  const [atlasResponse, manifestResponse] = await Promise.all([
    fetch('./cleric-atlas.json'), fetch('./cleric-manifest.json'),
  ]);
  if (!atlasResponse.ok || !manifestResponse.ok) throw new Error(`JSON 응답 오류 (${atlasResponse.status}, ${manifestResponse.status})`);
  const [atlasData, manifest] = await Promise.all([atlasResponse.json(), manifestResponse.json()]);
  if (!Array.isArray(manifest.directions) || !DIRECTIONS.every((direction, index) => manifest.directions[index] === direction) || !manifest.animations || !manifest.cell || !manifest.anchor || !atlasData.frames || !atlasData.meta?.image) throw new Error('manifest 또는 atlas 형식이 올바르지 않습니다.');
  if (!(manifest.cell.width > 0 && manifest.cell.height > 0) || !Number.isFinite(manifest.anchor.x) || !Number.isFinite(manifest.anchor.y)) throw new Error('cell 크기나 anchor 값이 올바르지 않습니다.');
  for (const direction of DIRECTIONS) for (const action of ['walk', 'idle']) {
    const key = `${action}_${direction}`;
    if (!Array.isArray(manifest.animations[key]?.frameNames) || !manifest.animations[key].frameNames.length) throw new Error(`manifest에 ${key} 프레임이 없습니다.`);
    const clip = manifest.animations[key];
    clip.frameNames.forEach((name, index) => {
      if (!atlasData.frames[name]) throw new Error(`atlas에 프레임 ${name}이 없습니다.`);
      const duration = clip.durationsMs?.[index] ?? atlasData.frames[name]?.duration ?? 100;
      if (!Number.isFinite(duration) || duration <= 0) throw new Error(`${key}의 ${name} 재생 시간이 올바르지 않습니다.`);
    });
  }

  const app = new PIXI.Application();
  await app.init({ background: '#202b2e', antialias: false, autoDensity: false, resolution: 1, resizeTo: $('stage') });
  $('stage').appendChild(app.canvas);
  const atlasUrl = new URL(atlasData.meta.image, new URL('./cleric-atlas.json', location.href)).href;
  const sheet = await PIXI.Assets.load(new URL('./cleric-atlas.json', location.href).href);
  $('atlas-download').href = atlasUrl;
  const input = createInputState();
  const sprite = new PIXI.AnimatedSprite([{ texture: PIXI.Texture.EMPTY, time: 100 }]);
  sprite.anchor.set(manifest.anchor.x, manifest.anchor.y);
  sprite.loop = true;
  sprite.autoUpdate = false;
  sprite.roundPixels = true;
  const firstTexture = sheet.textures[manifest.animations.idle_S.frameNames[0]];
  if (!firstTexture) throw new Error('idle_S 첫 프레임을 atlas에서 찾지 못했습니다.');
  firstTexture.source.scaleMode = 'nearest';
  app.stage.addChild(sprite);

  const scaleFor = (width, height) => {
    const fit = Math.min(width / manifest.cell.width, height / manifest.cell.height);
    return fit >= 3 ? 3 : fit >= 2 ? 2 : fit;
  };
  let pixelScale = scaleFor(app.screen.width, app.screen.height);
  sprite.scale.set(pixelScale);
  const grid = new PIXI.Graphics();
  app.stage.addChildAt(grid, 0);
  function drawGrid() {
    grid.clear();
    const w = app.screen.width; const h = app.screen.height;
    const spacing = Math.max(24, Math.round(48 * pixelScale));
    grid.setStrokeStyle({ width: 1, color: 0x435459, alpha: 0.28 });
    for (let x = -h; x < w + h; x += spacing) grid.moveTo(x, 0).lineTo(x + h, h);
    for (let x = 0; x < w + h; x += spacing) grid.moveTo(x, 0).lineTo(x - h, h);
    grid.stroke();
  }

  function chooseClip() {
    const key = `${input.action}_${input.direction}`;
    const clip = manifest.animations[key];
    const frames = clip.frameNames.map((name, index) => {
      const texture = sheet.textures[name];
      if (!texture) throw new Error(`atlas에 프레임 ${name}이 없습니다.`);
      return { texture, time: clip.durationsMs?.[index] ?? atlasData.frames[name]?.duration ?? 100 };
    });
    sprite.textures = frames;
    sprite.gotoAndPlay(0);
    status.direction = input.direction;
    status.action = input.action;
    $('direction').textContent = input.direction;
    $('action').textContent = input.action === 'walk' ? '걷기' : '대기';
  }

  function clampPosition() {
    [sprite.x, sprite.y] = clampCoordinates([input.x, input.y], { x: app.screen.width, y: app.screen.height }, manifest.cell, manifest.anchor, pixelScale);
    input.x = sprite.x; input.y = sprite.y;
    status.x = Math.round(input.x); status.y = Math.round(input.y);
    $('position').textContent = `${status.x}, ${status.y}`;
  }

  function update(seconds, ticker) {
    const oldDirection = input.direction; const oldAction = input.action;
    stepInput(input, Math.min(seconds, 0.1), 180);
    if (oldDirection !== input.direction || oldAction !== input.action) chooseClip();
    clampPosition();
    if (ticker) sprite.update(ticker);
    status.frame = Math.floor(sprite.currentFrame);
    $('frame').textContent = `${status.frame + 1}/${sprite.totalFrames}`;
  }

  window.__clericDemo.press = (key) => setKey(input, key, true);
  window.__clericDemo.release = (key) => setKey(input, key, false);
  window.__clericDemo.tick = (seconds) => update(seconds, { deltaTime: seconds * 60, deltaMS: seconds * 1000 });
  const isEditing = (target) => target instanceof Element && target.closest('input, select, textarea, [contenteditable]:not([contenteditable="false"]), [role="textbox"]');
  window.addEventListener('keydown', (event) => {
    if (isEditing(event.target)) return;
    if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(event.key)) event.preventDefault();
    setKey(input, event.key, true);
  });
  window.addEventListener('keyup', (event) => setKey(input, event.key, false));
  window.addEventListener('blur', () => input.keys.clear());
  document.addEventListener('visibilitychange', () => { if (document.hidden) input.keys.clear(); });
  app.renderer.on('resize', (width, height) => {
    pixelScale = scaleFor(width, height); sprite.scale.set(pixelScale); drawGrid(); clampPosition();
  });
  input.x = app.screen.width / 2;
  input.y = app.screen.height / 2 + (manifest.anchor.y - 0.5) * manifest.cell.height * pixelScale;
  drawGrid(); chooseClip(); clampPosition();
  app.ticker.add((ticker) => update(ticker.deltaMS / 1000, ticker));
  status.loaded = true;
  $('load-state').textContent = '16/16 동작 불러옴';
} catch (error) {
  fail(error);
}
