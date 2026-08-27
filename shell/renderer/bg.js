// Arka plan ambient katmani: nokta izgarasi, yavas tarama cizgisi, surukleyen
// parcaciklar — ui.py'nin _draw() arka plan bolumunun canvas portu.

function bgRand(min, max) {
  return min + Math.random() * (max - min);
}

class BackgroundRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.tick = 0;
    this.particles = Array.from({ length: 24 }, () => ({
      x: 0,
      y: 0,
      vx: bgRand(-0.15, 0.15),
      vy: bgRand(-0.15, 0.15),
      r: bgRand(0.5, 1.8),
      a: bgRand(15, 70),
    }));
    this._resize();
    window.addEventListener('resize', () => this._resize());
    requestAnimationFrame(() => this._loop());
  }

  _resize() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = rect.width;
    this.h = rect.height;
    this.particles.forEach((p) => {
      p.x = bgRand(0, this.w);
      p.y = bgRand(0, this.h);
    });
  }

  _loop() {
    this.tick += 1;
    this._draw();
    requestAnimationFrame(() => this._loop());
  }

  _draw() {
    const { ctx, w, h, tick } = this;
    ctx.clearRect(0, 0, w, h);

    if (tick % 3 === 0) {
      ctx.fillStyle = '#061414';
      const step = 72;
      for (let x = 0; x < w; x += step) {
        for (let y = 0; y < h; y += step) {
          ctx.fillRect(x, y, 1, 1);
        }
      }
    }

    const scanY = (tick * 0.7) % (h + 60) - 30;
    ctx.strokeStyle = '#081818';
    ctx.lineWidth = 1;
    for (let i = 0; i < 2; i++) {
      const ly = (scanY + i * 20) % h;
      ctx.beginPath();
      ctx.moveTo(0, ly);
      ctx.lineTo(w, ly + 35);
      ctx.stroke();
    }

    for (const p of this.particles) {
      p.x = (p.x + p.vx + w) % w;
      p.y = (p.y + p.vy + h) % h;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0, 255, 136, ${(p.a / 255).toFixed(3)})`;
      ctx.fill();
    }
  }
}

window.BackgroundRenderer = BackgroundRenderer;
