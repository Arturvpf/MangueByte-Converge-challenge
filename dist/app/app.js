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

/* Gráficos: o SVG estica (preserveAspectRatio none) e os traços usam
   non-scaling-stroke; rótulos e o ponto final ficam em HTML. */
const SVG_NS = 'http://www.w3.org/2000/svg';
const PLOT_W = 1000;
const PLOT_H = 240;
const CAPACITY = 954;

const toNumber = (value) => Number(String(value).replace(/\./g, '').replace(',', '.'));
const formatInt = (value) => Math.round(value).toLocaleString('pt-BR');
// Valores da API chegam como texto decimal ("14.0"); mostra no formato pt-BR.
const formatApi = (value) => (value == null || value === '' || Number.isNaN(Number(value))
  ? (value ?? '—') : Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 2 }));

function plot(chart, { min, max, ticks, line, quiet = [], band, capacity }) {
  const svg = chart.querySelector('svg');
  const x = (index, count) => (count === 1 ? PLOT_W : (index * PLOT_W) / (count - 1));
  const y = (value) => PLOT_H - ((value - min) / (max - min)) * PLOT_H;
  const points = (values) => values.map((value, index) => `${x(index, values.length)},${y(value)}`).join(' ');
  const shape = (tag, attrs) => {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  };
  const nodes = ticks.map((tick) => shape('line', { class: 'grid', x1: 0, x2: PLOT_W, y1: y(tick), y2: y(tick) }));
  if (band) {
    const upper = points(band.high);
    const lower = band.low.map((value, index) => `${x(index, band.low.length)},${y(value)}`).reverse().join(' ');
    nodes.push(shape('polygon', { class: 'band', points: `${upper} ${lower}` }));
  }
  if (capacity != null && line.length) {
    const top = points(line.map((value) => Math.max(value, capacity)));
    const base = line.map((_, index) => `${x(index, line.length)},${y(capacity)}`).reverse().join(' ');
    nodes.push(shape('polygon', { class: 'gap', points: `${top} ${base}` }));
    nodes.push(shape('line', { class: 'capacity', x1: 0, x2: PLOT_W, y1: y(capacity), y2: y(capacity) }));
  }
  quiet.forEach((values) => nodes.push(shape('polyline', { class: 'line line--quiet', points: points(values) })));
  if (line.length) nodes.push(shape('polyline', { class: 'line', points: points(line) }));
  svg.replaceChildren(...nodes);
  chart.querySelectorAll('.chart__y span').forEach((label) => {
    label.textContent = formatInt(max - (Number.parseFloat(label.style.top) / 100) * (max - min));
  });
  const dot = chart.querySelector('.chart__dot');
  dot.hidden = !line.length;
  if (line.length) {
    dot.style.left = '100%';
    dot.style.top = `${(y(line[line.length - 1]) / PLOT_H) * 100}%`;
  }
}

plot(document.querySelector('[data-chart="overview"]'), {
  min: 900, max: 1200, ticks: [900, 1000, 1100, 1200],
  line: [1060, 1085, 1120, 1150], capacity: CAPACITY,
});

const forecastData = {
  low: {
    label: 'baixa',
    values: ['1.050', '1.060', '1.075', '1.080'],
    heading: 'Mesmo com demanda baixa, confira o déficit por competência',
    copy: 'A faixa baixa reduz a pressão agregada, mas não mostra se os turnos e competências críticos estão cobertos.',
  },
  base: {
    label: 'provável',
    values: ['1.165', '1.180', '1.195', '1.200'],
    heading: 'A faixa provável mantém o déficit agregado',
    copy: 'Com 1.200 atendimentos projetados, o cálculo agregado em 42h equivale a cerca de 14 pessoas. A composição por competência segue pendente.',
  },
  high: {
    label: 'alta',
    values: ['1.265', '1.285', '1.305', '1.320'],
    heading: 'A demanda alta amplia a margem operacional necessária',
    copy: 'A faixa alta testa a robustez das alternativas. Sem dados por competência e turno, a Alinia não conclui uma composição de vagas.',
  },
};
const forecastChart = document.querySelector('[data-chart="forecast"]');
const forecastScale = { min: 900, max: 1350, ticks: [900, 1050, 1200, 1350] };

function showForecast(key) {
  const data = forecastData[key];
  const series = (name) => forecastData[name].values.map(toNumber);
  const last = data.values[data.values.length - 1];
  document.querySelectorAll('[data-forecast]').forEach((item) => item.setAttribute('aria-pressed', String(item.dataset.forecast === key)));
  document.querySelector('[data-forecast-value]').textContent = last;
  document.querySelector('[data-forecast-delta]').textContent = `+${formatInt(toNumber(last) - CAPACITY)} acima da capacidade em 42h`;
  document.querySelector('[data-forecast-heading]').textContent = data.heading;
  document.querySelector('[data-forecast-copy]').textContent = data.copy;
  data.values.forEach((value, index) => { document.querySelector(`[data-bar-label="${index}"]`).textContent = value; });
  plot(forecastChart, {
    ...forecastScale,
    line: series(key),
    quiet: Object.keys(forecastData).filter((name) => name !== key).map(series),
    capacity: CAPACITY,
  });
  forecastChart.setAttribute('aria-label', `Demanda projetada na faixa ${data.label}: ${data.values.join(', ')} atendimentos nas semanas 1 a 4, contra capacidade de cerca de 954`);
}

document.querySelectorAll('[data-forecast]').forEach((button) => {
  button.addEventListener('click', () => showForecast(button.dataset.forecast));
});
showForecast('base');

