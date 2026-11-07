/**
 * Abas com régua deslizante ("Tab Items", script-012).
 *
 * Geometria do original (G = largura da régua):
 *   - 303 traços, espaçamento G/101; a faixa tem 3G e começa em -G;
 *   - a linha ativa fica no traço 101 (= posição G dentro da faixa);
 *   - deslocamento da faixa: K = G * (0.1 + índice / 5) -> centro da aba;
 *   - transição: transform 900ms cubic-bezier(.22,1,.36,1), ligada só
 *     80ms depois da primeira medida (para não animar no carregamento).
 * Teclado: setas, Home e End, como no componente.
 */

import { qs, qsa } from '../lib/dom.js';

const TAB_COUNT_BASE = 5;
const ENABLE_TRANSITION_AFTER_MS = 80;

export function initRulerTabs(root = qs('[data-ruler-tabs]')) {
  if (!root) return;
  const tabs = qsa('[role="tab"]', root);
  const ruler = qs('.ruler', root);
  const strip = qs('[data-ruler-strip]', root);
  const panel = qs('[data-ruler-panel]');
  const texts = qsa('.ruler-tabs__text', panel);
  const scenes = qsa('.scene', panel);
  let active = 0;

  root.classList.add('is-static');

  const isPhone = () => window.matchMedia('(max-width: 746px)').matches;

  const positionRuler = () => {
    const width = ruler.clientWidth;
    let x;
    if (isPhone()) {
      // No celular a linha ativa fica no centro e a lista rola.
      x = width / 2;
      const tab = tabs[active];
      tab.parentElement.scrollTo({ left: tab.offsetLeft + tab.offsetWidth / 2 - width / 2, behavior: 'smooth' });
    } else {
      x = width * (0.1 + Math.min(active, 4) / TAB_COUNT_BASE);
    }
    strip.style.setProperty('--ruler-x', `${Math.round(x)}px`);
  };

  const select = (index, { focus = false } = {}) => {
    active = (index + tabs.length) % tabs.length;
    tabs.forEach((tab, i) => {
      const selected = i === active;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    texts.forEach((el, i) => (el.dataset.active = String(i === active)));
    scenes.forEach((el, i) => (el.dataset.active = String(i === active)));
    panel.setAttribute('aria-labelledby', tabs[active].id);
    positionRuler();
    if (focus) tabs[active].focus({ preventScroll: true });
  };

  tabs.forEach((tab, i) => tab.addEventListener('click', () => select(i)));

  root.addEventListener('keydown', (event) => {
    const keys = { ArrowRight: active + 1, ArrowLeft: active - 1, Home: 0, End: tabs.length - 1 };
    if (!(event.key in keys)) return;
    event.preventDefault();
    select(keys[event.key], { focus: true });
  });

  new ResizeObserver(positionRuler).observe(ruler);
  select(0);
  setTimeout(() => root.classList.remove('is-static'), ENABLE_TRANSITION_AFTER_MS);
}
