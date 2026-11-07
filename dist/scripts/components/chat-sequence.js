/**
 * Conversa animada do card "Investigação".
 *
 * Port do "AI Chat Card" (script-017). O original é uma máquina de
 * variantes que avança sozinha; a ordem e os tempos são os do bundle:
 *
 *   1 Typing ............ 2000ms  (digita a pergunta no campo)
 *   2a Sent ............. 850ms   (bolha do usuário aparece)
 *   2 Thinking .......... 1200ms
 *   3 Answered .......... 800ms   (resposta aparece)
 *   3b Typing Follow-up . 800ms
 *   4a Follow-up Sent ... 1200ms
 *   4 Follow-up ......... fim     (indicador de digitação fica ativo)
 *
 * Status do cabeçalho: Pronto -> Enviado -> Pensando -> Respondendo.
 * Bolhas entram com 450ms ease [.42,0,.58,1].
 */

import { qs, sleep, whenVisible, prefersReducedMotion } from '../lib/dom.js';

const ENTER_MS = 450;

export async function initChatSequence(root = qs('[data-chat]')) {
  if (!root) return;

  const status = qs('[data-chat-status] span', root);
  const input = qs('[data-chat-input]', root);
  const step = (name) => qs(`[data-step="${name}"]`, root);
  const rows = ['question', 'answer', 'followup', 'typing'].map(step);

  if (prefersReducedMotion()) {
    status.textContent = 'Respondendo';
    return; // estado final já está no HTML
  }

  // Estado inicial: nenhuma bolha visível.
  rows.forEach((row) => (row.hidden = true));
  await whenVisible(root, { rootMargin: '0px 0px -20% 0px' });

  const show = async (row) => {
    row.hidden = false;
    row.classList.add('is-entering');
    row.getBoundingClientRect(); // força o reflow para a transição rodar
    row.classList.remove('is-entering');
    await sleep(ENTER_MS);
  };

  const type = async (text, totalMs) => {
    input.classList.add('is-typing');
    const perChar = totalMs / text.length;
    for (let i = 1; i <= text.length; i++) {
      input.textContent = text.slice(0, i);
      await sleep(perChar);
    }
  };

  const clearInput = () => {
    input.classList.remove('is-typing');
    input.textContent = input.dataset.placeholder;
  };

  const questionText = qs('.bubble', rows[0]).textContent;
  const followupText = qs('.bubble', rows[2]).textContent;

  // 1 Typing (2000ms)
  await type(questionText, 2000);
  // 2a Sent (850ms)
  clearInput();
  status.textContent = 'Enviado';
  await show(rows[0]);
  await sleep(850 - ENTER_MS);
  // 2 Thinking (1200ms)
  status.textContent = 'Pensando';
  root.classList.add('is-busy');
  await sleep(1200);
  // 3 Answered (800ms)
  root.classList.remove('is-busy');
  status.textContent = 'Respondendo';
  await show(rows[1]);
  await sleep(800 - ENTER_MS);
  // 3b Typing Follow-up (800ms)
  await type(followupText, 800);
  // 4a Follow-up Sent (1200ms)
  clearInput();
  await show(rows[2]);
  await sleep(1200 - ENTER_MS);
  // 4 Follow-up: digitando
  root.classList.add('is-busy');
  await show(rows[3]);
}
