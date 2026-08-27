const fs = require('fs');
const path = require('path');

const MANAGED_KEYS = [
  'GEMINI_API_KEY',
  'JARVIS_TTS_VOICE',
  'JARVIS_GEMINI_MODEL',
  'JARVIS_WEATHER_LOCATION',
  'JARVIS_REPORT_PROJECTS',
  'JARVIS_MODE',
];

function parseEnvFile(text) {
  const values = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1);
    values[key] = value;
  }
  return values;
}

function updateEnvFile(text, updates) {
  const lines = text.length ? text.split(/\r?\n/) : [];
  const seen = new Set();
  const outLines = lines.map((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return line;
    const eq = trimmed.indexOf('=');
    if (eq === -1) return line;
    const key = trimmed.slice(0, eq).trim();
    if (Object.prototype.hasOwnProperty.call(updates, key)) {
      seen.add(key);
      return `${key}=${updates[key]}`;
    }
    return line;
  });
  for (const [key, value] of Object.entries(updates)) {
    if (!seen.has(key)) outLines.push(`${key}=${value}`);
  }
  return outLines.join('\n');
}

function readSettings(envPath) {
  let text = '';
  try {
    text = fs.readFileSync(envPath, 'utf-8');
  } catch (err) {
    text = '';
  }
  const values = parseEnvFile(text);
  const settings = {};
  for (const key of MANAGED_KEYS) {
    settings[key] = values[key] || '';
  }
  return settings;
}

function writeSettings(envPath, updates) {
  let text = '';
  try {
    text = fs.readFileSync(envPath, 'utf-8');
  } catch (err) {
    text = '';
  }
  const newText = updateEnvFile(text, updates);
  fs.writeFileSync(envPath, newText, 'utf-8');
}

function resolveEnvPath({ isPackaged, userDataPath, projectRoot }) {
  return isPackaged
    ? path.join(userDataPath, '.env')
    : path.join(projectRoot, 'agent', '.env');
}

module.exports = { MANAGED_KEYS, parseEnvFile, updateEnvFile, readSettings, writeSettings, resolveEnvPath };