// Cinco famílias de cenário (A–E), na ordem do contrato do backend.
const scenarioData = {
  a: { head: 'A · Contratar', coverage: 'A validar por competência', timing: 'Após recrutamento e ramp-up', risk: 'Prazo de chegada, mentoria e cobertura N1', status: 'Condicional' },
  b: { head: 'B · Temporários', coverage: 'Não verificada', timing: 'Após contratação e treinamento', risk: 'Modalidade, custo e prazo', status: 'Exploratório' },
  c: { head: 'C · Realocar', coverage: 'A validar por competência', timing: 'Após formação e realocação', risk: 'Impacto na equipe de origem', status: 'Condicional' },
  d: { head: 'D · Redesenhar', coverage: 'Não verificada', timing: 'Depende da nova organização', risk: 'Repousos e cobertura obrigatória', status: 'Exploratório' },
  e: { head: 'E · Não agir', coverage: 'Gap agregado de 3 posições', timing: 'Imediato', risk: 'Backlog e pressão operacional', status: 'Referência' },
};
let selectedScenarios = ['a', 'c'];

function renderComparison() {
  document.querySelectorAll('[data-select-scenario]').forEach((button) => {
    const selected = selectedScenarios.includes(button.dataset.selectScenario);
    button.setAttribute('aria-pressed', String(selected));
    button.closest('.scenario-card').classList.toggle('is-selected', selected);
    button.querySelector('[data-select-label]').textContent = selected ? 'Na comparação' : 'Comparar';
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
  demanda: { title: 'Demanda atual', intro: 'Fonte ilustrativa do exemplo da Unidade Centro.', items: [['Arquivo', 'demanda_centro.csv'], ['Unidade', 'Atendimentos comparáveis por semana'], ['Valor atual', '1.150 atendimentos por semana'], ['Limitação', 'Não somar unidades de trabalho incomparáveis entre equipes.']] },
  jornada: { title: 'Premissa de jornada', intro: 'A jornada de 42h é usada apenas para simulação do exemplo.', items: [['Jornada simulada', '42 horas semanais'], ['Controle necessário', 'Confirmar categoria, vigência e instrumento coletivo aplicável com o RH/jurídico.'], ['Execução', 'Nenhuma alteração de escala ou ponto nesta demonstração.']] },
  calculo: { title: 'Cálculo agregado', intro: 'Capacidade da equipe como se todos fizessem o mesmo trabalho, a partir dos números do exemplo.', items: [['Entradas', '11 pessoas × 42h × 91% de disponibilidade × 2,27 atendimentos por hora'], ['Capacidade', 'Cerca de 954 atendimentos por semana'], ['Pressão de demanda (IPD)', '1.150 ÷ 954 ≈ 1,21'], ['Gap agregado', '3 posições para cobrir a demanda em 42h'], ['Limitação', 'Não distribui horas por competência ou turno e não define automaticamente as vagas.']] },
  skills: { title: 'Matriz de competências pendente', intro: 'O gap agregado não resolve a composição da equipe.', items: [['Dado necessário', 'Horas elegíveis por competência, turno e função.'], ['Risco', 'Contar a mesma hora em várias competências ou supor que três pessoas fecham qualquer gap N1.'], ['Próximo passo', 'Validar a matriz com RH e operação antes de otimizar a alocação.']] },
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
  if (session.token) {
    document.querySelector('[data-review-feedback]').textContent = 'A sessão está ligada. A decisão só aparece depois da resposta da API.';
    return;
  }
  event.currentTarget.textContent = 'Checklist preparado';
  event.currentTarget.disabled = true;
  document.querySelector('[data-review-feedback]').textContent = 'Checklist preparado nesta sessão. Nenhuma requisição foi criada.';
});

const connectDialog = document.querySelector('[data-connect-dialog]');
document.querySelectorAll('[data-connect-open]').forEach((button) => button.addEventListener('click', () => {
  closeMenu();
  connectDialog.showModal();
}));
document.querySelector('[data-connect-close]').addEventListener('click', () => connectDialog.close());
connectDialog.addEventListener('click', (event) => { if (event.target === connectDialog) connectDialog.close(); });

const session = { token: null, runId: null, scenarios: [], decisions: new Map(), approvedId: null, runs: [] };
const cardKind = { a: 'hire', b: 'temporary', c: 'reallocate', d: 'redesign', e: 'do_nothing' };
const kindTitle = { hire: 'Contratar', temporary: 'Temporários', reallocate: 'Realocar ou capacitar', redesign: 'Redesenhar', do_nothing: 'Não agir' };
const kindHeading = {
  hire: 'Contratar quadro permanente', temporary: 'Contratar temporariamente', reallocate: 'Realocar ou capacitar',
  redesign: 'Redesenhar turnos ou processos', do_nothing: 'Não agir',
};

const errorMessages = {
  NOT_CONCLUSIVE: 'o cenário não passou pela validação independente de cobertura obrigatória e não pode ser aprovado',
  NOT_APPROVED: 'o rascunho só pode ser pedido para um cenário aprovado',
  MATERIAL_CHANGE: 'o cenário mudou depois de carregado; recarregue antes de decidir',
  IDEMPOTENCY_CONFLICT: 'este cenário já tem outra decisão registrada',
  POLICY_REVIEW_REQUIRED: 'há regra ausente, em revisão ou revogada para este cenário',
  FORBIDDEN_SCOPE: 'seu perfil não tem permissão para esta equipe',
  NOT_FOUND: 'o recurso não foi encontrado',
  FORECAST_NOT_APPLIED: 'a previsão ainda não foi aplicada por competência e turno',
  LEGAL_CONTEXT_REQUIRED: 'o contexto jurídico da equipe precisa de validação',
};
const violationLabels = {
  MANDATORY_COVERAGE_MISSING: 'cobertura obrigatória não atendida',
  CAPACITY_ARRIVES_TOO_LATE: 'capacidade chega depois do pico',
  TRAINING_NOT_COMPLETED: 'habilitação não concluída',
  POLICY_REVIEW_REQUIRED: 'regra em revisão',
  BUDGET_NOT_APPROVED: 'orçamento não aprovado',
  MODALITY_REVIEW_REQUIRED: 'modalidade não validada',
  SCHEDULE_NOT_APPROVED: 'escala não aprovada',
  POOL_HOURS_EXCEEDED: 'horas acima do disponível',
  SKILL_OR_SHIFT_MISMATCH: 'competência ou turno incompatível',
  UNKNOWN_POOL: 'grupo de capacidade desconhecido',
  DUPLICATE_POOL: 'grupo de capacidade duplicado',
};

// A aprovação exige um resultado válido do validador determinístico v4.2;
// o campo `conclusive` sozinho não basta.
function validation(item) {
  const result = item.v42_validation;
  if (!result || typeof result !== 'object') return { ok: false, label: 'Não executada' };
  if (result.status === 'valid' && result.mandatory_coverage_met === true && !(result.violations || []).length) {
    return { ok: true, label: 'Válida' };
  }
  const reasons = (result.violations || []).map((code) => violationLabels[code] || code);
  return { ok: false, label: reasons.length ? `Bloqueada: ${reasons.join(', ')}` : 'Bloqueada' };
}

function scenarioStatus(item) {
  if (item.conclusive && validation(item).ok) return 'Elegível para revisão';
  return 'Inconclusivo';
}

function readableGap(value) {
  if (value.startsWith('FORECAST_NOT_APPLIED:')) return 'Previsão ainda não aplicada por competência e turno';
  if (value.startsWith('LEGAL_CONTEXT_REQUIRED:')) return 'Categoria, contrato e instrumento coletivo ainda não validados';
  if (value.startsWith('MANAGER_REPORT_UNVERIFIED:')) return 'Relato do gestor ainda não verificado';
  return value;
}

function errorText(error) {
  const detail = error.body && error.body.detail;
  const code = detail && (detail.code || (Array.isArray(detail) ? detail.map((item) => item.msg).join(' ') : null));
  return errorMessages[code] || code || error.message || 'A API não confirmou a operação';
}

async function api(path, options = {}) {
  const headers = { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(session.token ? { Authorization: `Bearer ${session.token}` } : {}) };
  const response = await fetch(path, { method: options.method || 'GET', headers, body: options.body ? JSON.stringify(options.body) : undefined });
  const text = await response.text();
  let body = null;
  if (text) body = JSON.parse(text);
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}

function setStatus(message) {
  document.querySelector('[data-connect-status]').textContent = message;
}

function fillSelect(select, items, label) {
  select.replaceChildren(...items.map((item) => {
    const option = document.createElement('option');
    option.value = item.value;
    option.textContent = item.label;
    return option;
  }));
  if (!items.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = label;
    select.append(option);
  }
}

async function loadSnapshots() {
  const teamId = document.querySelector('[data-team]').value;
  const rows = teamId ? await api(`/api/teams/${encodeURIComponent(teamId)}/snapshots`) : [];
  fillSelect(document.querySelector('[data-snapshot]'), rows.map((row) => ({
    value: row.snapshot_id,
    label: `${row.source.reference} · ${row.snapshot_id}`,
  })), 'Nenhum snapshot');
}

function refreshRunSelect() {
  const teamId = document.querySelector('[data-team]').value;
  const rows = session.runs.filter((run) => run.team_id === teamId);
  fillSelect(document.querySelector('[data-run-select]'), rows.map((run) => ({
    value: run.run_id,
    label: `${run.state} · ${run.snapshot_id} · ${new Date(run.updated_at).toLocaleString('pt-BR')}`,
  })), 'Nenhuma investigação desta equipe');
  document.querySelector('[data-resume-run]').disabled = rows.length === 0;
}

async function loadRuns() {
  try {
    const result = await api('/api/investigations');
    session.runs = result.items || [];
  } catch (error) {
    if (error.status !== 404) throw error;
    session.runs = [];
  }
  refreshRunSelect();
}

document.querySelector('[data-connect-form]').addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  setStatus('Conferindo credenciais…');
  try {
    const login = await api('/api/auth/login', {
      method: 'POST',
      body: { tenant_id: data.get('tenant_id'), email: data.get('email'), password: data.get('password') },
    });
    // A new login must never retain the previous user's investigation or decision.
    session.token = login.access_token;
    session.runs = [];
    resetLoadedInvestigation();
    const me = await api('/api/auth/me');
    const role = me.memberships[0] ? me.memberships[0].role : 'sem papel';
    const teams = await api('/api/teams');
    fillSelect(document.querySelector('[data-team]'), teams.map((team) => ({ value: team.id, label: team.name || team.id })), 'Nenhuma equipe com snapshot');
    await loadSnapshots();
    // Restore only the last investigation authorized by the API. Session
    // credentials are intentionally not persisted in browser storage.
    let restored = false;
    let restoreError = null;
    try {
      await loadRuns();
      const last = session.runs.find((item) => teams.some((team) => team.id === item.team_id));
      if (last) {
        document.querySelector('[data-team]').value = last.team_id;
        await loadSnapshots();
        refreshRunSelect();
        if ([...document.querySelector('[data-snapshot]').options].some((option) => option.value === last.snapshot_id)) {
          // Read-only restore: never advance the workflow without a user action.
          restored = await resumeRun(last, { advance: false });
        }
      }
    } catch (error) {
      // Failure to resume is not a failure to authenticate. The user can still
      // select a snapshot and open an investigation manually.
      restoreError = errorText(error);
    }
    document.querySelector('[data-live-controls]').hidden = false;
    if (restored) connectDialog.close();
    document.querySelector('[data-review-action]').hidden = true;
    document.querySelector('[data-decision-form]').hidden = false;
    document.querySelector('[data-review-copy]').textContent = 'Rejeitar ou adiar fica registrado depois que a API responder. Aprovar exige que o cenário tenha passado pela validação independente.';
    // Ao restaurar, o banner já descreve a investigação carregada por paintRun().
    if (!restored) document.querySelector('[data-banner-copy]').textContent = `Conectado como ${role}. Os números de exemplo ficam até você carregar um recorte`;
    document.querySelector('[data-sidebar-status]').textContent = 'Conectado à API';
    document.querySelector('[data-connect-form]').hidden = true;
    if (restored) setStatus('Investigação anterior recuperada da API. Confira as evidências antes de decidir.');
    else if (restoreError) setStatus(`Sessão aberta; não foi possível restaurar a investigação: ${restoreError}`);
    else if (teams.length) setStatus('Sessão aberta. Escolha a equipe e o recorte.');
    else setStatus('Sessão aberta, mas esta empresa ainda não tem recorte de dados.');
  } catch (error) {
    session.token = null;
    setStatus(`Não foi possível entrar: ${errorText(error)}`);
  }
});

