(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.jarvisProtocol = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  function buildTextCommand(text) {
    return JSON.stringify({ type: 'command', text });
  }

  function buildPttStart() {
    return JSON.stringify({ type: 'ptt_start' });
  }

  function buildPttEnd() {
    return JSON.stringify({ type: 'ptt_end' });
  }

  function buildLocation(lat, lon) {
    return JSON.stringify({ type: 'location', lat, lon });
  }

  function encodeAudioChunk(int16Array) {
    const bytes = new Uint8Array(int16Array.buffer, int16Array.byteOffset, int16Array.byteLength);
    const frame = new Uint8Array(1 + bytes.length);
    frame[0] = 0x01;
    frame.set(bytes, 1);
    return frame.buffer;
  }

  function parseServerMessage(raw) {
    const msg = JSON.parse(raw);
    if (typeof msg.type !== 'string') {
      throw new Error('Sunucu mesajında "type" alanı yok.');
    }
    return msg;
  }

  function decodeServerFrame(data) {
    if (data instanceof ArrayBuffer) {
      const bytes = new Uint8Array(data);
      if (bytes[0] === 0x02) {
        return { type: 'audio_chunk', data: bytes.slice(1).buffer };
      }
      throw new Error('Bilinmeyen binary frame tipi: ' + bytes[0]);
    }
    return parseServerMessage(data);
  }

  return {
    buildTextCommand,
    buildPttStart,
    buildPttEnd,
    buildLocation,
    encodeAudioChunk,
    decodeServerFrame,
    parseServerMessage,
  };
});
