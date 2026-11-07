/**
 * Card "Cenários": fluxo que acende etapa por etapa e recomeça.
 *
 * Inspirado no "Automation Flow Card" (script-017): gatilho -> ação ->
 * ramificação -> conclusão, com conectores tracejados animados. Cada etapa
 * usa a mesma transição dos cards (400ms, ease [.42,0,.58,1]).
 */

import { qs, qsa, sleep, whenVisible, observeVisibility, prefersReducedMotion } from '../lib/dom.js';

const STEP_MS = 900;
const HOLD_MS = 2600;

export async function initFlowCard(root = qs('[data-flow]')) {
  if (!root) return;
  const nodes = qsa('.flow__node[data-flow-step]', root);
  const wires = qsa('line[data-flow-step], path[data-flow-step]', root);
  const runLabel = qs('[data-flow-run]', root);
  const lastStep = Math.max(...nodes.map((n) => Number(n.dataset.flowStep)));

  const setStep = (step) => {
    for (const node of nodes) node.classList.toggle('is-pending', Number(node.dataset.flowStep) > step);
    for (const wire of wires) wire.classList.toggle('is-on', Number(wire.dataset.flowStep) <= step);
    if (runLabel) runLabel.textContent = step >= 2 ? 'concluído' : 'executando';
  };

  if (prefersReducedMotion()) {
    setStep(lastStep);
    return;
  }

  setStep(0);
  let isVisible = false;
  observeVisibility(root, {
    onEnter: () => (isVisible = true),
    onLeave: () => (isVisible = false),
  });

  // Laço infinito; cada volta só começa com o card na tela.
  for (;;) {
    if (!isVisible) await whenVisible(root, { rootMargin: '0px 0px -20% 0px' });
    for (let step = 0; step <= lastStep; step++) {
      setStep(step);
      await sleep(STEP_MS);
    }
    await sleep(HOLD_MS);
  }
}
