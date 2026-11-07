/**
 * Card "Regras": carrossel de normas com item central destacado.
 *
 * Inspirado no "Rotating Integrations" / "Integrations Flow Card"
 * (script-017): uma faixa de itens que gira sozinha, com botões de
 * anterior/próximo (no original, um <fieldset> com Back/Next Arrow).
 */

import { qs, qsa, observeVisibility, prefersReducedMotion } from '../lib/dom.js';

const AUTOPLAY_MS = 2200;

export function initRuleCarousel(root = qs('[data-rules]')) {
  if (!root) return;
  const viewport = qs('.rules__viewport', root);
  const track = qs('[data-rules-track]', root);
  const items = qsa('li', track);
  const current = qs('[data-rules-current]', root);
  let index = 0;
  let timer = 0;

  const goTo = (next) => {
    index = (next + items.length) % items.length;
    const item = items[index];
    // centraliza o item ativo na janela
    const offset = item.offsetLeft + item.offsetWidth / 2 - viewport.clientWidth / 2;
    track.style.transform = `translate3d(${-offset}px, 0, 0)`;
    items.forEach((el, i) => el.classList.toggle('is-current', i === index));
    current.textContent = item.textContent;
  };

  const restart = () => {
    clearInterval(timer);
    if (prefersReducedMotion()) return;
    timer = setInterval(() => goTo(index + 1), AUTOPLAY_MS);
  };

  qs('[data-rules-prev]', root).addEventListener('click', () => {
    goTo(index - 1);
    restart();
  });
  qs('[data-rules-next]', root).addEventListener('click', () => {
    goTo(index + 1);
    restart();
  });

  goTo(0);
  new ResizeObserver(() => goTo(index)).observe(viewport);
  observeVisibility(root, {
    onEnter: restart,
    onLeave: () => clearInterval(timer),
  });
}
