/**
 * Wordmark com spotlight no rodapé (componente de spotlight, script-006).
 *
 * Original: o logo é uma máscara; a camada base fica a 15% de branco e a
 * camada acesa (gradiente #66ccff -> #fff -> #66ccff a 90deg) aparece só
 * dentro de um círculo de 180px que segue o ponteiro. Sem ponteiro, o
 * círculo varre o logo da esquerda para a direita em 5s e pausa 0,4s
 * (ciclo de 5400ms). Aqui o mesmo é feito com uma <mask> SVG.
 */

import { qs, observeVisibility, prefersReducedMotion } from '../lib/dom.js';
import { onTick } from '../lib/ticker.js';

const RADIUS_PX = 180;
const SWEEP_MS = 5000;
const CYCLE_MS = 5400;

export function initSpotlight(root = qs('[data-spotlight]')) {
  if (!root) return;
  const svg = qs('svg', root);
  const circle = qs('[data-spotlight-circle]', root);
  const lit = qs('[data-spotlight-lit]', root);
  const viewBox = svg.viewBox.baseVal;

  let pointer = null; // {x, y} em coordenadas do viewBox
  let loopTime = 0;
  let stopTicking = null;

  const pxToView = () => viewBox.width / svg.getBoundingClientRect().width;

  const place = (x, y) => {
    circle.setAttribute('cx', x);
    circle.setAttribute('cy', y);
  };

  const resizeRadius = () => circle.setAttribute('r', RADIUS_PX * pxToView());

  const isTouch = window.matchMedia('(hover: none), (pointer: coarse)').matches;
  if (!isTouch) {
    root.addEventListener('pointermove', (event) => {
      const rect = svg.getBoundingClientRect();
      const scale = viewBox.width / rect.width;
      pointer = { x: (event.clientX - rect.left) * scale, y: (event.clientY - rect.top) * scale };
      place(pointer.x, pointer.y);
    });
    root.addEventListener('pointerleave', () => {
      pointer = null;
      loopTime = 0;
    });
  }

  const tick = (_elapsed, delta) => {
    if (pointer) return;
    loopTime = (loopTime + delta) % CYCLE_MS;
    const r = Number(circle.getAttribute('r'));
    const t = Math.min(1, loopTime / SWEEP_MS);
    // Atravessa de -r até largura + r
    place(-r + t * (viewBox.width + 2 * r), viewBox.height * 0.5);
  };

  resizeRadius();
  new ResizeObserver(resizeRadius).observe(svg);

  if (prefersReducedMotion()) {
    place(viewBox.width * 0.3, viewBox.height * 0.5);
    return;
  }

  observeVisibility(root, {
    onEnter: () => {
      lit.style.opacity = '1';
      stopTicking ??= onTick(tick);
    },
    onLeave: () => {
      stopTicking?.();
      stopTicking = null;
    },
  });
}