function resetLoadedInvestigation() {
  session.runId = null;
  session.scenarios = [];
  session.decisions = new Map();
  session.approvedId = null;
  document.querySelector('[data-draft]').hidden = true;
  document.querySelector('[data-review-feedback]').textContent = '';
  fillSelect(document.querySelector('[data-decision-scenario]'), [], 'Nenhum cenário carregado');
  document.querySelector('[data-review="validation"]').textContent = 'Não executada neste recorte';
  syncApproval();
}

document.querySelector('[data-team]').addEventListener('change', () => {
  resetLoadedInvestigation();
  refreshRunSelect();
  loadSnapshots().catch((error) => setStatus(errorText(error)));
});
document.querySelector('[data-snapshot]').addEventListener('change', resetLoadedInvestigation);

function renderDemandFlow(flow) {
  const panel = document.querySelector('[data-demand-flow-panel]');
  const grid = document.querySelector('[data-demand-flow-grid]');
  const note = document.querySelector('[data-demand-flow-note]');
  panel.hidden = false;
  const rows = flow?.items || [];
  const latest = rows.at(-1);
  const classified = latest?.demand_semantics === 'incoming_plus_unmet';
  const fields = classified ? [
    ['Entradas', latest.incoming_cases], ['Concluídos', latest.completed_cases],
    ['Backlog inicial', latest.backlog_start], ['Backlog final', latest.backlog_end],
    ['Cancelados', latest.cancelled_cases], ['Reabertos', latest.reopened_cases],
    ['Demanda não registrada', latest.unmet_cases],
  ] : [['Fluxo de demanda', 'Não classificado neste recorte']];
  grid.replaceChildren(...fields.map(([label, value]) => {
    const cell = document.createElement('div');
    const name = document.createElement('span');
    const number = document.createElement('strong');
    name.textContent = label;
    number.textContent = classified ? formatApi(value) : value;
    cell.append(name, number);
    return cell;
  }));
  note.textContent = latest
    ? `${latest.start} a ${latest.end}. ${(flow.limitations || []).join(' ')}${classified ? '' : ' A quantidade legada não comprova entradas, conclusões ou backlog.'}`
    : 'Não há fluxo de entradas e backlog associado a este snapshot.';
}

