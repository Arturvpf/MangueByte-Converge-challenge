/**
 * Campo que "digita" uma pergunta ("Process Card" 2 / "Typewriter").
 * Digita, espera, apaga e repete enquanto estiver visível.
 */

import { qs, qsa, sleep, observeVisibility, prefersReducedMotion } from '../lib/dom.js';

const TYPE_MS = 45;
const ERASE_MS = 18;
const HOLD_MS = 2200;

function runTypewriter(root) {
  const text = root.dataset.typewriter;
  const target = qs('[data-typewriter-text]', root);

  if (prefersReducedMotion()) {
    target.textContent = text;
    return;
  }

  let visible = false;
  let running = false;

  const loop = async () => {
    running = true;
    while (visible) {
      for (let i = 1; i <= text.length && visible; i++) {
        target.textContent = text.slice(0, i);
        await sleep(TYPE_MS);
      }
      await sleep(HOLD_MS);
      for (let i = text.length; i >= 0 && visible; i--) {
        target.textContent = text.slice(0, i);
        await sleep(ERASE_MS);
      }
      await sleep(400);
    }
    running = false;
  };

  observeVisibility(root, {
    onEnter: () => {
      visible = true;
      if (!running) loop();
    },
    onLeave: () => (visible = false),
  });
}

export function initTypewriters(root = document) {
  qsa('[data-typewriter]', root).forEach(runTypewriter);
}
