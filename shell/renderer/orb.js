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
