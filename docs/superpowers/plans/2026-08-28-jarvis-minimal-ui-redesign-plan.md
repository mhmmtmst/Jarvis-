# Jarvis Minimal UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Jarvis's "sci-fi HUD" visual identity (neon cyan/black, bracket-cornered panels, ALL-CAPS English labels, particle orb, radar-scan background) with a calm, dark-neutral + single-accent minimal identity, without touching layout structure, widget set, or any functional/JS behavior beyond the display strings themselves.

**Architecture:** Three independent, sequential tasks against `shell/renderer/`: (1) CSS token/component overhaul + removal of the ambient background effect, (2) simplification of the animated orb's drawing to a single breathing gradient circle while preserving its public interface and state-driven behavior, (3) Turkish/sentence-case copy across static and dynamic UI text, restructuring the conversation log into a row-list with speaker labels, and removing a redundant duplicate wordmark element. No WebSocket protocol, state machine, or settings logic changes anywhere in this plan.

**Tech Stack:** Vanilla JS (no framework), CSS custom properties, HTML5 Canvas 2D, Node's built-in test runner (`node:test`).

## Global Constraints

- **Scope is visual identity only.** The 3-column grid (`.hud-grid`: 260px / 1fr / 420px), widget set, window size, WebSocket protocol, and state machine in `shell/renderer/renderer.js` do not change beyond the display-string edits explicitly listed in Task 3.
- **Color tokens** (exact values, from the approved design spec `docs/superpowers/specs/2026-08-27-jarvis-minimal-ui-redesign-design.md`):
  `--bg:#121214`, `--panel-bg:#1a1a1d`, `--panel-border:#26262a`, `--pri:#6b6bf5`, `--text:#e4e4e7`, `--text-dim:#9a9aa2`, `--text-faint:#6a6a72`, `--green:#6b6bf5` (idle/listening — same as accent), `--gold:#d9b46a` (thinking), `--org:#d9b46a` (bar warning — reuses the thinking amber, one fewer hue in the palette), `--blue:#7ec8e3` (speaking), `--red:#e2685f` (error). The old `--mid`/`--dim`/`--dimmer`/`--org2`/`--muted` tokens are deleted; every call site that referenced them is migrated to one of the tokens above (mapping is given inline in Task 1).
- **Font:** system sans-serif stack `-apple-system, 'Segoe UI', system-ui, sans-serif` everywhere; the `Rajdhani` Google Fonts `@import` is deleted. No more ALL-CAPS via `text-transform: uppercase` on dynamic state text.
- **`orb.js`'s public interface does not change its two call sites in `renderer.js`** (`new window.OrbRenderer(canvas)`, `orbRenderer.setState(state)`, `orbRenderer.setPaused(paused)`). `setUserSpeaking` is dropped — grepping `renderer.js` confirms it is never called (dead code); this plan removes it rather than preserving an unreachable branch.
- **Existing tests must stay green.** After every task, run `node --test` from `shell/` and confirm the full suite (currently 42 tests across `protocol.test.js`, `settings.test.js`, `agent-process.test.js`) still passes, plus any new tests this plan adds.
- **No new automated visual/DOM test infrastructure** (no jsdom). Per the spec's Test Strategy, only newly-introduced *pure* logic (orb color/motion selection, state-label translation) gets unit tests; inline `textContent = '...'` string changes are verified by manual run (`npm start`) at the end, not by new test infra — this is a deliberate, spec-mandated scope boundary, not a gap.
- All commit messages are in this repo's existing style (short, imperative, Turkish or English mixed as seen in `git log` — follow whichever the implementer finds already in recent commits).

---

## Task 1: Renk paleti, tipografi, panel/buton şekli ve arka plan kaldırma

