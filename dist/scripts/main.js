/**
 * Boot da página.
 *
 * Ordem:
 *  1. marca <html class="js"> (o CSS só esconde [data-appear] com JS ativo);
 *  2. espera as fontes: régua, carrossel e o padrão ASCII medem texto;
 *  3. smooth scroll (Lenis) antes do header, que usa a instância no menu;
 *  4. componentes, de cima para baixo na página;
 *  5. entrada do hero (opacity .001 -> 1, spring .6s, delay .2s).
 */

import { qsa } from './lib/dom.js';
import { initSmoothScroll } from './components/smooth-scroll.js';
import { initHeader } from './components/header.js';
import { initLiquidMetal } from './components/liquid-metal.js';
import { createFlutedSwirl, PRESETS } from './components/fluted-swirl.js';
import { initDotRows, initLiveOverview } from './components/live-overview.js';
import { initCapabilitiesNav } from './components/capabilities-nav.js';
import { initChatSequence } from './components/chat-sequence.js';
import { initFlowCard } from './components/flow-card.js';
import { initRuleCarousel } from './components/rule-carousel.js';
import { initRulerTabs } from './components/ruler-tabs.js';
import { initTypewriters } from './components/typewriter.js';
import { initExpandCards } from './components/expand-cards.js';
import { initCounters } from './components/counter.js';
import { initAreaChart } from './components/area-chart.js';
import { initAsciiPattern } from './components/ascii-pattern.js';
import { initCopyButtons } from './components/copy-button.js';
import { initAccordion } from './components/accordion.js';
import { initSpotlight } from './components/spotlight.js';
import { observeVisibility } from './lib/dom.js';

document.documentElement.classList.add('js');

/** Executa cada init isolado: um componente com erro não derruba os outros. */
function safely(name, init) {
  try {
    const result = init();
    if (result instanceof Promise) result.catch((error) => console.error(`[${name}]`, error));
  } catch (error) {
    console.error(`[${name}]`, error);
  }
}

async function boot() {
  await document.fonts?.ready;

  safely('smooth-scroll', initSmoothScroll);
  safely('header', initHeader);

  // Hero
  safely('fluted-swirl', () => {
    for (const canvas of qsa('[data-fluted-swirl]')) {
      createFlutedSwirl(canvas, PRESETS[canvas.dataset.flutedSwirl] ?? PRESETS.hero);
    }
  });
  safely('liquid-metal', initLiquidMetal);
  safely('dot-rows', initDotRows);

  // Capacidades
  safely('capabilities-nav', initCapabilitiesNav);
  safely('chat', initChatSequence);
  safely('overview', initLiveOverview);
  safely('flow', initFlowCard);
  safely('rules', initRuleCarousel);

  // Casos de uso, processo, exemplo, escala
  safely('ruler-tabs', initRulerTabs);
  safely('typewriter', initTypewriters);
  safely('sources-card', () => {
    for (const card of qsa('[data-sources-card]')) {
      observeVisibility(card, { once: true, onEnter: () => card.classList.add('is-visible') });
    }
  });
  safely('expand-cards', initExpandCards);
  safely('counters', initCounters);
  safely('area-chart', initAreaChart);

  // Segurança, FAQ, rodapé
  safely('ascii-pattern', initAsciiPattern);
  safely('copy', initCopyButtons);
  safely('accordion', initAccordion);
  safely('spotlight', initSpotlight);

  // Entrada do hero
  requestAnimationFrame(() => qsa('[data-appear]').forEach((el) => el.classList.add('is-in')));
}

boot();
