/**
 * FAQ ("FAQ", script-015): um item aberto por vez; a altura anima no CSS
 * (grid-template-rows, 300ms, ease [.44,0,.56,1]).
 */

import { qs, qsa } from '../lib/dom.js';

export function initAccordion(root = qs('[data-accordion]')) {
  if (!root) return;
  const items = qsa('.accordion__item', root);

  const setOpen = (item, open) => {
    item.dataset.open = String(open);
    qs('.accordion__trigger', item).setAttribute('aria-expanded', String(open));
  };

  for (const item of items) {
    qs('.accordion__trigger', item).addEventListener('click', () => {
      const willOpen = item.dataset.open !== 'true';
      items.forEach((other) => setOpen(other, other === item ? willOpen : false));
    });
  }
}
