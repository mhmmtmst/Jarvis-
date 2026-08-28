const test = require('node:test');
const assert = require('node:assert/strict');
const { parseEnvFile, updateEnvFile } = require('./settings');

test('parseEnvFile extracts KEY=value pairs, skipping blanks and comments', () => {
  const text = [
    '# yorum satırı',
    '',
    'GEMINI_API_KEY=abc123',
    'JARVIS_WS_PORT=8765',
  ].join('\n');

  assert.deepEqual(parseEnvFile(text), {
    GEMINI_API_KEY: 'abc123',
    JARVIS_WS_PORT: '8765',
  });
});

test('parseEnvFile handles a value that itself contains an equals sign', () => {
  const text = 'JARVIS_REPORT_PROJECTS=Odakla:C:/x=y,Jarvis:C:/z';
  assert.deepEqual(parseEnvFile(text), {
    JARVIS_REPORT_PROJECTS: 'Odakla:C:/x=y,Jarvis:C:/z',
  });
});

test('updateEnvFile replaces an existing key in place, preserving order and comments', () => {
  const text = [
    '# yorum',
    'GEMINI_API_KEY=abc123',
    'JARVIS_TTS_VOICE=Kore',
    'JARVIS_WS_PORT=8765',
  ].join('\n');

  const result = updateEnvFile(text, { JARVIS_TTS_VOICE: 'Charon' });

  assert.equal(result, [
    '# yorum',
    'GEMINI_API_KEY=abc123',
    'JARVIS_TTS_VOICE=Charon',
    'JARVIS_WS_PORT=8765',
  ].join('\n'));
});

test('updateEnvFile appends a key that does not exist yet in the file', () => {
  const text = 'GEMINI_API_KEY=abc123';

  const result = updateEnvFile(text, { JARVIS_TTS_VOICE: 'Charon' });

  assert.equal(result, 'GEMINI_API_KEY=abc123\nJARVIS_TTS_VOICE=Charon');
});

test('updateEnvFile handles multiple updates in one call, mixing replace and append', () => {
  const text = 'JARVIS_GEMINI_MODEL=old-model';

  const result = updateEnvFile(text, {
    JARVIS_GEMINI_MODEL: 'new-model',
    JARVIS_WEATHER_LOCATION: 'Safranbolu',
  });

  assert.equal(result, 'JARVIS_GEMINI_MODEL=new-model\nJARVIS_WEATHER_LOCATION=Safranbolu');
});

test('updateEnvFile on an empty starting file just appends all updates', () => {
  const result = updateEnvFile('', { JARVIS_TTS_VOICE: 'Charon' });
  assert.equal(result, 'JARVIS_TTS_VOICE=Charon');
});

const { resolveEnvPath, resolveMemoryPath, MANAGED_KEYS } = require('./settings');

test('MANAGED_KEYS includes GEMINI_API_KEY', () => {
  assert.ok(MANAGED_KEYS.includes('GEMINI_API_KEY'));
});

test('MANAGED_KEYS includes JARVIS_MODE', () => {
  assert.ok(MANAGED_KEYS.includes('JARVIS_MODE'));
});

test('MANAGED_KEYS includes JARVIS_TTS_VOICE', () => {
  assert.ok(MANAGED_KEYS.includes('JARVIS_TTS_VOICE'));
});

test('readSettings picks up GEMINI_API_KEY from the .env text via parseEnvFile/updateEnvFile round trip', () => {
  const text = 'GEMINI_API_KEY=secret-abc\nJARVIS_TTS_VOICE=Kore';
  assert.deepEqual(parseEnvFile(text), {
    GEMINI_API_KEY: 'secret-abc',
    JARVIS_TTS_VOICE: 'Kore',
  });
});

test('resolveEnvPath returns the dev path (projectRoot/agent/.env) when not packaged', () => {
  const result = resolveEnvPath({
    isPackaged: false,
    userDataPath: 'C:/Users/x/AppData/Roaming/Jarvis',
    projectRoot: 'C:/jarvis',
  });
  assert.equal(result, require('path').join('C:/jarvis', 'agent', '.env'));
});

test('resolveEnvPath returns the userData path (userDataPath/.env) when packaged', () => {
  const result = resolveEnvPath({
    isPackaged: true,
    userDataPath: 'C:/Users/x/AppData/Roaming/Jarvis',
    projectRoot: 'C:/jarvis',
  });
  assert.equal(result, require('path').join('C:/Users/x/AppData/Roaming/Jarvis', '.env'));
});

test('resolveMemoryPath returns the dev path (projectRoot/agent/memory.json) when not packaged', () => {
  const result = resolveMemoryPath({
    isPackaged: false,
    userDataPath: 'C:/Users/x/AppData/Roaming/Jarvis',
    projectRoot: 'C:/jarvis',
  });
  assert.equal(result, require('path').join('C:/jarvis', 'agent', 'memory.json'));
});

test('resolveMemoryPath returns the userData path (userDataPath/memory.json) when packaged, so it survives auto-updates', () => {
  const result = resolveMemoryPath({
    isPackaged: true,
    userDataPath: 'C:/Users/x/AppData/Roaming/Jarvis',
    projectRoot: 'C:/jarvis',
  });
  assert.equal(result, require('path').join('C:/Users/x/AppData/Roaming/Jarvis', 'memory.json'));
});