**Files:**
- Modify: `shell/renderer/styles.css` (full-file replacement — see Step 3)
- Modify: `shell/renderer/index.html:9` (remove `<canvas id="bg-canvas"></canvas>`)
- Modify: `shell/renderer/index.html:165` (remove `<script src="bg.js"></script>`)
- Modify: `shell/renderer/renderer.js:73` (remove the `bgRenderer` line)
- Delete: `shell/renderer/bg.js`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the full set of CSS custom properties listed in Global Constraints, available to Tasks 2 and 3. `.hud-panel`, `.control-btn`, `.status-pill`, `.command-form input` all get `border-radius` and flat (non-gradient, non-glow) styling that Task 3's new `.log-line`/`.log-speaker`/`.log-text` classes (introduced in Task 3) will visually match.

This task has no new application logic — it is a CSS/markup-deletion task. There is no failing-test step; verification is the existing suite staying green plus a visual smoke check.

- [ ] **Step 1: Confirm current test baseline**

Run: `cd shell && node --test`
Expected: all current tests pass (42 tests at time of writing). Note the count — Step 5 must match or exceed it.

- [ ] **Step 2: Remove the background canvas from the page**

In `shell/renderer/index.html`, delete line 9:
```html
  <canvas id="bg-canvas"></canvas>
```
and delete the script tag near the bottom of the file:
```html
  <script src="bg.js"></script>
```

- [ ] **Step 3: Replace `shell/renderer/styles.css` with the new minimal stylesheet**

Delete `shell/renderer/bg.js` (the file is removed entirely — no script references it anymore after Step 2).

Replace the full content of `shell/renderer/styles.css` with:

