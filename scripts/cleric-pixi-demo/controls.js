export const DIRECTIONS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
const KEY_DIRECTIONS = {
  ArrowUp: [0, -1], w: [0, -1], ArrowDown: [0, 1], s: [0, 1],
  ArrowLeft: [-1, 0], a: [-1, 0], ArrowRight: [1, 0], d: [1, 0],
};

export function createInputState() {
  return { keys: new Set(), direction: 'S', action: 'idle', x: 0, y: 0 };
}

export function setKey(state, key, pressed) {
  const normalized = key.length === 1 ? key.toLowerCase() : key;
  if (!KEY_DIRECTIONS[normalized]) return;
  if (pressed) state.keys.add(normalized);
  else state.keys.delete(normalized);
}

export function stepInput(state, deltaSeconds, speed) {
  const up = state.keys.has('ArrowUp') || state.keys.has('w');
  const down = state.keys.has('ArrowDown') || state.keys.has('s');
  const left = state.keys.has('ArrowLeft') || state.keys.has('a');
  const right = state.keys.has('ArrowRight') || state.keys.has('d');
  let dx = Number(right && !left) - Number(left && !right);
  let dy = Number(down && !up) - Number(up && !down);
  if (dx || dy) {
    const length = Math.hypot(dx, dy);
    dx /= length;
    dy /= length;
    state.direction = DIRECTIONS[Math.round((Math.atan2(dx, -dy) / (Math.PI / 4) + 8) % 8)];
    state.action = 'walk';
    state.x += dx * speed * deltaSeconds;
    state.y += dy * speed * deltaSeconds;
  } else {
    state.action = 'idle';
  }
  return state;
}

export function clampPosition(position, stage, cell, anchor, scale) {
  return ['x', 'y'].map((axis, index) => {
    const size = cell[index === 0 ? 'width' : 'height'] * scale;
    const start = anchor[axis] * size;
    const end = stage[axis] - (1 - anchor[axis]) * size;
    return end < start ? stage[axis] / 2 : Math.max(start, Math.min(end, position[index]));
  });
}
