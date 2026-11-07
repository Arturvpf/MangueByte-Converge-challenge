const routes = {
  'visao-geral': 'Visão geral',
  investigacao: 'Investigação',
  previsao: 'Previsão',
  cenarios: 'Cenários',
  revisao: 'Revisão do RH',
};

const sidebar = document.querySelector('#sidebar');
const menuToggle = document.querySelector('[data-menu-toggle]');
const mobileBackdrop = document.querySelector('[data-mobile-backdrop]');

function closeMenu() {
  sidebar.classList.remove('is-open');
  mobileBackdrop.hidden = true;
  menuToggle.setAttribute('aria-expanded', 'false');
  menuToggle.setAttribute('aria-label', 'Abrir navegação');
}

function showRoute() {
  const route = decodeURIComponent(location.hash.slice(1));
  const active = Object.hasOwn(routes, route) ? route : 'visao-geral';
  document.querySelectorAll('[data-screen]').forEach((section) => {
    const selected = section.dataset.screen === active;
    section.hidden = !selected;
    section.classList.toggle('is-active', selected);
  });
  document.querySelectorAll('[data-nav]').forEach((link) => {
    if (link.dataset.nav === active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  document.querySelector('[data-topbar-title]').textContent = routes[active];
  document.title = `${routes[active]} — Alinia`;
  closeMenu();
  window.scrollTo({ top: 0, behavior: 'instant' });
}

menuToggle.addEventListener('click', () => {
  const open = sidebar.classList.toggle('is-open');
  mobileBackdrop.hidden = !open;
  menuToggle.setAttribute('aria-expanded', String(open));
  menuToggle.setAttribute('aria-label', open ? 'Fechar navegação' : 'Abrir navegação');
});
mobileBackdrop.addEventListener('click', closeMenu);
window.addEventListener('hashchange', showRoute);
showRoute();

const forecastData = {
  low: {
    value: '1.080',
    values: ['1.050', '1.060', '1.075', '1.080'],
    widths: ['51%', '54%', '58%', '60%'],
    heading: 'Mesmo com demanda baixa, verifique o déficit por skill.',
    copy: 'A faixa baixa reduz a pressão agregada, mas não mostra se os turnos e competências críticos estão cobertos.',
  },
  base: {
    value: '1.200',
    values: ['1.165', '1.180', '1.195', '1.200'],
    widths: ['67%', '72%', '77%', '80%'],
    heading: 'O cenário base mantém o déficit agregado.',
    copy: 'Com 1.200 atendimentos projetados, o baseline homogêneo de 42h equivale a aproximadamente 14 pessoas. A composição por competência segue pendente.',
  },
  high: {
    value: '1.320',
    values: ['1.265', '1.285', '1.305', '1.320'],
    widths: ['84%', '89%', '94%', '98%'],
    heading: 'A alta demanda amplia a necessidade de margem operacional.',
    copy: 'O cenário alto testa a robustez das alternativas. Sem dados por skill e turno, a Alinia não conclui uma composição de vagas.',
  },
};

document.querySelectorAll('[data-forecast]').forEach((button) => {
  button.addEventListener('click', () => {
    const data = forecastData[button.dataset.forecast];
    document.querySelectorAll('[data-forecast]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
    document.querySelector('[data-forecast-value]').textContent = data.value;
    document.querySelector('[data-forecast-heading]').textContent = data.heading;
    document.querySelector('[data-forecast-copy]').textContent = data.copy;
    data.values.forEach((value, index) => {
      document.querySelector(`[data-bar="${index}"]`).style.setProperty('--bar', data.widths[index]);
      document.querySelector(`[data-bar-label="${index}"]`).textContent = value;
    });
    document.querySelector('.forecast-bars').setAttribute('aria-label', `Barras ilustrativas de demanda para cenário ${button.textContent.trim()}: semanas 1 a 4, ${data.values.join(', ')} atendimentos`);
  });
});

const scenarioData = {
  a: { head: 'A · Contratar', coverage: 'A validar por skill', timing: 'Após contratação e ramp-up', risk: 'Mentoria e cobertura N1', status: 'Condicional' },
  c: { head: 'C · Realocar', coverage: 'A validar por skill', timing: 'Após formação e realocação', risk: 'Impacto na equipe de origem', status: 'Condicional' },
  e: { head: 'E · Não agir', coverage: 'Gap agregado de 3 posições', timing: 'Imediato', risk: 'Backlog e pressão operacional', status: 'Referência' },
};
let selectedScenarios = ['a', 'c'];

function renderComparison() {
  document.querySelectorAll('[data-select-scenario]').forEach((button) => {
    const selected = selectedScenarios.includes(button.dataset.selectScenario);
    button.setAttribute('aria-pressed', String(selected));
    button.closest('.scenario-card').classList.toggle('is-selected', selected);
    button.querySelector('.select-box').textContent = selected ? '✓' : '';
    button.lastChild.textContent = selected ? 'Selecionado para comparação' : 'Adicionar à comparação';
  });
  document.querySelector('[data-comparison-count]').textContent = `${selectedScenarios.length} selecionado${selectedScenarios.length === 1 ? '' : 's'}`;
  document.querySelector('[data-comparison-empty]').hidden = selectedScenarios.length > 0;
  document.querySelectorAll('[data-compare-head]').forEach((head, index) => {
    head.textContent = selectedScenarios[index] ? scenarioData[selectedScenarios[index]].head : '—';
  });
  document.querySelectorAll('[data-compare]').forEach((cell) => {
    const key = selectedScenarios[Number(cell.dataset.compare)];
    cell.textContent = key ? scenarioData[key][cell.dataset.field] : '—';
  });
}

document.querySelectorAll('[data-select-scenario]').forEach((button) => {
  button.addEventListener('click', () => {
    const key = button.dataset.selectScenario;
    if (selectedScenarios.includes(key)) selectedScenarios = selectedScenarios.filter((item) => item !== key);
    else selectedScenarios = [...selectedScenarios.slice(-1), key];
    renderComparison();
  });
});
renderComparison();

const evidence = {
  demanda: { title: 'Demanda atual', intro: 'Fonte ilustrativa do exemplo da Unidade Centro no PRD v4.1.', items: [['Unidade', 'Atendimentos comparáveis por semana'], ['Valor atual', '1.150 atendimentos / semana'], ['Limitação', 'Não somar unidades de trabalho incomparáveis entre equipes.']] },
  jornada: { title: 'Premissa de jornada', intro: 'A jornada de 42h é usada apenas para simulação do exemplo.', items: [['Jornada simulada', '42 horas semanais'], ['Controle necessário', 'Confirmar categoria, vigência e instrumento coletivo aplicável com o RH/jurídico.'], ['Execução', 'Nenhuma alteração de escala ou ponto nesta demonstração.']] },
  calculo: { title: 'Cálculo agregado', intro: 'Baseline homogêneo reproduzido a partir dos números do PRD.', items: [['Entradas', '11 pessoas × 42h × 91% de disponibilidade × 2,27 atendimentos/hora'], ['Capacidade', 'Aproximadamente 954 atendimentos por semana'], ['IPD', '1.150 ÷ 954 ≈ 1,21'], ['Limitação', 'Não distribui horas por competência ou turno e não define automaticamente as vagas.']] },
  skills: { title: 'Matriz de competências pendente', intro: 'O gap agregado não resolve a composição da equipe.', items: [['Dado necessário', 'Horas elegíveis por skill, turno e função.'], ['Risco', 'Contar a mesma hora em várias competências ou supor que três pessoas fecham qualquer gap N1.'], ['Próximo passo', 'Validar a matriz com RH e operação antes de otimizar a alocação.']] },
  historico: { title: 'Histórico insuficiente', intro: 'Uma hipótese sazonal exige comparação temporal antes de orientar modalidade de contratação.', items: [['Dado necessário', 'Histórico de demanda comparável e calendário de eventos.'], ['Método', 'Baseline e backtesting com origem temporal rolante.'], ['Estado', 'Hipótese não verificada nesta demonstração.']] },
};

const drawer = document.querySelector('[data-drawer]');
const drawerBackdrop = document.querySelector('[data-drawer-backdrop]');
let previousFocus;

function closeDrawer() {
  drawer.hidden = true;
  drawerBackdrop.hidden = true;
  document.body.style.overflow = '';
  previousFocus?.focus();
}

document.querySelectorAll('[data-evidence]').forEach((button) => {
  button.addEventListener('click', () => {
    previousFocus = button;
    const item = evidence[button.dataset.evidence];
    document.querySelector('[data-drawer-title]').textContent = item.title;
    document.querySelector('[data-drawer-intro]').textContent = item.intro;
    const body = document.querySelector('[data-drawer-body]');
    body.replaceChildren(...item.items.map(([label, value]) => {
      const box = document.createElement('div');
      const heading = document.createElement('span');
      const text = document.createElement('strong');
      heading.textContent = label;
      text.textContent = value;
      box.append(heading, text);
      return box;
    }));
    drawer.hidden = false;
    drawerBackdrop.hidden = false;
    document.body.style.overflow = 'hidden';
    drawer.querySelector('[data-drawer-close]').focus();
  });
});
document.querySelectorAll('[data-drawer-close]').forEach((button) => button.addEventListener('click', closeDrawer));
drawerBackdrop.addEventListener('click', closeDrawer);
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') { closeDrawer(); closeMenu(); } });

document.querySelector('[data-review-action]').addEventListener('click', (event) => {
  event.currentTarget.textContent = 'Checklist preparado ✓';
  event.currentTarget.disabled = true;
  document.querySelector('[data-review-feedback]').textContent = 'Checklist preparado nesta sessão. Nenhuma requisição foi criada.';
});