// Visão geral no modo conectado: a demanda vem da série por período do
// demand-flow; a capacidade é a do bloco homogêneo do último período, repetida
// só como referência. Sem série suficiente, o gráfico continua ilustrativo.
const OVERVIEW_PERIODS = 6;
function renderOverviewChart(flow, block) {
  const chart = document.querySelector('[data-chart="overview"]');
  const foot = document.querySelector('[data-overview-chart-foot]');
  const rows = (flow?.items || []).filter((item) => item.quantity != null && Number.isFinite(Number(item.quantity))).slice(-OVERVIEW_PERIODS);
  if (rows.length < 2) {
    foot.textContent = 'Série ilustrativa: este recorte não tem histórico suficiente para desenhar a demanda';
    return;
  }
  const line = rows.map((item) => Number(item.quantity));
  const capacity = block && Number.isFinite(Number(block.capacity_cases)) ? Number(block.capacity_cases) : null;
  const known = capacity == null ? line : [...line, capacity];
  // Três intervalos de passo "redondo" (1, 2, 2,5 ou 5 × 10ⁿ) cobrindo os valores com folga.
  const low = Math.min(...known);
  const high = Math.max(...known);
  const raw = Math.max((high - low) * 1.2, high * 0.02, 1) / 3;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  let step = [1, 2, 2.5, 5, 10].map((factor) => factor * magnitude).find((value) => value >= raw);
  let min = Math.floor(low / step) * step;
  while (min + 3 * step < high) {
    step *= 2;
    min = Math.floor(low / step) * step;
  }
  const max = min + 3 * step;
  plot(chart, {
    min, max, ticks: [0, 1, 2, 3].map((index) => min + index * step),
    line, capacity: capacity ?? undefined,
  });
  const day = (value) => String(value).slice(0, 10).split('-').reverse().slice(0, 2).join('/');
  chart.querySelector('.chart__x').replaceChildren(...rows.map((item) => {
    const label = document.createElement('span');
    label.textContent = day(item.start);
    return label;
  }));
  const values = line.map(formatInt).join(', ');
  chart.setAttribute('aria-label', `Demanda registrada nos últimos ${rows.length} períodos do recorte: ${values}${capacity == null ? '' : `, contra capacidade de cerca de ${formatInt(capacity)}`}`);
  document.querySelector('[data-overview-chart-sub]').textContent = `Casos por período nos últimos ${rows.length} períodos do recorte`;
  document.querySelector('[data-overview-capacity-label]').textContent = 'Capacidade do último período';
  foot.textContent = capacity == null
    ? 'Demanda do CSV do recorte. Sem bloco homogêneo, a capacidade não é desenhada'
    : 'Demanda do CSV do recorte. A capacidade é a do último período, repetida como referência; não há histórico de capacidade';
}

