const test = require('node:test');
const assert = require('node:assert/strict');
const {
  buildTextCommand,
  buildPttStart,
  buildPttEnd,
  buildLocation,
  encodeAudioChunk,
  decodeServerFrame,
  parseServerMessage,
} = require('./protocol');

test('buildTextCommand encodes text as a command message', () => {
  const raw = buildTextCommand('not defterini aç');
  assert.deepEqual(JSON.parse(raw), { type: 'command', text: 'not defterini aç' });
});

test('buildPttStart encodes a ptt_start message', () => {
  assert.deepEqual(JSON.parse(buildPttStart()), { type: 'ptt_start' });
});

test('buildPttEnd encodes a ptt_end message', () => {
  assert.deepEqual(JSON.parse(buildPttEnd()), { type: 'ptt_end' });
});

test('buildLocation encodes lat/lon as a location message', () => {
  const raw = buildLocation(41.2544, 32.6944);
  assert.deepEqual(JSON.parse(raw), { type: 'location', lat: 41.2544, lon: 32.6944 });
});

test('encodeAudioChunk prefixes PCM16 data with tag 0x01', () => {
  const pcm = new Int16Array([1, -1, 256]);
  const frame = encodeAudioChunk(pcm);
  const bytes = new Uint8Array(frame);

  assert.equal(bytes[0], 0x01);
  assert.equal(bytes.length, 1 + pcm.byteLength);
  const payload = new Int16Array(bytes.slice(1).buffer);
  assert.deepEqual(Array.from(payload), [1, -1, 256]);
});

test('decodeServerFrame parses JSON text frames via parseServerMessage', () => {
  const msg = decodeServerFrame('{"type":"status","state":"idle"}');
  assert.deepEqual(msg, { type: 'status', state: 'idle' });
});

test('decodeServerFrame decodes tag 0x02 binary frames as audio_chunk', () => {
  const payload = new Uint8Array([9, 8, 7]);
  const frame = new Uint8Array(1 + payload.length);
  frame[0] = 0x02;
  frame.set(payload, 1);

  const msg = decodeServerFrame(frame.buffer);

  assert.equal(msg.type, 'audio_chunk');
  assert.deepEqual(Array.from(new Uint8Array(msg.data)), [9, 8, 7]);
});

test('decodeServerFrame throws on unknown binary tag', () => {
  const frame = new Uint8Array([0x99, 1, 2]);
  assert.throws(() => decodeServerFrame(frame.buffer));
});

test('parseServerMessage returns the parsed object for a valid message', () => {
  const msg = parseServerMessage('{"type":"response","text":"merhaba"}');
  assert.deepEqual(msg, { type: 'response', text: 'merhaba' });
});

test('parseServerMessage throws when "type" is missing', () => {
  assert.throws(() => parseServerMessage('{"text":"merhaba"}'));
});
