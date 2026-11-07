/**
 * Um único requestAnimationFrame para a página inteira.
 *
 * O original tem um relógio compartilhado parecido (objeto `J` no módulo do
 * Liquid Metal: elapsed, last, subscribers), que limita o delta a 100ms e
 * pausa quando a aba fica oculta. Aqui o mesmo contrato serve a todos os
 * componentes animados (shaders, padrão ASCII, spotlight).
 */

const subscribers = new Set();
let rafId = 0;
let last = 0;
let elapsed = 0;

function frame(now) {
  const delta = Math.min(100, now - last);
  last = now;
  elapsed += delta;
  for (const callback of subscribers) callback(elapsed, delta);
  rafId = subscribers.size > 0 ? requestAnimationFrame(frame) : 0;
}

function start() {
  if (rafId || document.hidden) return;
  last = performance.now();
  rafId = requestAnimationFrame(frame);
}

function stop() {
  cancelAnimationFrame(rafId);
  rafId = 0;
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) stop();
  else if (subscribers.size > 0) start();
});

/**
 * Inscreve um callback `(elapsedMs, deltaMs) => void`.
 * @returns {() => void} cancela a inscrição
 */
export function onTick(callback) {
  subscribers.add(callback);
  start();
  return () => {
    subscribers.delete(callback);
    if (subscribers.size === 0) stop();
  };
}
