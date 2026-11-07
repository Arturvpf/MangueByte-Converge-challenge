/**
 * Navegação sticky das Capacidades com scroll-spy.
 *
 * No original cada item é um "Single Tab" com variantes Active/Inactive e a
 * barra lateral marca o card visível. Aqui: o card cujo topo passou da
 * metade da tela vira ativo e o indicador (::before da nav) viaja até ele.
 */

import { qs, qsa } from '../lib/dom.js';

export function initCapabilitiesNav(root = qs('[data-capabilities]')) {
  if (!root) return;
  const nav = qs('.capabilities__nav', root);
  const links = qsa('.capabilities__link', root);
  const cards = links.map((link) => qs(link.getAttribute('href')));

  const moveIndicator = (link) => {
    nav.style.setProperty('--indicator-y', `${link.offsetTop}px`);
    nav.style.setProperty('--indicator-h', `${link.offsetHeight}px`);
  };

  const setActive = (index) => {
    links.forEach((link, i) => {
      const isActive = i === index;
      link.classList.toggle('is-active', isActive);
      if (isActive) {
        link.setAttribute('aria-current', 'true');
        moveIndicator(link);
      } else {
        link.removeAttribute('aria-current');
      }
    });
  };

  // Um card fica "ativo" enquanto atravessa a linha do meio da tela.
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) setActive(cards.indexOf(entry.target));
      }
    },
    { rootMargin: '-50% 0px -50% 0px' },
  );
  cards.forEach((card) => card && observer.observe(card));

  setActive(0);
  window.addEventListener('resize', () => {
    const current = links.find((link) => link.classList.contains('is-active'));
    if (current) moveIndicator(current);
  });
}
