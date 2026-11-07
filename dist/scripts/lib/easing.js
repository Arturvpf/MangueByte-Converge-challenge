/**
 * Curvas e interpolação de valores.
 *
 * O framer-motion descreve curvas como arrays `[x1, y1, x2, y2]`. `bezier()`
 * transforma esse array numa função `t -> progresso`, para que os números
 * lidos do bundle possam ser usados sem conversão manual.
 */

/** Cubic-bezier de CSS como função JS (Newton-Raphson + bisseção). */
export function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1;
  const bx = 3 * (x2 - x1) - cx;
  const ax = 1 - cx - bx;
  const cy = 3 * y1;
  const by = 3 * (y2 - y1) - cy;
  const ay = 1 - cy - by;

  const sampleX = (t) => ((ax * t + bx) * t + cx) * t;
  const sampleY = (t) => ((ay * t + by) * t + cy) * t;
  const slopeX = (t) => (3 * ax * t + 2 * bx) * t + cx;

  function solveT(x) {
    let t = x;
    for (let i = 0; i < 8; i++) {
      const error = sampleX(t) - x;
      if (Math.abs(error) < 1e-6) return t;
      const slope = slopeX(t);
      if (Math.abs(slope) < 1e-6) break;
      t -= error / slope;
    }
    let lo = 0;
    let hi = 1;
    t = x;
    while (lo < hi) {
      const value = sampleX(t);
      if (Math.abs(value - x) < 1e-6) return t;
      if (x > value) lo = t;
      else hi = t;
      t = (lo + hi) / 2;
      if (hi - lo < 1e-6) break;
    }
    return t;
  }

  return (x) => (x <= 0 ? 0 : x >= 1 ? 1 : sampleY(solveT(x)));
}

/** Curvas usadas pelo site (valores originais). */
export const ease = {
  inOut: bezier(0.44, 0, 0.56, 1), // FAQ, contadores de estatística
  standard: bezier(0.42, 0, 0.58, 1), // AI Chat Card
  outExpo: bezier(0.22, 1, 0.36, 1), // Tab Items
  // spring {bounce: 0, duration: .6} (amortecimento crítico) aproximado
  spring: bezier(0.25, 1, 0.5, 1),
};

/**
 * Anima um número de `from` até `to`.
 * @returns {Promise<void>} resolve ao terminar
 */
export function tween({ from, to, duration = 1000, delay = 0, easing = ease.inOut, onUpdate }) {
  return new Promise((resolve) => {
    const startAt = performance.now() + delay;
    function step(now) {
      const t = Math.min(1, Math.max(0, (now - startAt) / duration));
      onUpdate(from + (to - from) * easing(t));
      if (t < 1) requestAnimationFrame(step);
      else resolve();
    }
    requestAnimationFrame(step);
  });
}
