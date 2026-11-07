/**
 * Smooth scroll com Lenis.
 *
 * Original: componente "Lenis" (script-006) instanciado com
 *   { smoothWheel: true, duration: intensity / 10, anchors: true, ... }
 * e intensity = 6 na Home -> duration 0.6.
 */

import Lenis from '../vendor/lenis.mjs';
import { prefersReducedMotion } from '../lib/dom.js';

let lenis = null;

export function initSmoothScroll() {
  if (prefersReducedMotion()) return null;

  lenis = new Lenis({
    duration: 0.6,
    smoothWheel: true,
    autoRaf: true,
    anchors: { offset: 0 },
  });
  return lenis;
}

/** Rola até um elemento ou posição, com ou sem Lenis. */
export function scrollToTarget(target, { offset = 0 } = {}) {
  if (lenis) {
    lenis.scrollTo(target, { offset });
    return;
  }
  const el = typeof target === 'string' ? document.querySelector(target) : target;
  if (el instanceof Element) {
    const top = el.getBoundingClientRect().top + window.scrollY + offset;
    window.scrollTo({ top, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  }
}

export const getLenis = () => lenis;