async function loadMetrics(teamId, snapshotId, { closeDialog = true } = {}) {
  if (!teamId || !snapshotId) {
    setStatus('Não há snapshot para carregar.');
    return;
  }
  setStatus('Carregando métricas…');
  try {
    const metrics = await api(`/api/teams/${encodeURIComponent(teamId)}/metrics?snapshot_id=${encodeURIComponent(snapshotId)}`);
    const demandRows = metrics.demand.filter((item) => item.quantity != null);
    const demand = demandRows.length ? demandRows.reduce((total, item) => total + Number(item.quantity), 0) : null;
    let flow = null;
    try {
      flow = await api(`/api/teams/${encodeURIComponent(teamId)}/demand-flow?snapshot_id=${encodeURIComponent(snapshotId)}`);
    } catch (error) {
      if (error.status !== 404) throw error;
    }
    renderDemandFlow(flow);
    const block = metrics.homogeneous;
    document.querySelector('[data-live="demand"]').textContent = demand == null ? '—' : formatApi(demand);
    document.querySelector('[data-live-meta="demand"]').textContent = demand == null ? 'demanda ausente no snapshot' : 'quantidade agregada do snapshot';
    document.querySelector('[data-live="capacity"]').textContent = block ? formatApi(block.capacity_cases) : (metrics.pool_hours ? formatApi(metrics.pool_hours) : '—');
    document.querySelector('[data-live-meta="capacity"]').textContent = block ? 'capacidade do bloco homogêneo' : 'horas de pool, contadas uma vez';
    document.querySelector('[data-live="ipd"]').textContent = block ? formatApi(block.ipd) : '—';
    document.querySelector('[data-live-meta="ipd"]').textContent = block ? 'calculado dos agregados do arquivo' : 'sem bloco homogêneo neste snapshot';
    document.querySelector('[data-live="gap"]').textContent = block && block.headcount_gap != null ? String(block.headcount_gap) : '—';
    document.querySelector('[data-live-meta="gap"]').textContent = block ? `quadro de referência ${block.required_headcount}` : 'gap não calculado';
    const teamSelect = document.querySelector('[data-team]');
    const teamName = teamSelect.selectedOptions[0] ? teamSelect.selectedOptions[0].textContent : teamId;
    document.querySelector('[data-unit-name]').textContent = teamName;
    document.querySelector('[data-unit-crumb]').textContent = teamName;
    document.querySelector('[data-unit-meta]').textContent = `Recorte ${snapshotId}`;
    document.querySelector('[data-review="capacity"]').textContent = block ? `${formatApi(block.capacity_cases)} por semana` : 'Não calculada';
    document.querySelector('[data-review="source"]').textContent = `Recorte ${snapshotId}`;
    const ipd = block ? Number.parseFloat(block.ipd) : Number.NaN;
    const share = Math.round(Math.abs(ipd - 1) * 100);
    document.querySelector('[data-overview-title]').textContent = Number.isFinite(ipd)
      ? (share === 0 ? 'A demanda está no nível da capacidade' : `A demanda está ${share}% ${ipd > 1 ? 'acima' : 'abaixo'} da capacidade`)
      : 'Demanda e capacidade do recorte';
    document.querySelector('[data-banner-copy]').textContent = `Visão geral do recorte ${snapshotId}. As demais etapas só usam dados da API depois de abrir ou retomar uma investigação. ${metrics.limitations.join(' ')}`;
    setStatus('Métricas carregadas da API.');
    renderOverviewChart(flow, block);
    if (closeDialog) connectDialog.close();
    location.hash = '#visao-geral';
    return true;
  } catch (error) {
    setStatus(`Métricas não carregadas: ${errorText(error)}`);
    return false;
  }
}

document.querySelector('[data-load-metrics]').addEventListener('click', () => {
  loadMetrics(document.querySelector('[data-team]').value, document.querySelector('[data-snapshot]').value);
});

