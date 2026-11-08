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
  if (session.token) {
    document.querySelector('[data-review-feedback]').textContent = 'A sessão está ligada. A decisão só aparece depois da resposta da API.';
    return;
  }
  event.currentTarget.textContent = 'Checklist preparado ✓';
  event.currentTarget.disabled = true;
  document.querySelector('[data-review-feedback]').textContent = 'Checklist preparado nesta sessão. Nenhuma requisição foi criada.';
});

const session = { token: null, runId: null, scenarios: [], approvedId: null };
const cardKind = { a: 'hire', c: 'reallocate', e: 'do_nothing' };
const kindTitle = { hire: 'Contratar', reallocate: 'Realocar', do_nothing: 'Não agir' };

function errorText(error) {
  const detail = error.body && error.body.detail;
  const code = detail && (detail.code || (Array.isArray(detail) ? detail.map((item) => item.msg).join(' ') : null));
  return code || error.message || 'A API não confirmou a operação.';
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

document.querySelector('[data-connect-form]').addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  setStatus('Conferindo credenciais…');
  try {
    const login = await api('/api/auth/login', {
      method: 'POST',
      body: { tenant_id: data.get('tenant_id'), email: data.get('email'), password: data.get('password') },
    });
    session.token = login.access_token;
    const me = await api('/api/auth/me');
    const role = me.memberships[0] ? me.memberships[0].role : 'sem papel';
    const teams = await api('/api/teams');
    fillSelect(document.querySelector('[data-team]'), teams.map((team) => ({ value: team.id, label: team.name || team.id })), 'Nenhuma equipe com snapshot');
    await loadSnapshots();
    document.querySelector('[data-live-controls]').hidden = false;
    document.querySelector('[data-review-action]').hidden = true;
    document.querySelector('[data-decision-form]').hidden = false;
    document.querySelector('[data-review-copy]').textContent = 'Rejeitar, adiar ou aprovar só muda de estado depois que a API responder. Aprovar um cenário inconclusivo não é registrado.';
    document.querySelector('[data-banner-copy]').textContent = `Ligado como ${role}. Números ilustrativos permanecem até o carregamento de um snapshot.`;
    document.querySelector('[data-sidebar-status]').textContent = 'Ligado à API';
    setStatus(teams.length ? 'Sessão aberta. Escolha a equipe e carregue as métricas.' : 'Sessão aberta, mas esta empresa ainda não tem snapshot.');
  } catch (error) {
    session.token = null;
    setStatus(`Não foi possível entrar: ${errorText(error)}`);
  }
});

document.querySelector('[data-team]').addEventListener('change', () => {
  loadSnapshots().catch((error) => setStatus(errorText(error)));
});

