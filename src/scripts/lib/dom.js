/**
 * Utilitários de DOM e de visibilidade.
 */

export const qs = (selector, root = document) => root.querySelector(selector);
export const qsa = (selector, root = document) => Array.from(root.querySelectorAll(selector));

export const prefersReducedMotion = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Chama `onEnter`/`onLeave` quando o elemento entra/sai da viewport.
 * Equivale ao `useInView` do framer-motion usado pelos componentes originais.
 *
 * @param {Element} el
 * @param {{ onEnter?: Function, onLeave?: Function, once?: boolean, rootMargin?: string, threshold?: number }} options
 * @returns {() => void} função para parar de observar
 */
export function observeVisibility(el, { onEnter, onLeave, once = false, rootMargin = '0px', threshold = 0 } = {}) {
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          onEnter?.(entry);
          if (once) observer.disconnect();
        } else {
          onLeave?.(entry);
        }
      }
    },
    { rootMargin, threshold },
  );
  observer.observe(el);
  return () => observer.disconnect();
}

/** Resolve quando o elemento aparece na viewport pela primeira vez. */
export const whenVisible = (el, options = {}) =>
  new Promise((resolve) => observeVisibility(el, { ...options, once: true, onEnter: resolve }));
