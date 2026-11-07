/**
 * Card "Previsão": matriz de pontos e números que se atualizam.
 *
 * Inspirado no "Live Overview Card" (script-017), em que cada coluna da
 * matriz de pontos é uma barra e o painel "respira" em intervalos curtos.
 * Os valores aqui são uma série sintética em torno do exemplo do PRD
 * (demanda ~1.200/semana); não representam dados reais.
 */

import { qs, qsa, observeVisibility, prefersReducedMotion } from '../lib/dom.js';

const COLUMNS = 56; // 8 colunas por dia da semana
const ROWS = 6;
const UPDATE_MS = 1400;

/* Exemplo "Unidade Centro" do PRD (seção 10), cenário 42h. */
const DEMAND_PROJECTED = 1200; // atendimentos/semana projetados
const DEMAND_CURRENT = 1150; // base do IPD atual
const CAPACITY_42H = 954; // capacidade semanal no cenário 42h

const formatInt = (n) => Math.round(n).toLocaleString('pt-BR');
const formatDec = (n) => n.toFixed(2).replace('.', ',');

/** Intensidade 0..1 por coluna: padrão semanal + ruído determinístico. */
function columnLevel(index, phase) {
  const day = index / 8;
  const weekly = 0.55 + 0.3 * Math.sin((day / 7) * Math.PI * 2 - 0.6);
  const noise = Math.sin(index * 12.9898 + phase * 0.7) * 0.5 + 0.5;
  return Math.min(1, Math.max(0.05, weekly * 0.85 + noise * 0.25));
}

export function initLiveOverview(root = qs('[data-overview]')) {
  if (!root) return;
  const plot = qs('[data-dot-chart]', root);

  // Monta a grade (coluna-major, como o grid-auto-flow: column).
  const fragment = document.createDocumentFragment();
  for (let i = 0; i < COLUMNS * ROWS; i++) fragment.append(document.createElement('i'));
  plot.append(fragment);
  const dots = qsa('i', plot);

  const live = {
    demand: qs('[data-live="demand"]', root),
    capacity: qs('[data-live="capacity"]', root),
    ipd: qs('[data-live="ipd"]', root),
    now: qs('[data-live="now"]', root),
  };

  let phase = 0;
  const render = () => {
    for (let col = 0; col < COLUMNS; col++) {
      const level = columnLevel(col, phase);
      const lit = Math.round(level * ROWS);
      for (let row = 0; row < ROWS; row++) {
        const dot = dots[col * ROWS + row];
        const fromBottom = ROWS - 1 - row;
        dot.classList.toggle('is-on', fromBottom < lit - 1);
        dot.classList.toggle('is-mid', fromBottom === lit - 1);
      }
    }
    // Oscilação pequena e determinística só para o painel parecer "vivo".
    const wobble = Math.sin(phase * 1.3);
    const demand = DEMAND_PROJECTED + wobble * 14;
    live.demand.textContent = formatInt(demand);
    live.now.textContent = formatInt(demand);
    live.capacity.textContent = formatInt(CAPACITY_42H);
    live.ipd.textContent = formatDec(DEMAND_CURRENT / CAPACITY_42H + wobble * 0.004);
  };

  render();
  if (prefersReducedMotion()) return;

  let timer = 0;
  observeVisibility(root, {
    onEnter: () => {
      if (timer) return;
      timer = setInterval(() => {
        phase += 1;
        render();
      }, UPDATE_MS);
    },
    onLeave: () => {
      clearInterval(timer);
      timer = 0;
    },
  });
}

/** Linha de pontos do painel do hero ("Cobertura por turno"). */
export function initDotRows(root = document) {
  for (const row of qsa('[data-dot-row]', root)) {
    const count = Number(row.dataset.dotRow);
    const filled = Math.round(count * Number(row.dataset.dotFill));
    for (let i = 0; i < count; i++) {
      const dot = document.createElement('i');
      if (i >= count - filled) dot.className = 'is-on';
      row.append(dot);
    }
  }
}
