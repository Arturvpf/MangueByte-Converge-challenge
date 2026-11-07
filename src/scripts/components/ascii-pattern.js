/**
 * Padrão ASCII animado ("Animated Pattern Background", script-012).
 *
 * Para cada célula de texto calcula um valor 0..1 a partir de dois centros
 * que orbitam (Lissajous) e escolhe um caractere do conjunto. A fórmula é a
 * do bundle; os parâmetros são os da instância da Home:
 *   characterSet: binary (" 01"), pattern: "3" (modo 2), easing: 0,
 *   frequencyA: 10, frequencyB: 20, centerASpeed: 30, centerBSpeed: 35,
 *   scale: 1.1, fonte 12px, cor rgba(255,255,255,.24), interval: .2s
 */

import { observeVisibility, prefersReducedMotion } from '../lib/dom.js';

const CHARSET = ' 01';
const PARAMS = {
  mode: 2, // pattern "3" -> {1:0, 2:1, 3:2}
  frequencyA: 10 / 100,
  frequencyB: 20 / 100,
  centerASpeed: 30 / 50,
  centerBSpeed: 35 / 50,
  scale: 1.1,
  fontSize: 12,
  color: 'rgba(255, 255, 255, 0.24)',
  intervalMs: 200,
};

/** Remapeia v de [a,b] para [c,d]. */
const remap = (v, a, b, c, d) => ((v - a) / (b - a)) * (d - c) + c;
const distance = (p, q) => Math.hypot(q[0] - p[0], q[1] - p[1]);

/** Curva de easing do componente: com easing 0 vira a identidade. */
const smooth = (t) => t;

function draw(ctx, canvas, time, charWidthRatio) {
  const { width: w, height: h } = canvas;
  const dpr = window.devicePixelRatio || 1;
  const fontPx = PARAMS.fontSize * PARAMS.scale * dpr;
  const lineHeight = fontPx; // lineHeight: 1em
  const charWidth = lineHeight * charWidthRatio;
  const minSide = Math.min(w, h);
  const aspect = w / h;

  const morphA = remap(Math.cos(time * PARAMS.frequencyA), -1, 1, 6, 60);
  const morphB = remap(Math.cos(time * PARAMS.frequencyB), -1, 1, 6, 60);
  const centerA = [Math.cos(time * 3 * PARAMS.centerASpeed) * 0.5, Math.sin(time * 7 * PARAMS.centerASpeed) * 0.5];
  const centerB = [Math.cos(time * 5 * PARAMS.centerBSpeed) * 0.5, Math.sin(time * 4 * PARAMS.centerBSpeed) * 0.5];

  ctx.clearRect(0, 0, w, h);
  ctx.font = `400 ${fontPx}px ${getComputedStyle(document.body).getPropertyValue('--font-mono')}`;
  ctx.textBaseline = 'top';
  ctx.fillStyle = PARAMS.color;

  for (let y = 0; y < h; y += lineHeight) {
    for (let x = 0; x < w; x += charWidth) {
      const px = Math.floor(x);
      const py = Math.floor(y);
      const p = [((2 * (px - w / 2)) / minSide) * aspect, (2 * (py - h / 2)) / minSide];
      const a = PARAMS.mode % 2 === 0 ? Math.atan2(centerA[1] - p[1], centerA[0] - p[0]) : distance(p, centerA);
      const b = PARAMS.mode === 0 ? Math.atan2(centerB[1] - p[1], centerB[0] - p[0]) : distance(p, centerB);
      const value = smooth((Math.cos(a * morphA) * Math.cos(b * morphB) + 1) / 2);
      const char = CHARSET[Math.min(CHARSET.length - 1, Math.floor(value * CHARSET.length))];
      if (char !== ' ') ctx.fillText(char, px, py);
    }
  }
}

/** Mede largura/altura de um caractere monoespaçado (função `sn` do original). */
function measureCharRatio() {
  const probe = document.createElement('span');
  probe.textContent = 'W';
  Object.assign(probe.style, {
    position: 'absolute',
    visibility: 'hidden',
    whiteSpace: 'nowrap',
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
    lineHeight: '12px',
  });
  document.body.append(probe);
  const ratio = probe.offsetWidth / probe.offsetHeight;
  probe.remove();
  return ratio || 0.6;
}

export function initAsciiPattern(canvas = document.querySelector('[data-ascii-pattern]')) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d', { alpha: true });
  const startedAt = performance.now();
  let charRatio = measureCharRatio();
  let timer = 0;

  // tempo do original: (agora - início) * 0.1 * 1e-4 (ms -> unidades lentas)
  const currentTime = () => (performance.now() - startedAt) * 0.1 * 1e-4;

  const resize = () => {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(canvas.clientWidth * dpr);
    canvas.height = Math.round(canvas.clientHeight * dpr);
    draw(ctx, canvas, currentTime(), charRatio);
  };

  document.fonts?.ready.then(() => {
    charRatio = measureCharRatio();
    resize();
  });
  new ResizeObserver(resize).observe(canvas);

  if (prefersReducedMotion()) return;
  observeVisibility(canvas, {
    onEnter: () => {
      if (!timer) timer = setInterval(() => draw(ctx, canvas, currentTime(), charRatio), PARAMS.intervalMs);
    },
    onLeave: () => {
      clearInterval(timer);
      timer = 0;
    },
  });
}
