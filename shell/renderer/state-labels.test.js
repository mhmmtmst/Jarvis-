const test = require('node:test');
const assert = require('node:assert/strict');
const { describeAgentState } = require('./state-labels');

test('describeAgentState translates idle', () => {
  assert.equal(describeAgentState('idle'), 'boşta');
});

test('describeAgentState translates listening', () => {
  assert.equal(describeAgentState('listening'), 'dinliyor');
});

test('describeAgentState translates thinking', () => {
  assert.equal(describeAgentState('thinking'), 'düşünüyor');
});

test('describeAgentState translates speaking', () => {
  assert.equal(describeAgentState('speaking'), 'konuşuyor');
});

test('describeAgentState translates error', () => {
  assert.equal(describeAgentState('error'), 'hata');
});

test('describeAgentState falls back to the raw state for an unknown value', () => {
  assert.equal(describeAgentState('mystery'), 'mystery');
});
