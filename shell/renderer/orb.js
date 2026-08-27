// J.A.R.V.I.S orb — eslikli parcacik sistemi.
// alpunlu12-commits/jarvis (Acik Kaynak etiketli) reposundaki ui.py'nin
// Tkinter Canvas ile cizdigi orb'un ayni animasyon mantigi (concentric
// halkalar, kabuk/parcacik alani, donen segment yaylar, pulse ring, nefes
// alma) HTML5 Canvas'a portlanmis hali — kod kopyalanmadi, sadece hareket/
// renk mantigi yeniden yazildi.

const ORB_COLORS = {
  idle: [0, 255, 136],
  listening: [0, 255, 136],
  thinking: [255, 204, 0],
  speaking: [68, 136, 255],
  error: [255, 51, 68],
  muted: [200, 30, 80],
  paused: [30, 60, 55],
};

const ACCENT_COLORS = {
  thinking: [255, 210, 72],
  speaking: [170, 220, 255],
  user_speaking: [118, 200, 255],
  default: [120, 255, 185],
};

function ac(r, g, b, a) {
  const f = Math.max(0, Math.min(255, a)) / 255;
  return `rgba(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)}, ${f.toFixed(3)})`;
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
    this.userSpeaking = false;
    this.paused = false;

    this.tick = 0;
    this.scale = 0.8;
    this.targetScale = 0.8;
    this.haloA = 55;
    this.targetHalo = 55;
    this.lastTargetAt = 0;
    this.ringsSpin = [0, 45, 90, 200];
    this.pulseR = [];

    this.orbParticles = Array.from({ length: 160 }, () => ({
      angle: rand(0, Math.PI * 2),
      orbit: rand(0.06, 0.98),
      speed: rand(-0.03, 0.03),
      size: rand(0.8, 2.8),
      phase: rand(0, Math.PI * 2),
      wobble: rand(0.01, 0.04),
      depth: rand(0.3, 1.0),
    }));
    this.shellParticles = Array.from({ length: 84 }, () => ({
      angle: rand(0, Math.PI * 2),
      speed: rand(-0.02, 0.02),
      size: rand(1.4, 3.8),
      phase: rand(0, Math.PI * 2),
      glow: rand(0.4, 1.0),
    }));

    this._resize();
    window.addEventListener('resize', () => this._resize());
    this._raf = requestAnimationFrame(() => this._loop());
  }

  setState(state) {
    this.state = state;
    this.speaking = state === 'speaking';
  }

  setUserSpeaking(active) {
    this.userSpeaking = active;
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
    // Orb'un kendi govdesi (parcacik alani, kabuk, yaylar) sabit bir boyutta
    // kalir; pulse ring'ler bundan bagimsiz, canvas'in tamamina yayilabilir —
    // boylece "sonar" halkalari cok daha genis bir alanda genisleyebiliyor.
    this.face = Math.min(320, Math.min(this.w, this.h) * 0.92);
    this.pulseLimit = Math.min(this.w, this.h) * 0.49;
  }

  _orbRgb() {
    const key = this.paused ? 'paused' : this.state;
    return ORB_COLORS[key] || ORB_COLORS.idle;
  }

  _accentRgb() {
    if (this.state === 'thinking') return ACCENT_COLORS.thinking;
    if (this.speaking) return ACCENT_COLORS.speaking;
    if (this.userSpeaking) return ACCENT_COLORS.user_speaking;
    return ACCENT_COLORS.default;
  }

  _step() {
    this.tick += 1;
    const now = performance.now() / 1000;

    if (now - this.lastTargetAt > (this.speaking ? 0.12 : 0.5)) {
      if (this.paused) {
        this.targetScale = rand(0.58, 0.64);
        this.targetHalo = rand(5, 10);
      } else if (this.speaking) {
        this.targetScale = rand(0.98, 1.1);
        this.targetHalo = rand(180, 250);
      } else if (this.userSpeaking) {
        this.targetScale = rand(0.88, 0.98);
        this.targetHalo = rand(120, 175);
      } else if (this.state === 'thinking') {
        this.targetScale = rand(0.8, 0.88);
        this.targetHalo = rand(95, 145);
      } else {
        this.targetScale = rand(0.72, 0.8);
        this.targetHalo = rand(34, 58);
      }
      this.lastTargetAt = now;
    }

    const sp = this.speaking ? 0.34 : 0.18;
    this.scale += (this.targetScale - this.scale) * sp;
    this.haloA += (this.targetHalo - this.haloA) * sp;

    const spds = this.paused
      ? [0, 0, 0, 0]
      : this.speaking
      ? [1.6, -1.1, 2.4, -0.7]
      : [0.55, -0.35, 0.9, -0.28];
    this.ringsSpin = this.ringsSpin.map((deg, i) => (deg + spds[i] * 0.6) % 360);

    const pspd = this.speaking ? 4.5 : 2.0;
    this.pulseR = this.pulseR.map((r) => r + pspd).filter((r) => r < this.pulseLimit);
    if (this.pulseR.length < 4 && Math.random() < (this.speaking ? 0.07 : 0.02)) {
      this.pulseR.push(0);
    }
  }

  _loop() {
    this._step();
    this._draw();
    this._raf = requestAnimationFrame(() => this._loop());
  }

  _draw() {
    const { ctx, w, h, cx, cy, tick } = this;
    ctx.clearRect(0, 0, w, h);

    const [R, G, B] = this._orbRgb();
    const ha = this.haloA;
    let speakPulse = 1.0;
    if (this.speaking) {
      speakPulse = 1.0 + 0.12 * Math.sin(tick * 0.14) + 0.05 * Math.sin(tick * 0.07 + 1.2);
    } else if (this.userSpeaking) {
      speakPulse = 1.0 + 0.06 * Math.sin(tick * 0.11 + 0.7);
    } else if (this.state === 'thinking') {
      speakPulse = 1.0 + 0.03 * Math.sin(tick * 0.06);
    } else {
      speakPulse = 1.0 + 0.01 * Math.sin(tick * 0.04);
    }

    const fw = this.face * this.scale * speakPulse;
    const fieldR = fw * 0.49;
    const innerR = fw * 0.34;
    const activity = this.paused
      ? 0.1
      : this.speaking
      ? 1.0
      : this.userSpeaking
      ? 0.78
      : this.state === 'thinking'
      ? 0.62
      : 0.26;
    const accentRgb = this._accentRgb();

    // Pulse rings — disariya dogru genisleyen sonar halkalari (orb'un
    // kendi govdesinden cok daha genis bir alana yayilir)
    for (const pr of this.pulseR) {
      const alpha = Math.max(0, 130 * (1 - pr / this.pulseLimit));
      const rr = pr + fieldR * 0.96;
      ctx.beginPath();
      ctx.arc(cx, cy, rr, 0, Math.PI * 2);
      ctx.strokeStyle = ac(R, G, B, alpha);
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Buyuk dis parilti
    if (!this.paused) {
      for (let i = 10; i >= 1; i--) {
        const frac = i / 10;
        const rr = fieldR * (1.02 + 0.045 * frac);
        const alpha = ha * 0.1 * frac;
        ctx.beginPath();
        ctx.arc(cx, cy, rr, 0, Math.PI * 2);
        ctx.strokeStyle = ac(R, G, B, alpha);
        ctx.lineWidth = 3;
        ctx.stroke();
      }
    }

    // Yapisal ic ice halkalar
    for (const [frac, width, alphaMult] of [
      [1.0, 2, 0.34],
      [0.9, 2, 0.24],
      [0.76, 1, 0.18],
      [0.62, 1, 0.12],
    ]) {
      const rr = fieldR * frac;
      ctx.beginPath();
      ctx.arc(cx, cy, rr, 0, Math.PI * 2);
      ctx.strokeStyle = ac(R, G, B, ha * alphaMult * (this.paused ? 0.4 : 1.0));
      ctx.lineWidth = width;
      ctx.stroke();
    }

    // Kabuk parcaciklari
    const shellPush = this.speaking ? 1.16 : this.userSpeaking ? 1.07 : 1.0;
    const shellR = fieldR * 0.93 * shellPush;
    this.shellParticles.forEach((sp, idx) => {
      const speedMult = this.speaking ? 2.8 : this.userSpeaking ? 1.6 : 1.1;
      const angle = sp.angle + tick * sp.speed * speedMult;
      const wobble = 1.0 + (this.speaking ? 0.07 : 0.035) * Math.sin(tick * 0.05 + sp.phase);
      const x = cx + Math.cos(angle) * shellR * wobble;
      const y = cy + Math.sin(angle) * shellR * wobble;
      const alpha = (70 + 120 * sp.glow) * (this.paused ? 0.26 : 0.52 + activity * 0.45);
      const useAccent = idx % 9 === 0 && !this.paused;
      const col = useAccent
        ? ac(accentRgb[0], accentRgb[1], accentRgb[2], Math.min(255, alpha + 30))
        : ac(R, G, B, alpha);
      const pr = sp.size * (1.0 + 0.24 * Math.sin(tick * 0.03 + sp.phase));
      ctx.beginPath();
      ctx.arc(x, y, pr, 0, Math.PI * 2);
      ctx.fillStyle = col;
      ctx.fill();
    });

    // Donen segment yaylar
    const arcR1 = fieldR * 0.96;
    const arcR2 = fieldR * 0.78;
    const arcs = [
      [this.ringsSpin[0], this.speaking ? 52 : 34, 3, false],
      [(this.ringsSpin[0] + 148) % 360, 26, 2, true],
      [(this.ringsSpin[2] + 28) % 360, this.userSpeaking ? 64 : 40, 3, false],
      [(this.ringsSpin[2] + 212) % 360, 18, 2, true],
    ];
    for (const [start, extentDeg, width, accent] of arcs) {
      const rr = width === 3 ? arcR1 : arcR2;
      const col = accent && !this.paused
        ? ac(accentRgb[0], accentRgb[1], accentRgb[2], 120 + 80 * activity)
        : ac(R, G, B, ha * (width === 3 ? 1.2 : 0.7));
      const startRad = (start * Math.PI) / 180;
      const endRad = ((start + extentDeg) * Math.PI) / 180;
      ctx.beginPath();
      ctx.arc(cx, cy, rr, startRad, endRad);
      ctx.strokeStyle = col;
      ctx.lineWidth = width;
      ctx.stroke();
    }

    // Yorunge parcacik alani
    const fieldLimit = innerR * (this.paused ? 0.82 : this.speaking ? 1.36 : this.userSpeaking ? 1.16 : 1.0);
    this.orbParticles.forEach((p, idx) => {
      const speedMult = this.paused ? 0.1 : this.speaking ? 3.1 : this.userSpeaking ? 2.0 : 1.1;
      const angle = p.angle + tick * p.speed * speedMult;
      const wobble = 1.0 + (this.speaking ? 0.3 : 0.18) * Math.sin(tick * p.wobble + p.phase);
      const orbit = fieldLimit * p.orbit * wobble;
      const depth = 0.5 + 0.5 * Math.sin(angle * 2.0 + tick * 0.008 + p.phase);
      const ySquash = 0.62 + depth * 0.38;
      const drift = (this.speaking ? 8.0 : this.userSpeaking ? 5.0 : 4.0) * p.depth;
      const x = cx + Math.cos(angle) * orbit + Math.sin(tick * 0.007 + p.phase) * drift;
      const y = cy + Math.sin(angle) * orbit * ySquash + Math.cos(tick * 0.006 + p.phase) * drift;
      let baseAlpha = (18 + 155 * p.depth) * (0.24 + activity * 0.86) * (0.45 + depth * 0.75);
      if (this.paused) baseAlpha *= 0.4;

      let col;
      if (idx % 11 === 0 && !this.paused) {
        col = ac(accentRgb[0], accentRgb[1], accentRgb[2], Math.min(255, baseAlpha + 25));
      } else if (this.userSpeaking && idx % 7 === 0) {
        col = ac(120, 205, 255, Math.min(255, baseAlpha + 20));
      } else {
        col = ac(R, G, B, baseAlpha);
      }
      const pr = p.size * (this.paused ? 0.7 : 0.9 + depth * 0.65 + 0.3 * activity * p.depth);
      ctx.beginPath();
      ctx.arc(x, y, pr, 0, Math.PI * 2);
      ctx.fillStyle = col;
      ctx.fill();

      if (idx % 18 === 0 && !this.paused) {
        ctx.beginPath();
        ctx.moveTo(cx + (x - cx) * 0.18, cy + (y - cy) * 0.18);
        ctx.lineTo(x, y);
        ctx.strokeStyle = ac(R, G, B, 18 + 35 * p.depth * activity);
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    });

    // Merkezdeki bosluk — orb'u mercek gibi degil hava gibi tutar
    const voidR = innerR * (this.paused ? 0.18 : 0.12);
    if (voidR > 0) {
      ctx.save();
      ctx.globalCompositeOperation = 'destination-out';
      ctx.beginPath();
      ctx.arc(cx, cy, voidR, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(0,0,0,1)';
      ctx.fill();
      ctx.restore();
    }
  }
}

window.OrbRenderer = OrbRenderer;
