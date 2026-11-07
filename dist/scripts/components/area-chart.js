/**
 * Gráfico de área da seção "Determinístico" ("Animated Chart Line", script-012).
 *
 * O original desenha uma curva crescente com preenchimento em gradiente e
 * listras verticais brancas, revelada quando entra na tela. Aqui a série é
 * a projeção ilustrativa da Unidade Centro (PRD v4.1, seção 10): demanda de
 * ~1.000 até ~1.300 atendimentos/semana em 26 semanas, contra capacidade de
 * ~954 no cenário 42h.
 */

import { qs, whenVisible, prefersReducedMotion } from '../lib/dom.js';
import { tween, ease } from '../lib/easing.js';

const VIEW = { w: 1000, h: 400 };
const DOMAIN = { min: 600, max: 1400 };
const WEEKS = 26;
const CAPACITY = 954;
const BAR_STEP = 10; // px no viewBox entre listras verticais

const yOf = (value) => ((DOMAIN.max - value) / (DOMAIN.max - DOMAIN.min)) * VIEW.h;

/** Demanda projetada (curva convexa, ilustrativa). */
const demandAt = (t) => 1000 + 300 * t ** 2.2;

function buildSeries() {
  const points = [];
  for (let i = 0; i <= WEEKS; i++) {
    const t = i / WEEKS;
    points.push([t * VIEW.w, yOf(demandAt(t))]);
  }
  return points;
}

/** Curva suave (Catmull-Rom -> Bézier cúbica). */
function smoothPath(points) {
  let d = `M${points[0][0]},${points[0][1]}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0]},${c1[1]} ${c2[0]},${c2[1]} ${p2[0]},${p2[1]}`;
  }
  return d;
}

export async function initAreaChart(root = qs('[data-chart]')) {
  if (!root) return;
  const line = qs('[data-chart-line]', root);
  const area = qs('[data-chart-area]', root);
  const bars = qs('[data-chart-bars]', root);
  const capacity = qs('[data-chart-capacity]', root);
  const axis = qs('.chart__axis', root);

  const linePath = smoothPath(buildSeries());
  line.setAttribute('d', linePath);
  area.setAttribute('d', `${linePath} L${VIEW.w},${VIEW.h} L0,${VIEW.h} Z`);

  const capY = yOf(CAPACITY);
  capacity.setAttribute('y1', capY);
  capacity.setAttribute('y2', capY);

  // Listras verticais dentro da área.
  for (let x = BAR_STEP; x < VIEW.w; x += BAR_STEP) {
    const bar = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    bar.setAttribute('x1', x);
    bar.setAttribute('x2', x);
    bar.setAttribute('y1', 0);
    bar.setAttribute('y2', VIEW.h);
    bar.setAttribute('vector-effect', 'non-scaling-stroke');
    bars.append(bar);
  }

  // Eixo: rótulos posicionados pelo mesmo mapeamento da curva.
  axis.querySelectorAll('span').forEach((label) => {
    const value = Number(label.textContent.replace('.', ''));
    label.style.position = 'absolute';
    label.style.top = `${(yOf(value) / VIEW.h) * 100}%`;
    label.style.transform = 'translateY(-50%)';
  });

  if (prefersReducedMotion()) return;

  // Revelação: a linha "desenha" e a área acompanha por um clip retangular.
  const wipe = qs('[data-chart-wipe]', root);
  const length = line.getTotalLength();
  line.style.strokeDasharray = `${length}`;
  line.style.strokeDashoffset = `${length}`;
  wipe.setAttribute('width', 0);

  await whenVisible(root, { rootMargin: '0px 0px -25% 0px' });
  await tween({
    from: 0,
    to: 1,
    delay: 200,
    duration: 1400,
    easing: ease.inOut,
    onUpdate: (t) => {
      line.style.strokeDashoffset = `${length * (1 - t)}`;
      wipe.setAttribute('width', VIEW.w * t);
    },
  });
}