function renderReport(run) {
  const report = run.report;
  if (!report) return;
  document.querySelector('[data-trigger]').textContent = report.trigger;
  document.querySelector('[data-trigger-meta]').textContent = `${run.team_id} · ${run.state} · ciclo ${run.cycle_count}/${run.cycle_limit}`;
  const panel = document.querySelector('[data-hypothesis-panel]');
  panel.querySelectorAll('.hypothesis').forEach((node) => node.remove());
  report.hypotheses.forEach((item, index) => {
    const row = document.createElement('div');
    row.className = 'hypothesis';
    const number = document.createElement('span');
    number.className = 'hypothesis__number';
    number.textContent = String(index + 1).padStart(2, '0');
    const body = document.createElement('div');
    const top = document.createElement('div');
    top.className = 'hypothesis__top';
    const title = document.createElement('strong');
    title.textContent = item.statement;
    const pill = document.createElement('span');
    pill.className = `status-pill ${item.verification === 'supported' ? 'status-pill--supported' : 'status-pill--pending'}`;
    pill.textContent = item.verification === 'supported' ? 'Sustentada' : 'Não verificada';
    top.append(title, pill);
    body.append(top);
    row.append(number, body);
    panel.append(row);
  });
  document.querySelector('[data-hypothesis-count]').textContent = `${report.hypotheses.length} da API`;
  document.querySelector('[data-limitations]').textContent = report.limitations.join(' ');
  const list = document.querySelector('[data-question-list]');
  list.replaceChildren();
  const pending = report.questions.filter((item) => item.status === 'pending');
  document.querySelector('[data-question-copy]').hidden = pending.length > 0;
  document.querySelector('[data-question-status]').textContent = pending.length ? `${pending.length} pendente(s)` : 'Sem pergunta pendente';
  document.querySelector('[data-step-meta="investigacao"]').textContent = pending.length ? `${pending.length} pergunta${pending.length === 1 ? '' : 's'}` : '';
  pending.forEach((question) => {
    const form = document.createElement('form');
    form.className = 'question-form';
    const text = document.createElement('p');
    text.textContent = question.text;
    const input = document.createElement('input');
    input.name = 'answer';
    input.required = true;
    input.maxLength = 2000;
    const button = document.createElement('button');
    button.className = 'button';
    button.type = 'submit';
    button.textContent = 'Enviar resposta';
    form.append(text, input, button);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      button.disabled = true;
      try {
        await api(`/api/investigations/${session.runId}/answers`, {
          method: 'POST',
          body: { question_id: question.question_id, answer: new FormData(form).get('answer'), idempotency_key: `${session.runId}-${question.question_id}` },
        });
        const current = await api(`/api/investigations/${session.runId}`);
        if (current.report.questions.some((item) => item.status === 'pending')) renderReport(current);
        else await paintRun(await api(`/api/investigations/${session.runId}/advance`, { method: 'POST' }));
      } catch (error) {
        button.disabled = false;
        setStatus(`Resposta não registrada: ${errorText(error)}`);
      }
    });
    list.append(form);
  });
}

function renderForecast(forecast) {
  if (!forecast) return;
  document.querySelector('[data-forecast-switch]').hidden = true;
  const statusLabel = { calibrated: 'Faixa validada', uncalibrated: 'Sem faixa validada', abstained: 'Previsão abstida' };
  const label = statusLabel[forecast.status] || forecast.status;
  document.querySelector('[data-forecast-status]').textContent = label;
  document.querySelector('[data-method="model"]').textContent = forecast.method === 'moving_median_4' ? 'Mediana móvel de 4 semanas' : forecast.method;
  document.querySelector('[data-method="backtest"]').textContent = forecast.backtest ? `MAE ${forecast.backtest.mae}` : 'Sem backtest';
  document.querySelector('[data-method="confidence"]').textContent = label;
  document.querySelector('[data-review="quality"]').textContent = label;
  const points = (forecast.points || []).slice(0, 4);
  const number = (value) => (value == null ? null : Number(value));
  const estimates = points.map((point) => number(point.point_estimate));
  const lower = points.map((point) => number(point.lower));
  const upper = points.map((point) => number(point.upper));
  const complete = (values) => values.length > 0 && values.every((value) => value != null);
  const last = estimates[estimates.length - 1];
  document.querySelector('[data-forecast-value]').textContent = last == null ? '—' : formatInt(last);
  document.querySelector('[data-review="demand"]').textContent = last == null ? 'Sem estimativa' : `${formatInt(last)} por semana`;
  document.querySelector('[data-forecast-heading]').textContent = forecast.status === 'abstained' ? 'A previsão se absteve' : 'Estimativa pontual da mediana móvel';
  document.querySelector('[data-forecast-copy]').textContent = (forecast.limitations || []).join(' ');
  document.querySelector('[data-forecast-delta]').textContent = complete(lower) && complete(upper)
    ? `Faixa de ${formatInt(lower[lower.length - 1])} a ${formatInt(upper[upper.length - 1])} na semana 4`
    : '';
  document.querySelector('[data-forecast-foot]').textContent = forecast.interval_description
    || 'Sem faixa validada para esta equipe. O gráfico mostra só a estimativa pontual quando ela existe';
  document.querySelectorAll('[data-bar-label]').forEach((item, index) => {
    item.textContent = estimates[index] == null ? '—' : formatInt(estimates[index]);
  });
  const band = complete(lower) && complete(upper) ? { low: lower, high: upper } : null;
  const known = [...estimates, ...(band ? [...lower, ...upper] : [])].filter((value) => value != null);
  const min = Math.floor(Math.min(...known, 900) / 50) * 50;
  const max = Math.ceil(Math.max(...known, 1350) / 50) * 50;
  plot(forecastChart, { min, max, ticks: [min, max], line: complete(estimates) ? estimates : [], band });
}