document.querySelector('[data-load-metrics]').addEventListener('click', async () => {
  const teamId = document.querySelector('[data-team]').value;
  const snapshotId = document.querySelector('[data-snapshot]').value;
  if (!teamId || !snapshotId) {
    setStatus('Não há snapshot para carregar.');
    return;
  }
  setStatus('Carregando métricas…');
  try {
    const metrics = await api(`/api/teams/${encodeURIComponent(teamId)}/metrics?snapshot_id=${encodeURIComponent(snapshotId)}`);
    const demand = metrics.demand.find((item) => item.quantity != null);
    const block = metrics.homogeneous;
    document.querySelector('[data-live="demand"]').textContent = demand ? demand.quantity : '—';
    document.querySelector('[data-live-meta="demand"]').textContent = demand ? 'quantidade do snapshot' : 'demanda ausente no snapshot';
    document.querySelector('[data-live="capacity"]').textContent = block ? block.capacity_cases : (metrics.pool_hours || '—');
    document.querySelector('[data-live-meta="capacity"]').textContent = block ? 'capacidade do bloco homogêneo' : 'horas de pool, contadas uma vez';
    document.querySelector('[data-live="ipd"]').textContent = block ? block.ipd : '—';
    document.querySelector('[data-live-meta="ipd"]').textContent = block ? 'calculado dos agregados do arquivo' : 'sem bloco homogêneo neste snapshot';
    document.querySelector('[data-live="gap"]').textContent = block && block.headcount_gap != null ? String(block.headcount_gap) : '—';
    document.querySelector('[data-live-meta="gap"]').textContent = block ? `quadro de referência ${block.required_headcount}` : 'gap não calculado';
    document.querySelector('[data-banner-copy]').textContent = `Métricas do snapshot ${snapshotId}. ${metrics.limitations.join(' ')}`;
    setStatus('Métricas carregadas da API.');
  } catch (error) {
    setStatus(`Métricas não carregadas: ${errorText(error)}`);
  }
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
  document.querySelector('[data-forecast-status]').textContent = forecast.status;
  document.querySelector('[data-method="model"]').textContent = forecast.method;
  document.querySelector('[data-method="backtest"]').textContent = forecast.backtest ? `MAE ${forecast.backtest.mae}` : 'Sem backtest';
  document.querySelector('[data-method="confidence"]').textContent = forecast.status;
  const points = forecast.points || [];
  const estimate = points[0] && points[0].point_estimate != null ? String(points[0].point_estimate) : '—';
  document.querySelector('[data-forecast-value]').textContent = estimate;
  document.querySelector('[data-forecast-heading]').textContent = forecast.status === 'abstained' ? 'A previsão se absteve.' : 'Estimativa pontual da mediana móvel.';
  document.querySelector('[data-forecast-copy]').textContent = (forecast.limitations || []).join(' ');
  document.querySelector('[data-forecast-foot]').textContent = 'A API não devolve P10, P50 ou P90. Barras abaixo repetem a estimativa pontual quando ela existe.';
  points.slice(0, 4).forEach((point, index) => {
    const bar = document.querySelector(`[data-bar="${index}"]`);
    const label = document.querySelector(`[data-bar-label="${index}"]`);
    if (!bar || !label || point.point_estimate == null) return;
    label.textContent = String(point.point_estimate);
    bar.style.setProperty('--bar', '70%');
  });
  if (!points.length) {
    document.querySelectorAll('[data-bar-label]').forEach((label) => { label.textContent = '—'; });
  }
}

function renderScenarios(items) {
  session.scenarios = items;
  items.forEach((item) => {
    const key = Object.keys(cardKind).find((candidate) => cardKind[candidate] === item.kind);
    const card = document.querySelector(`[data-scenario="${key}"]`);
    if (!card) return;
    card.querySelector('h2').textContent = kindTitle[item.kind];
    card.querySelector(':scope > p').textContent = item.assumptions[0] || item.gaps[0] || item.kind;
    const facts = card.querySelectorAll('.scenario-card__facts strong');
    facts[0].textContent = item.conclusive ? 'Conclusivo' : 'Inconclusivo';
    facts[1].textContent = item.headcount_delta == null ? 'Não calculado' : String(item.headcount_delta);
    facts[2].textContent = item.residual_hours == null ? 'Sem resíduo' : `${item.residual_hours} h`;
    scenarioData[key] = {
      head: `${key.toUpperCase()} · ${kindTitle[item.kind]}`,
      coverage: item.conclusive ? 'Solver e política permitiram concluir' : 'Inconclusivo',
      timing: item.kind,
      risk: item.gaps[0] || 'Sem lacuna declarada',
      status: item.conclusive ? 'Conclusivo' : 'Inconclusivo',
    };
  });
  renderComparison();
  const hire = items.find((item) => item.kind === 'hire');
  document.querySelector('[data-review-lead]').textContent = hire
    ? `Cenário de contratação ${hire.conclusive ? 'conclusivo' : 'inconclusivo'}${hire.headcount_delta == null ? ', sem headcount calculado' : `, headcount ${hire.headcount_delta}`}. ${hire.assumptions[0] || ''}`
    : 'A API não devolveu um cenário de contratação.';
  const select = document.querySelector('[data-decision-scenario]');
  fillSelect(select, items.map((item) => ({ value: item.scenario_id, label: `${kindTitle[item.kind]} · ${item.conclusive ? 'conclusivo' : 'inconclusivo'}` })), 'Nenhum cenário');
}

async function paintRun(run) {
  session.runId = run.run_id;
  renderReport(run);
  renderForecast(run.forecast);
  if (run.state === 'AWAITING_HUMAN' || run.state === 'COMPLETED') {
    const scenarios = await api(`/api/investigations/${run.run_id}/scenarios`);
    renderScenarios(scenarios.items);
    setStatus(`Investigação em ${run.state}. Os cenários vieram da API.`);
    if (location.hash !== '#cenarios' && location.hash !== '#revisao') location.hash = '#cenarios';
  } else {
    setStatus(`Investigação em ${run.state}. Responda as perguntas pendentes para continuar.`);
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
    await paintRun(await api(`/api/investigations/${opened.run_id}/advance`, { method: 'POST' }));
  } catch (error) {
    setStatus(`Investigação não aberta: ${errorText(error)}`);
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
    if (stored.decision === 'approve') {
      session.approvedId = scenarioId;
      document.querySelector('[data-draft]').hidden = false;
    }
  } catch (error) {
    feedback.textContent = `A API não registrou a decisão: ${errorText(error)}.`;
  } finally {
    submitter.disabled = false;
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