```css
:root {
  --bg: #121214;
  --panel-bg: #1a1a1d;
  --panel-border: #26262a;
  --pri: #6b6bf5;
  --text: #e4e4e7;
  --text-dim: #9a9aa2;
  --text-faint: #6a6a72;
  --green: #6b6bf5;
  --gold: #d9b46a;
  --org: #d9b46a;
  --blue: #7ec8e3;
  --red: #e2685f;

  --state-color: var(--green);
}

* { box-sizing: border-box; }

html, body {
  margin: 0;
  height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, 'Segoe UI', system-ui, sans-serif;
  overflow: hidden;
}

.display-font {
  font-family: -apple-system, 'Segoe UI', system-ui, sans-serif;
  font-weight: 600;
}

.hud-top, .hud-grid, .hud-controls {
  position: relative;
  z-index: 1;
}

.hud-top { display: flex; justify-content: flex-end; align-items: center; padding: 12px 24px; gap: 10px; }

.status-pill {
  border: 1px solid var(--panel-border);
  color: var(--text-dim);
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 11px;
  letter-spacing: 0.3px;
  font-weight: 500;
  transition: color 0.3s ease, border-color 0.3s ease;
}
.status-pill.online { color: var(--green); border-color: var(--green); }
.status-pill.error { color: var(--red); border-color: var(--red); }

.hud-grid {
  display: grid;
  grid-template-columns: 260px 1fr 420px;
  gap: 14px;
  padding: 0 24px;
  height: calc(100% - 60px);
}

.hud-panel {
  position: relative;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 10px;
  padding: 18px 16px 16px;
  overflow: hidden;
}

.hud-left { display: flex; flex-direction: column; gap: 14px; }
.hud-left .widget-system { flex: 1; }

.panel-title {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
  color: var(--text-dim);
  margin: 0 0 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--panel-border);
}

.clock-time {
  font-size: 40px;
  font-weight: 600;
  color: var(--text);
}
.clock-date { font-size: 11px; opacity: 0.75; letter-spacing: 0.3px; color: var(--text-dim); margin-top: 4px; }

.bar-row { display: flex; align-items: center; gap: 8px; font-size: 11px; margin-bottom: 9px; }
.bar-row span:first-child { color: var(--text-dim); width: 46px; flex-shrink: 0; }
.bar { flex: 1; height: 6px; background: var(--bg); border-radius: 3px; overflow: hidden; }
.bar-fill { height: 100%; width: 0%; background: var(--pri); transition: width 0.4s ease, background 0.3s ease; }
.bar-pct { width: 34px; text-align: right; opacity: 0.9; font-variant-numeric: tabular-nums; color: var(--pri); }

.bar-row.warn .bar-fill { background: var(--org); }
.bar-row.crit .bar-fill { background: var(--red); }
.bar-row.warn .bar-pct { color: var(--org); }
.bar-row.crit .bar-pct { color: var(--red); }

.hud-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  position: relative;
}

.hero-title {
  position: absolute;
  top: 4px;
  left: 50%;
  transform: translateX(-50%);
  text-align: center;
}
.hero-wordmark {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--text);
}
.hero-tagline {
  font-size: 11px;
  letter-spacing: 0.3px;
  color: var(--text-faint);
  margin-top: 4px;
}

.orb-wrap {
  width: 560px;
  height: 560px;
  position: relative;
  margin-top: 40px;
}
#orb-canvas { width: 100%; height: 100%; display: block; }

.wordmark {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--state-color);
  transition: color 0.4s ease;
}
.agent-state {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.3px;
  opacity: 0.85;
  color: var(--state-color);
  transition: color 0.4s ease;
}

.hud-right { display: flex; flex-direction: column; }
.hud-right .panel-title { margin-bottom: 0; border-bottom: none; padding-bottom: 0; }

.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--panel-border);
  margin-bottom: 10px;
}

.wave-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 18px;
}
.wave-bars span {
  width: 2px;
  height: 3px;
  background: var(--text-faint);
  transition: height 0.12s ease, background 0.3s ease;
}
.wave-bars.active span { background: var(--pri); }
.conversation-log { flex: 1; overflow-y: auto; font-size: 13px; display: flex; flex-direction: column; gap: 8px; padding-right: 4px; }
.conversation-log .entry-user { color: var(--text); }
.conversation-log .entry-jarvis { color: var(--pri); }
.conversation-log .entry-error { color: var(--red); }

.command-form { display: flex; gap: 8px; margin-top: 12px; }
.command-form input {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--panel-border);
  color: var(--text);
  padding: 8px 10px;
  border-radius: 8px;
  font-family: inherit;
  transition: border-color 0.2s ease;
}
.command-form input:focus {
  outline: none;
  border-color: var(--pri);
}

.command-form button, .control-btn {
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  color: var(--text-dim);
  padding: 8px 14px;
  border-radius: 8px;
  font-weight: 500;
  letter-spacing: 0.3px;
  cursor: pointer;
  transition: border-color 0.2s ease, color 0.2s ease, background 0.2s ease, transform 0.1s ease;
}
.command-form button:hover, .control-btn:hover {
  border-color: var(--text-faint);
  background: #202024;
}
.command-form button:active, .control-btn:active {
  transform: translateY(1px);
}
.control-btn.control-danger { border-color: color-mix(in srgb, var(--red) 40%, var(--panel-border)); color: var(--red); }

.hud-controls { display: flex; justify-content: center; gap: 12px; margin-top: 6px; }
.hud-controls .control-btn { padding: 6px 12px; font-size: 11px; }

.control-live {
  border-color: var(--green);
  color: var(--green);
  cursor: default;
  display: inline-flex;
  align-items: center;
}
.control-live.offline { border-color: var(--red); color: var(--red); }

.btn-icon {
  display: inline-flex;
  align-items: center;
  margin-right: 7px;
  flex-shrink: 0;
}
.control-live .btn-icon { animation: icon-pulse 1.6s ease-in-out infinite; }
.control-live.offline .btn-icon { animation: none; }

@keyframes icon-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.weather-placeholder {
  font-size: 11px;
  color: var(--text-faint);
  font-style: italic;
  padding: 8px 0;
}

.weather-temp {
  font-size: 30px;
  font-weight: 600;
  color: var(--text);
}
.weather-city {
  font-size: 10px;
  letter-spacing: 0.3px;
  color: var(--text-dim);
  margin-top: 2px;
  text-transform: uppercase;
}
.weather-condition {
  font-size: 12px;
  color: var(--text);
  margin-top: 6px;
}
.weather-detail {
  font-size: 11px;
  color: var(--text);
  opacity: 0.8;
  margin-top: 3px;
}

.wake-indicator {
  opacity: 0.3;
  font-size: 0.7rem;
  letter-spacing: 0.05em;
  margin-left: 0.75rem;
  color: var(--green);
  transition: opacity 0.2s ease;
}
.wake-indicator.active {
  opacity: 1;
}

/* Durum -> renk. hud-center'a yazilir, wordmark/agent-state buradan
   miras alir (orb.js kendi ayri paletiyle canvas'i cizer). */
#hud-center[data-state="idle"] { --state-color: var(--green); }
#hud-center[data-state="listening"] { --state-color: var(--green); }
#hud-center[data-state="thinking"] { --state-color: var(--gold); }
#hud-center[data-state="speaking"] { --state-color: var(--blue); }
#hud-center[data-state="error"] { --state-color: var(--red); }

.debug-toggle {
  margin-left: 12px;
  background: transparent;
  border: 1px solid var(--panel-border);
  color: var(--text-dim);
  border-radius: 6px;
  font-size: 11px;
  padding: 3px 8px;
  cursor: pointer;
  letter-spacing: 0.05em;
}

.debug-panel {
  position: fixed;
  top: 48px;
  right: 16px;
  width: 420px;
  height: 320px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 10px;
  z-index: 50;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.debug-panel.hidden {
  display: none;
}

.debug-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid var(--panel-border);
  font-size: 11px;
  letter-spacing: 0.05em;
}

.debug-panel-header button {
  background: transparent;
  border: 1px solid var(--panel-border);
  color: inherit;
  cursor: pointer;
  border-radius: 6px;
  font-size: 10px;
  padding: 2px 6px;
  margin-left: 6px;
}

.debug-log {
  flex: 1;
  overflow-y: auto;
  padding: 8px 10px;
  font-family: 'Consolas', 'Cascadia Code', monospace;
  font-size: 11px;
  white-space: pre-wrap;
}

.debug-log-line.stderr {
  color: var(--red);
}

.debug-log-line.status {
  color: var(--gold);
}

.debug-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.debug-body.hidden,
.settings-body.hidden,
#debug-restart.hidden {
  display: none;
}

.debug-panel-header .debug-tabs {
  display: flex;
  gap: 6px;
}

.debug-panel-header .debug-tab {
  background: transparent;
  border: 1px solid var(--panel-border);
  color: var(--text-dim);
  border-radius: 6px;
  font-size: 10px;
  padding: 3px 10px;
  cursor: pointer;
  letter-spacing: 0.05em;
}

.debug-panel-header .debug-tab.active {
  color: var(--pri);
  border-color: var(--pri);
}

.settings-body {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.settings-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--text-dim);
}

.settings-field input,
.settings-field select {
  background: var(--bg);
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  color: var(--text);
  padding: 4px 6px;
  font-size: 12px;
}

.settings-checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-dim);
}

.settings-save-btn {
  background: transparent;
  border: 1px solid var(--pri);
  border-radius: 8px;
  color: var(--pri);
  padding: 6px 10px;
  cursor: pointer;
  font-size: 11px;
  letter-spacing: 0.05em;
}

.settings-firstrun-note {
  font-size: 11px;
  color: var(--gold);
  line-height: 1.5;
}

.settings-version-row {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-faint);
  letter-spacing: 0.05em;
}

.settings-firstrun-note.hidden {
  display: none;
}

.debug-tabs .debug-tab.hidden {
  display: none;
}

#debug-close.hidden {
  display: none;
}
```