function renderScenarios(items) {
  session.scenarios = items;
  items.forEach((item) => {
    const key = Object.keys(cardKind).find((candidate) => cardKind[candidate] === item.kind);
    const card = document.querySelector(`[data-scenario="${key}"]`);
    if (!card) return;
    const check = validation(item);
    const flags = item.legal_flags || [];
    card.querySelector('h2').textContent = kindHeading[item.kind];
    card.querySelector('.scenario-card__main > p').textContent = readableGap(flags[0] || item.gaps[0] || item.dependencies?.[0] || item.assumptions[0] || '');
    const status = card.querySelector('[data-scenario-status]');
    status.textContent = scenarioStatus(item);
    status.className = `status-pill ${item.kind === 'do_nothing' ? 'status-pill--reference' : 'status-pill--pending'}`;
    card.querySelector('.scenario-card__facts').replaceChildren(...[
      ['Headcount', item.headcount_delta == null ? 'Não calculado' : String(item.headcount_delta)],
      ['Déficit residual', item.residual_hours == null ? 'Não simulado' : `${item.residual_hours} h`],
      ['Custo', item.costs_estimated ? 'Estimado' : 'Não estimado'],
      ['Validação independente', check.label],
    ].map(([name, value]) => {
      const row = document.createElement('div');
      const term = document.createElement('span');
      const data = document.createElement('strong');
      term.textContent = name;
      data.textContent = value;
      row.append(term, data);
      return row;
    }));
    scenarioData[key] = {
      head: `${key.toUpperCase()} · ${kindTitle[item.kind]}`,
      coverage: check.ok ? 'Validada de forma independente' : check.label,
      timing: item.lead_time_and_ramp_up ? 'Prazo de chegada informado' : 'Prazo de chegada não informado',
      risk: readableGap(flags[0] || item.gaps[0] || item.dependencies?.[0] || 'Sem lacuna declarada'),
      status: scenarioStatus(item),
    };
  });
  renderComparison();
  const validated = items.filter((item) => validation(item).ok).length;
  document.querySelector('[data-step-meta="cenarios"]').textContent = String(items.length);
  document.querySelector('[data-review="validation"]').textContent = validated ? `${validated} de ${items.length} cenários validados` : 'Não executada';
  const hire = items.find((item) => item.kind === 'hire');
  document.querySelector('[data-review-lead]').textContent = hire
    ? `Cenário de contratação na versão ${hire.version}: ${scenarioStatus(hire).toLowerCase()}${hire.headcount_delta == null ? ', sem headcount calculado' : `, headcount agregado ${hire.headcount_delta}`}. ${readableGap(hire.gaps[0] || hire.dependencies?.[0] || hire.assumptions[0] || '')}`
    : 'A API não devolveu um cenário de contratação.';
  const select = document.querySelector('[data-decision-scenario]');
  fillSelect(select, items.map((item) => ({
    value: item.scenario_id,
    label: `${kindTitle[item.kind]} · versão ${item.version} · ${scenarioStatus(item).toLowerCase()}`,
  })), 'Nenhum cenário');
  syncApproval();
}

// Aprovar só fica disponível para cenário com validação independente válida.
function syncApproval() {
  const selectedId = document.querySelector('[data-decision-scenario]').value;
  const scenario = session.scenarios.find((item) => item.scenario_id === selectedId);
  const recorded = session.decisions.get(selectedId);
  const ok = Boolean(scenario) && scenario.conclusive === true && validation(scenario).ok;
  document.querySelectorAll('[data-decision-form] button[type="submit"]').forEach((button) => {
    button.disabled = Boolean(recorded) || (button.value === 'approve' && !ok);
  });
  document.querySelector('[data-approve-hint]').hidden = ok && !recorded;
  document.querySelector('[data-approve-hint]').textContent = recorded
    ? `Decisão ${recorded.decision} já registrada para esta versão do cenário.`
    : scenario
    ? `Aprovação bloqueada: ${scenario.conclusive ? validation(scenario).label : readableGap(scenario.gaps[0] || scenario.dependencies?.[0] || 'simulação inconclusiva')}.`
    : 'Carregue um cenário da API antes de aprovar.';
  if (recorded) document.querySelector('[data-review-feedback]').textContent = `Decisão ${recorded.decision} registrada (${recorded.decision_id}).`;
}
document.querySelector('[data-decision-scenario]').addEventListener('change', syncApproval);

async function paintRun(run) {
  if (session.runId !== run.run_id) {
    session.scenarios = [];
    session.decisions = new Map();
    session.approvedId = null;
    document.querySelector('[data-draft]').hidden = true;
    document.querySelector('[data-review-feedback]').textContent = '';
    fillSelect(document.querySelector('[data-decision-scenario]'), [], 'Cenários ainda não disponíveis');
    syncApproval();
  }
  session.runId = run.run_id;
  renderReport(run);
  renderForecast(run.forecast);
  if (run.state === 'AWAITING_HUMAN' || run.state === 'COMPLETED') {
    const scenarios = await api(`/api/investigations/${run.run_id}/scenarios`);
    const details = await Promise.allSettled(scenarios.items.map((item) => api(`/api/scenarios/${encodeURIComponent(item.scenario_id)}`)));
    session.decisions = new Map(details.flatMap((result, index) =>
      result.status === 'fulfilled' && result.value.decision ? [[scenarios.items[index].scenario_id, result.value.decision]] : []));
    session.approvedId = [...session.decisions].find(([, record]) => record.decision === 'approve')?.[0] || null;
    document.querySelector('[data-draft]').hidden = !session.approvedId;
    renderScenarios(scenarios.items);
    setStatus(`Investigação em ${run.state}, ciclo ${run.cycle_count}. Cenários da versão atual carregados da API.`);
    document.querySelector('[data-banner-copy]').textContent = `Investigação ${run.run_id} · recorte ${run.snapshot_id} · ciclo ${run.cycle_count}. Os cenários mostrados são os da versão atual do ciclo.`;
    if (location.hash !== '#cenarios' && location.hash !== '#revisao') location.hash = '#cenarios';
  } else {
    setStatus(run.failure ? `Investigação ${run.state}: ${run.failure}.` : `Investigação em ${run.state}. Responda as perguntas pendentes para continuar.`);
    if (location.hash !== '#investigacao') location.hash = '#investigacao';
  }
}

