/**
 * Contador numérico ("Animated Number Counter", script-020).
 *
 * Original: anima de `start` a `end` quando entra na tela (trigger
 * layerInView, replay: false), com `toFixed(decimals)` e separador opcional.
 * Instâncias da Home: delay .4s, 1.4s, ease [.44,0,.56,1] (estatísticas);
 * spring {bounce:0, duration:1} (card de depoimento).
 *
 * Atributos: data-to, data-from (0), data-decimals (0), data-delay (0),
 * data-duration (1000). Formatação em pt-BR (vírgula decimal).
 */

import { qsa, whenVisible, prefersReducedMotion } from '../lib/dom.js';
import { tween, ease } from '../lib/easing.js';

const format = (value, decimals) =>
  value.toLocaleString('pt-BR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

export async function animateCounter(el) {
  const to = Number(el.dataset.to);
  const from = Number(el.dataset.from ?? 0);
  const decimals = Number(el.dataset.decimals ?? 0);
  const delay = Number(el.dataset.delay ?? 0);
  const duration = Number(el.dataset.duration ?? 1000);

  if (prefersReducedMotion()) {
    el.textContent = format(to, decimals);
    return;
  }

  el.textContent = format(from, decimals);
  await whenVisible(el);
  await tween({
    from,
    to,
    delay,
    duration,
    easing: delay ? ease.inOut : ease.spring,
    onUpdate: (value) => (el.textContent = format(value, decimals)),
  });
}

export function initCounters(root = document) {
  qsa('[data-counter]', root).forEach(animateCounter);
}
