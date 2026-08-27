const test = require('node:test');
const assert = require('node:assert/strict');
const { orbColorForState, orbMotionTarget } = require('./orb');

test('orbColorForState returns the accent color for idle', () => {
  assert.deepEqual(orbColorForState('idle', false), [107, 107, 245]);
});

test('orbColorForState returns the same accent color for listening', () => {
  assert.deepEqual(orbColorForState('listening', false), [107, 107, 245]);
});

test('orbColorForState returns amber for thinking', () => {
  assert.deepEqual(orbColorForState('thinking', false), [217, 180, 106]);
});

test('orbColorForState returns sky blue for speaking', () => {
  assert.deepEqual(orbColorForState('speaking', false), [126, 200, 227]);
});

test('orbColorForState returns red for error', () => {
  assert.deepEqual(orbColorForState('error', false), [226, 104, 95]);
});

test('orbColorForState returns neutral gray when paused, regardless of state', () => {
  assert.deepEqual(orbColorForState('speaking', true), [85, 85, 92]);
});

test('orbColorForState falls back to the idle color for an unknown state', () => {
  assert.deepEqual(orbColorForState('bogus', false), [107, 107, 245]);
});

test('orbMotionTarget returns the paused target when paused, regardless of state', () => {
  assert.deepEqual(orbMotionTarget('speaking', { paused: true, speaking: true }), { scale: [0.6, 0.64], halo: [4, 8] });
});

test('orbMotionTarget returns the speaking target when speaking', () => {
  assert.deepEqual(orbMotionTarget('speaking', { paused: false, speaking: true }), { scale: [0.98, 1.08], halo: [70, 100] });
});

test('orbMotionTarget returns the thinking target for the thinking state', () => {
  assert.deepEqual(orbMotionTarget('thinking', { paused: false, speaking: false }), { scale: [0.82, 0.88], halo: [45, 60] });
});

test('orbMotionTarget returns the default target for idle, listening, and error', () => {
  const expected = { scale: [0.74, 0.8], halo: [18, 28] };
  assert.deepEqual(orbMotionTarget('idle', { paused: false, speaking: false }), expected);
  assert.deepEqual(orbMotionTarget('listening', { paused: false, speaking: false }), expected);
  assert.deepEqual(orbMotionTarget('error', { paused: false, speaking: false }), expected);
});