document.querySelector('[data-open-investigation]').addEventListener('click', async () => {
  const teamId = document.querySelector('[data-team]').value;
  const snapshotId = document.querySelector('[data-snapshot]').value;
  if (!teamId || !snapshotId) {
    setStatus('Escolha um snapshot antes de investigar.');
    return;
  }
  setStatus('Abrindo investigação…');
  try {
    const opened = await api('/api/investigations', {
      method: 'POST',
      body: { team_id: teamId, snapshot_id: snapshotId, idempotency_key: `ui-${teamId}-${snapshotId}`, cycle_limit: 3 },
    });
    connectDialog.close();
    await paintRun(await api(`/api/investigations/${opened.run_id}/advance`, { method: 'POST' }));
    await loadRuns();
  } catch (error) {
    setStatus(`Investigação não aberta: ${errorText(error)}`);
  }
});

document.querySelector('[data-run-select]').addEventListener('change', (event) => {
  document.querySelector('[data-resume-run]').disabled = !event.currentTarget.value;
});

// Carrega o recorte e a investigação escolhidos. `advance` só é usado quando
// a pessoa pede a retomada; a restauração automática no login é só leitura.
async function resumeRun(selected, { advance = true } = {}) {
  document.querySelector('[data-snapshot]').value = selected.snapshot_id;
  document.querySelector('[data-run-select]').value = selected.run_id;
  if (!await loadMetrics(selected.team_id, selected.snapshot_id, { closeDialog: false })) return false;
  const path = `/api/investigations/${encodeURIComponent(selected.run_id)}`;
  let run = await api(path);
  if (advance && !['WAITING_INPUT', 'AWAITING_HUMAN', 'COMPLETED', 'FAILED', 'BLOCKED'].includes(run.state)) {
    run = await api(`${path}/advance`, { method: 'POST' });
  }
  await paintRun(run);
  return true;
}

document.querySelector('[data-resume-run]').addEventListener('click', async (event) => {
  // currentTarget vira null depois do primeiro await; guarde o botão antes.
  const button = event.currentTarget;
  const selected = session.runs.find((run) => run.run_id === document.querySelector('[data-run-select]').value);
  if (!selected) return;
  button.disabled = true;
  setStatus('Retomando investigação…');
  try {
    if (await resumeRun(selected)) connectDialog.close();
  } catch (error) {
    setStatus(`Investigação não retomada: ${errorText(error)}`);
  } finally {
    button.disabled = false;
  }
});

document.querySelector('[data-decision-form]').addEventListener('submit', async (event) => {
  event.preventDefault();
  const submitter = event.submitter;
  const decision = submitter ? submitter.value : 'defer';
  const scenarioId = document.querySelector('[data-decision-scenario]').value;
  const scenario = session.scenarios.find((item) => item.scenario_id === scenarioId);
  const feedback = document.querySelector('[data-review-feedback]');
  if (!scenario) {
    feedback.textContent = 'Não há cenário carregado. Nada foi registrado.';
    return;
  }
  feedback.textContent = 'Enviando decisão…';
  submitter.disabled = true;
  try {
    const stored = await api(`/api/scenarios/${scenarioId}/decisions`, {
      method: 'POST',
      body: {
        decision, reason: new FormData(event.currentTarget).get('reason'), expected_hash: scenario.content_hash,
        idempotency_key: `ui-${scenarioId}-${decision}-${scenario.content_hash.slice(0, 12)}`,
      },
    });
    feedback.textContent = `Decisão ${stored.decision} registrada (${stored.decision_id}). executed=${stored.executed}.`;
    session.decisions.set(scenarioId, stored);
    if (stored.decision === 'approve') {
      session.approvedId = scenarioId;
      document.querySelector('[data-draft]').hidden = false;
    }
  } catch (error) {
    feedback.textContent = `A API não registrou a decisão: ${errorText(error)}.`;
  } finally {
    submitter.disabled = false;
    syncApproval();
  }
});

document.querySelector('[data-draft]').addEventListener('click', async (event) => {
  const feedback = document.querySelector('[data-review-feedback]');
  if (!session.approvedId) {
    feedback.textContent = 'O rascunho só é pedido depois de uma aprovação confirmada.';
    return;
  }
  event.currentTarget.disabled = true;
  feedback.textContent = 'Pedindo rascunho…';
  try {
    const draft = await api(`/api/scenarios/${session.approvedId}/requisition-drafts`, {
      method: 'POST',
      body: { idempotency_key: `ui-draft-${session.approvedId}` },
    });
    feedback.textContent = `Rascunho ${draft.draft_id} criado. executed=${draft.executed}. Sem efeito administrativo.`;
  } catch (error) {
    event.currentTarget.disabled = false;
    feedback.textContent = `Rascunho não criado: ${errorText(error)}.`;
  }
});
