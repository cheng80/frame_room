import assert from 'node:assert/strict';
import { createInputState, setKey, stepInput, clampPosition } from './controls.js';

const state = createInputState();
setKey(state, 'ArrowUp', true);
setKey(state, 'w', true);
stepInput(state, 1, 180);
assert.equal(state.y, -180);
setKey(state, 'w', false);
stepInput(state, 1, 180);
assert.equal(state.y, -360);
setKey(state, 'ArrowUp', false);
stepInput(state, 0, 180);
assert.equal(state.action, 'idle');

const diagonal = createInputState();
setKey(diagonal, 'w', true); setKey(diagonal, 'ArrowUp', true);
setKey(diagonal, 'd', true); setKey(diagonal, 'ArrowRight', true);
stepInput(diagonal, 1, 180);
assert.equal(diagonal.direction, 'NE');
assert.ok(Math.abs(Math.hypot(diagonal.x, diagonal.y) - 180) < 1e-9);
setKey(diagonal, 'ArrowUp', false); setKey(diagonal, 'w', false);
stepInput(diagonal, 0, 180);
assert.equal(diagonal.direction, 'E');
assert.equal(diagonal.action, 'walk');
setKey(diagonal, 'ArrowRight', false); setKey(diagonal, 'd', false);
stepInput(diagonal, 0, 180);
assert.equal(diagonal.direction, 'E');
assert.equal(diagonal.action, 'idle');

const opposite = createInputState();
setKey(opposite, 'w', true); setKey(opposite, 'ArrowDown', true);
stepInput(opposite, 1, 180);
assert.equal(opposite.action, 'idle');
assert.deepEqual(clampPosition([0, 0], { x: 100, y: 80 }, { width: 64, height: 64 }, { x: 0.5, y: 0.8 }, 2), [50, 40]);
assert.deepEqual(clampPosition([0, 0], { x: 40, y: 30 }, { width: 64, height: 64 }, { x: 0.5, y: 0.8 }, 2), [20, 15]);
assert.deepEqual(clampPosition([0, 0], { x: 256, y: 256 }, { width: 64, height: 64 }, { x: 0.5, y: 0.8 }, 3), [96, 153.60000000000002]);
console.log('verify: axes, duplicate keys, release, diagonal speed, and sprite bounds pass');