- [ ] **Step 4: Remove the background renderer instantiation**

In `shell/renderer/renderer.js`, delete line 73:
```js
const bgRenderer = new window.BackgroundRenderer(document.getElementById('bg-canvas'));
```
(Leave line 74, `const orbRenderer = new window.OrbRenderer(...)`, untouched.)

- [ ] **Step 5: Run the full test suite**

Run: `cd shell && node --test`
Expected: same test count as Step 1, all passing (this task changes no logic, only CSS/markup deletions).

- [ ] **Step 6: Commit**

```bash
git add shell/renderer/styles.css shell/renderer/index.html shell/renderer/renderer.js
git rm shell/renderer/bg.js
git commit -m "feat(shell): minimal koyu-notr renk paleti, duz panel/buton stili, arka plan efektini kaldir"
```

---

## Task 2: Orb'u tek nefes alan küreye sadeleştir

**Files:**
- Modify: `shell/renderer/orb.js` (full-file replacement)
- Create: `shell/renderer/orb.test.js`

**Interfaces:**
- Consumes: nothing from Task 1 (orb.js draws its own colors independent of CSS tokens, per the existing codebase's separation — see the comment already in `styles.css` above `#hud-center[data-state=...]`).
- Produces: `orbColorForState(state, paused) -> [r, g, b]` and `orbMotionTarget(state, { paused, speaking }) -> { scale: [min, max], halo: [min, max] }`, both exported via `module.exports` in Node and `window.orbColorForState` / `window.orbMotionTarget` in the browser (same dual-export pattern as `shell/renderer/protocol.js`). `OrbRenderer` keeps its existing browser-only public interface: `new OrbRenderer(canvas)`, `.setState(state)`, `.setPaused(paused)`. `setUserSpeaking` is removed (confirmed unused — see Global Constraints).

- [ ] **Step 1: Write the failing tests for the pure orb-decision functions**

Create `shell/renderer/orb.test.js`:

```js
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && node --test orb.test.js` (run from `shell/renderer/` or point at the full relative path `shell/renderer/orb.test.js` from `shell/` — either works since `node --test` accepts a file path)
Expected: FAIL — `Cannot find module './orb'` or `orbColorForState is not a function`, because `orb.js` does not export these yet.

- [ ] **Step 3: Replace `shell/renderer/orb.js` with the simplified implementation**

```js
// Jarvis orb — tek nefes alan gradyan küre.
// Rengi (ORB_COLORS) ve hedef ölçek/glow'u (MOTION_TARGETS) belirleyen
// mantık saf fonksiyonlara ayrıldı ki DOM/canvas olmadan test edilebilsin;
// çizimin kendisi (OrbRenderer._draw) tarayıcıda çalışır, otomatik test
// edilmez (bkz. plan Global Constraints — kapsamlı DOM test altyapısı yok).

const ORB_COLORS = {
  idle: [107, 107, 245],
  listening: [107, 107, 245],
  thinking: [217, 180, 106],
  speaking: [126, 200, 227],
  error: [226, 104, 95],
  paused: [85, 85, 92],
};

function orbColorForState(state, paused) {
  if (paused) return ORB_COLORS.paused;
  return ORB_COLORS[state] || ORB_COLORS.idle;
}

const MOTION_TARGETS = {
  paused: { scale: [0.6, 0.64], halo: [4, 8] },
  speaking: { scale: [0.98, 1.08], halo: [70, 100] },
  thinking: { scale: [0.82, 0.88], halo: [45, 60] },
  default: { scale: [0.74, 0.8], halo: [18, 28] },
};

function orbMotionTarget(state, { paused, speaking }) {
  if (paused) return MOTION_TARGETS.paused;
  if (speaking) return MOTION_TARGETS.speaking;
  if (state === 'thinking') return MOTION_TARGETS.thinking;
  return MOTION_TARGETS.default;
}

function rand(min, max) {
  return min + Math.random() * (max - min);
}

class OrbRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.state = 'idle';
    this.speaking = false;
    this.paused = false;

    this.tick = 0;
    this.scale = 0.74;
    this.targetScale = 0.74;
    this.halo = 18;
    this.targetHalo = 18;
    this.lastTargetAt = 0;

    this._resize();
    window.addEventListener('resize', () => this._resize());
    this._raf = requestAnimationFrame(() => this._loop());
  }

  setState(state) {
    this.state = state;
    this.speaking = state === 'speaking';
  }

  setPaused(paused) {
    this.paused = paused;
  }

  _resize() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = rect.width;
    this.h = rect.height;
    this.cx = this.w / 2;
    this.cy = this.h / 2;
    this.faceR = Math.min(140, Math.min(this.w, this.h) * 0.34);
  }

  _step() {
    this.tick += 1;
    const now = performance.now() / 1000;

    if (now - this.lastTargetAt > (this.speaking ? 0.15 : 0.6)) {
      const target = orbMotionTarget(this.state, { paused: this.paused, speaking: this.speaking });
      this.targetScale = rand(target.scale[0], target.scale[1]);
      this.targetHalo = rand(target.halo[0], target.halo[1]);
      this.lastTargetAt = now;
    }

    const sp = this.speaking ? 0.3 : 0.15;
    this.scale += (this.targetScale - this.scale) * sp;
    this.halo += (this.targetHalo - this.halo) * sp;
  }

  _loop() {
    this._step();
    this._draw();
    this._raf = requestAnimationFrame(() => this._loop());
  }

  _draw() {
    const { ctx, w, h, cx, cy, tick } = this;
    ctx.clearRect(0, 0, w, h);

    const [R, G, B] = orbColorForState(this.state, this.paused);
    const breathe = 1.0 + 0.03 * Math.sin(tick * 0.04);
    const r = this.faceR * this.scale * breathe;

    ctx.save();
    ctx.shadowColor = `rgba(${R}, ${G}, ${B}, 0.5)`;
    ctx.shadowBlur = this.halo;

    const gradient = ctx.createRadialGradient(cx - r * 0.3, cy - r * 0.3, r * 0.05, cx, cy, r);
    gradient.addColorStop(0, `rgba(${Math.min(255, R + 40)}, ${Math.min(255, G + 40)}, ${Math.min(255, B + 40)}, 1)`);
    gradient.addColorStop(1, `rgba(${Math.round(R * 0.55)}, ${Math.round(G * 0.55)}, ${Math.round(B * 0.55)}, 1)`);

    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = gradient;
    ctx.fill();
    ctx.restore();
  }
}

if (typeof module === 'object' && module.exports) {
  module.exports = { orbColorForState, orbMotionTarget };
} else {
  window.OrbRenderer = OrbRenderer;
  window.orbColorForState = orbColorForState;
  window.orbMotionTarget = orbMotionTarget;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && node --test`
Expected: all tests pass, including the 12 new orb tests.

- [ ] **Step 5: Commit**

```bash
git add shell/renderer/orb.js shell/renderer/orb.test.js
git commit -m "feat(shell): orb'u halka/parcacik sisteminden tek nefes alan kureye sadelestir"
```

---

## Task 3: Metin/dil Türkçeleştirmesi, konuşma paneli satır-listesi, tekrarlayan wordmark'ı kaldırma

**Files:**
- Create: `shell/renderer/state-labels.js`
- Create: `shell/renderer/state-labels.test.js`
- Modify: `shell/renderer/index.html`
- Modify: `shell/renderer/renderer.js`
- Modify: `shell/renderer/styles.css`

**Interfaces:**
- Consumes: `.hud-panel`, `.panel-border`-based flat button/input styling from Task 1 (no direct code dependency, just visual consistency).
- Produces: `describeAgentState(state) -> string` (Turkish display label), exported the same dual way as `orb.js`/`protocol.js`. `appendLog(kind, text)` in `renderer.js` now builds a `.log-line > .log-speaker + .log-text` structure instead of a single flat `div.entry-*`.

- [ ] **Step 1: Write the failing tests for the state-label translator**

Create `shell/renderer/state-labels.test.js`:

```js
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && node --test state-labels.test.js`
Expected: FAIL — `Cannot find module './state-labels'`.

- [ ] **Step 3: Create `shell/renderer/state-labels.js`**

```js
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.jarvisStateLabels = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  const AGENT_STATE_LABELS = {
    idle: 'boşta',
    listening: 'dinliyor',
    thinking: 'düşünüyor',
    speaking: 'konuşuyor',
    error: 'hata',
  };

  function describeAgentState(state) {
    return AGENT_STATE_LABELS[state] || state;
  }

  return { AGENT_STATE_LABELS, describeAgentState };
});
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && node --test`
Expected: all tests pass, including the 6 new state-label tests.

- [ ] **Step 5: Wire `state-labels.js` into the page and use it in `setAgentState`**

In `shell/renderer/index.html`, add the script tag right before `renderer.js` (after `orb.js`):
```html
  <script src="protocol.js"></script>
  <script src="bg.js"></script>
  <script src="orb.js"></script>
  <script src="renderer.js"></script>
```
becomes (note `bg.js` is already gone from Task 1 — the block should read):
```html
  <script src="protocol.js"></script>
  <script src="orb.js"></script>
  <script src="state-labels.js"></script>
  <script src="renderer.js"></script>
```

In `shell/renderer/renderer.js`, replace:
```js
function setAgentState(state) {
  hudCenter.dataset.state = state;
  agentStateEl.textContent = state;
  orbRenderer.setState(state);
}
```
with:
```js
function setAgentState(state) {
  hudCenter.dataset.state = state;
  agentStateEl.textContent = window.jarvisStateLabels.describeAgentState(state);
  orbRenderer.setState(state);
}
```

- [ ] **Step 6: Restructure the conversation log into a row-list with speaker labels**

In `shell/renderer/renderer.js`, replace:
```js
function appendLog(kind, text) {
  const line = document.createElement('div');
  line.className = `entry-${kind}`;
  line.textContent = text;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}
```
with:
```js
function appendLog(kind, text) {
  const line = document.createElement('div');
  line.className = `log-line entry-${kind}`;

  const speaker = document.createElement('div');
  speaker.className = 'log-speaker';
  speaker.textContent = kind === 'user' ? 'sen' : kind === 'error' ? 'hata' : 'jarvis';

  const body = document.createElement('div');
  body.className = 'log-text';
  body.textContent = text;

  line.appendChild(speaker);
  line.appendChild(body);
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}
```

In `shell/renderer/styles.css`, replace:
```css
.conversation-log { flex: 1; overflow-y: auto; font-size: 13px; display: flex; flex-direction: column; gap: 8px; padding-right: 4px; }
.conversation-log .entry-user { color: var(--text); }
.conversation-log .entry-jarvis { color: var(--pri); }
.conversation-log .entry-error { color: var(--red); }
```
with:
```css
.conversation-log { flex: 1; overflow-y: auto; font-size: 13px; display: flex; flex-direction: column; padding-right: 4px; }
.log-line { padding: 8px 0; border-bottom: 1px solid var(--panel-border); }
.log-line:last-child { border-bottom: none; }
.log-speaker { font-size: 10px; color: var(--text-faint); margin-bottom: 3px; }
.log-line.entry-user .log-speaker { color: var(--pri); }
.log-text { color: var(--text); }
.log-line.entry-error .log-text { color: var(--red); }
```

- [ ] **Step 7: Translate/decapitalize the remaining dynamic strings in `renderer.js`**

Replace:
```js
socket.addEventListener('open', () => {
  statusEl.textContent = 'ONLINE';
  statusEl.classList.add('online');
  statusEl.classList.remove('error');
  liveBadge.classList.remove('offline');
  sendBrowserLocation();
});
socket.addEventListener('close', () => {
  statusEl.textContent = 'CONNECTING';
  statusEl.classList.remove('online');
  liveBadge.classList.add('offline');
});
socket.addEventListener('error', () => {
  statusEl.textContent = 'CONNECTING';
  statusEl.classList.remove('online');
  statusEl.classList.add('error');
  liveBadge.classList.add('offline');
});
```
with:
```js
socket.addEventListener('open', () => {
  statusEl.textContent = 'bağlandı';
  statusEl.classList.add('online');
  statusEl.classList.remove('error');
  liveBadge.classList.remove('offline');
  sendBrowserLocation();
});
socket.addEventListener('close', () => {
  statusEl.textContent = 'bağlanıyor';
  statusEl.classList.remove('online');
  liveBadge.classList.add('offline');
});
socket.addEventListener('error', () => {
  statusEl.textContent = 'bağlantı hatası';
  statusEl.classList.remove('online');
  statusEl.classList.add('error');
  liveBadge.classList.add('offline');
});
```

Replace:
```js
pauseBtn.addEventListener('click', () => {
  paused = !paused;
  pauseBtn.textContent = paused ? 'RESUME' : 'PAUSE';
  orbRenderer.setPaused(paused);
});
```
with:
```js
pauseBtn.addEventListener('click', () => {
  paused = !paused;
  pauseBtn.textContent = paused ? 'devam et' : 'duraklat';
  orbRenderer.setPaused(paused);
});
```

- [ ] **Step 8: Translate/decapitalize the static labels in `index.html` and remove the duplicate wordmark**

Replace:
```html
    <span id="connection-status" class="status-pill">CONNECTING</span>
    <span id="wake-indicator" class="wake-indicator">ASİSTAN DİNLİYOR</span>
```
with:
```html
    <span id="connection-status" class="status-pill">bağlanıyor</span>
    <span id="wake-indicator" class="wake-indicator">asistan dinliyor</span>
```

Replace each panel title:
- `<h2 class="panel-title">TIME</h2>` → `<h2 class="panel-title">Saat</h2>`
- `<h2 class="panel-title">WEATHER</h2>` → `<h2 class="panel-title">Hava durumu</h2>`
- `<h2 class="panel-title">SYSTEM STATUS</h2>` → `<h2 class="panel-title">Sistem</h2>`
- `<h2 class="panel-title">CONVERSATION</h2>` → `<h2 class="panel-title">Konuşma</h2>`

Replace:
```html
      <div class="hero-title">
        <div class="hero-wordmark">J.A.R.V.I.S</div>
        <div class="hero-tagline">YAPAY ZEKA SES ASİSTANI</div>
      </div>
      <div class="orb-wrap">
        <canvas id="orb-canvas"></canvas>
      </div>
      <div class="wordmark">J.A.R.V.I.S</div>
      <div id="agent-state" class="agent-state">idle</div>
```
with:
```html
      <div class="hero-title">
        <div class="hero-wordmark">Jarvis</div>
        <div class="hero-tagline">yapay zeka ses asistanı</div>
      </div>
      <div class="orb-wrap">
        <canvas id="orb-canvas"></canvas>
      </div>
      <div id="agent-state" class="agent-state">boşta</div>
```

(This also removes the `.wordmark` div — it duplicated the hero title with no functional purpose; confirmed via grep that no JS reads or writes `.wordmark`.)

In `shell/renderer/styles.css`, delete the now-unused rule (the `.wordmark` div no longer exists in the markup):
```css
.wordmark {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--state-color);
  transition: color 0.4s ease;
}
```

Replace the LIVE/PAUSE/SHUTDOWN button labels:
```html
          </span>LIVE
        </span>
```
with:
```html
          </span>canlı
        </span>
```
```html
          </span>PAUSE
        </button>
```
with:
```html
          </span>duraklat
        </button>
```
```html
          </span>SHUTDOWN
        </button>
```
with:
```html
          </span>kapat
        </button>
```

Replace:
```html
        <button type="submit">SEND</button>
```
with:
```html
        <button type="submit">Gönder</button>
```

- [ ] **Step 9: Run the full test suite**

Run: `cd shell && node --test`
Expected: all tests pass (42 pre-existing + 6 new state-label + 12 new orb = 60 total; exact pre-existing count should match Task 1 Step 1's baseline).

- [ ] **Step 10: Manual visual check**

Run `npm start` from `shell/` (requires a configured `.env` — see `shell/.env`/`agent/.env.example`; if no `GEMINI_API_KEY` is available, the window still opens and every static label, panel title, button text, and the idle orb can be checked without a live connection). Confirm:
- No English ALL-CAPS labels remain outside the DEBUG/SETTINGS panel (out of scope, per spec).
- Only one "Jarvis" wordmark is visible above the orb.
- The conversation log (type a command via the text input, which works without a live agent connection failing — it will just not get a response) shows a speaker label above each line with a thin separator.
- The orb still changes color/breathing speed between idle and (if reachable) other states.

- [ ] **Step 11: Commit**

```bash
git add shell/renderer/state-labels.js shell/renderer/state-labels.test.js shell/renderer/index.html shell/renderer/renderer.js shell/renderer/styles.css
git commit -m "feat(shell): arayuz metinlerini turkcelestir, konusma panelini satir-listesine cevir, tekrar eden wordmark'i kaldir"
```
