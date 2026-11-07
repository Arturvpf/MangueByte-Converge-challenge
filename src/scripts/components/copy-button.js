/**
 * Botão de copiar ("Copy Clipboard" / "Copy Button", script-012):
 * copia o texto de [data-copy-source] e mostra "Copiado!" por 1,6s.
 */

import { qsa } from '../lib/dom.js';

const FEEDBACK_MS = 1600;

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback para contextos sem a Clipboard API (ex.: http sem localhost)
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    return ok;
  }
}

export function initCopyButtons(root = document) {
  for (const button of qsa('[data-copy]', root)) {
    const source = button.closest('.code')?.querySelector('[data-copy-source]');
    let timer = 0;
    button.addEventListener('click', async () => {
      if (!source || !(await copyText(source.textContent.trim()))) return;
      button.classList.add('is-copied');
      clearTimeout(timer);
      timer = setTimeout(() => button.classList.remove('is-copied'), FEEDBACK_MS);
    });
  }
}
