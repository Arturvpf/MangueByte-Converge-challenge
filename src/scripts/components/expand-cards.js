/**
 * Linha de cards em que só um fica aberto ("Testimonial Tab", script-015).
 * A largura é animada no CSS (flex-grow, spring .6s); aqui só se troca o
 * estado e se reinicia o contador do card que abriu.
 */

import { qs, qsa } from '../lib/dom.js';
import { animateCounter } from './counter.js';

export function initExpandCards(root = qs('[data-expand-cards]')) {
  if (!root) return;
  const cards = qsa('.x-card', root);

  const open = (target) => {
    for (const card of cards) {
      const isOpen = card === target;
      if (isOpen && card.dataset.expanded === 'true') return;
      card.dataset.expanded = String(isOpen);
      qs('.x-card__toggle', card).setAttribute('aria-expanded', String(isOpen));
    }
    qsa('[data-counter]', target).forEach(animateCounter);
  };

  cards.forEach((card) => qs('.x-card__toggle', card).addEventListener('click', () => open(card)));
}
