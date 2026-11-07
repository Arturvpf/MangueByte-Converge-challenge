/**
 * Header: tema claro/escuro conforme a seção sob ele + menu mobile.
 *
 * O Navbar original troca entre variantes Light/Dark. Aqui uma linha fina
 * na altura do header é observada: qualquer seção [data-theme="dark"] que a
 * cruze deixa o header escuro.
 */

import { qs, qsa } from '../lib/dom.js';
import { getLenis } from './smooth-scroll.js';

export function initHeader() {
  const header = qs('[data-header]');
  if (!header) return;

  const darkSections = qsa('[data-theme="dark"]');
  const active = new Set();

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) active.add(entry.target);
        else active.delete(entry.target);
      }
      header.classList.toggle('is-dark', active.size > 0);
    },
    // Faixa de 1px logo abaixo do topo da tela (meio do header).
    { rootMargin: '-32px 0px -100% 0px', threshold: 0 },
  );
  darkSections.forEach((section) => observer.observe(section));

  initMobileMenu(header);
}

function initMobileMenu(header) {
  const toggle = qs('[data-menu-toggle]', header);
  const menu = qs('[data-menu]');
  if (!toggle || !menu) return;

  const setOpen = (open) => {
    toggle.setAttribute('aria-expanded', String(open));
    toggle.querySelector('.visually-hidden').textContent = open ? 'Fechar menu' : 'Abrir menu';
    menu.classList.toggle('is-open', open);
    const lenis = getLenis();
    if (lenis) open ? lenis.stop() : lenis.start();
  };

  toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
  menu.addEventListener('click', (event) => {
    if (event.target.closest('a')) setOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && menu.classList.contains('is-open')) {
      setOpen(false);
      toggle.focus();
    }
  });
  window.matchMedia('(min-width: 1200px)').addEventListener('change', (event) => {
    if (event.matches) setOpen(false);
  });
}
