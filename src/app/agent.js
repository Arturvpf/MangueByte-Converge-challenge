/* ==========================================================================
   Alinia — interface de conversa com o agente.

   O modelo de linguagem do agente ainda não está ligado (ver a branch
   agent/alinia-investigator). Até lá, cada pergunta é encaminhada a uma
   ferramenta fixa:
   - conectado: as ferramentas leem e registram pela API, e cada número leva o
     selo da fonte;
   - sem conexão: a conversa é uma simulação com os dados de exemplo da
     Unidade Centro, e a interface diz isso.
   A interface não muda quando o modelo entrar: ele passa a escolher a
   ferramenta e a redigir o texto, e os passos e as fontes continuam visíveis.

   Regras que esta tela não quebra:
   - todo texto vindo de dados ou do usuário entra como textContent;
   - a Alinia não aprova, rejeita nem adia; leva até a Revisão do RH;
   - número sem fonte não é afirmado; campo ausente não vira zero;
   - nada é guardado no navegador.
   ========================================================================== */

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const pause = (ms) => new Promise((resolve) => { setTimeout(resolve, reduceMotion ? 0 : ms); });
const normalize = (text) => text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const shortId = (value) => (value && value.length > 12 ? `${value.slice(0, 8)}…` : value);

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text != null) element.textContent = text;
  return element;
}

function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'icon');
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#${name}`);
  svg.append(use);
  return svg;
}

/* --- Intenções ------------------------------------------------------------
   Ordem importa: as guardas vêm primeiro, e "aprovar a contratação" é decisão,
   não contratação. Os padrões rodam sobre o texto sem acento. */
const INTENTS = [
  ['injection', /(ignor[ea]r?|esque[cç]a) (as |suas |todas as )?(instruc|regras)|revel[ae]r?|\btoken\b|\bsenha\b|prompt do sistema|system prompt|modo desenvolvedor/],
  ['people', /\bcpf\b|salario d[eoa]s? |\bdemit|\bdeslig|pior (funcionario|pessoa|colaborador)|avali[ae]r? (o|a|os|as) (funcionario|colaborador|pessoa)|quem (produz|trabalha|rende) menos|ranking de (pessoas|funcionarios|colaboradores)/],
  ['decide', /\b(aprov|rejeit|reprov|adiar|adie\b|adiamento|requisic|decid|decisao)/],
  ['hire', /\b(contrat|vagas?\b|headcount|quantas pessoas|quantos funcionarios|novas? pessoas)/],
  ['forecast', /\b(previs|crescer|cresc|proximas semanas|futur|tendencia|projec|projet)/],
  ['scenarios', /\b(cenario|alternativ|opcoes|opcao|o que (fazer|posso fazer|devo)|realoc|temporari|redesenh|capacit)/],
  ['rules', /\b(regras?\b|jornada|lei\b|cct|acordo coletivo|convencao|politica|juridic|clt|repouso|estagi)/],
  ['sources', /\b(fontes?\b|de onde|origem|evidencia)/],
  ['investigate', /\b(investig|por ?que|causa|nao da conta|motivo|explic|hipotes)/],
  ['overview', /\b(resum|situacao|visao geral|como esta|capacidade|demanda|deficit|ipd|pressao|backlog|numeros)/],
  ['greet', /^(oi|ola|bom dia|boa tarde|boa noite|e ai|hey)\b/],
  ['help', /\b(ajuda|o que voce (faz|pode)|como (voce )?funciona|quem e voce)/],
];

function detectIntent(text) {
  const value = normalize(text).trim();
  const match = INTENTS.find(([, pattern]) => pattern.test(value));
  return match ? match[0] : 'fallback';
}

const SUGGESTIONS = [
  'Qual é a situação da equipe?',
  'Por que a equipe não dá conta da demanda?',
  'Quanto a demanda deve crescer?',
  'Quais são as alternativas?',
  'Posso contratar 3 pessoas?',
  'Quais regras se aplicam?',
];

const RUN_STATES = {
  WAITING_INPUT: 'Aguardando resposta do gestor',
  AWAITING_HUMAN: 'Aguardando decisão do RH',
  COMPLETED: 'Concluída',
  FAILED: 'Interrompida',
  BLOCKED: 'Bloqueada',
};
const SETTLED = ['WAITING_INPUT', 'AWAITING_HUMAN', 'COMPLETED', 'FAILED', 'BLOCKED'];

const RULE_LABELS = {
  'workweek.max_hours': 'Jornada semanal máxima',
  'workday.max_hours': 'Jornada diária máxima',
  'rest.weekly_min_days': 'Repouso semanal mínimo',
  'contract.modality': 'Modalidade contratual',
  'internship.counts_as_capacity': 'Estágio conta como capacidade',
};
const RULE_REASONS = {
  missing: 'nenhuma regra vigente cadastrada',
  conflict: 'há regras em conflito',
  pinned_revoked: 'a versão fixada foi revogada',
  pinned_not_found: 'a versão fixada não foi encontrada',
  hash_mismatch: 'a integridade da regra não confere',
};

/* --- Dados da simulação (mesmos números da Unidade Centro nas outras telas) */
const DEMO = {
  unit: 'Unidade Centro',
  question: { id: 'q-n1', text: 'Há tarefas que exigem supervisão N1 no turno da tarde?' },
  hypotheses: [
    ['Demanda acima da capacidade agregada', 'sustentada', 'calculo'],
    ['Cobertura desigual por competência e turno', 'não verificada', 'skills'],
    ['Pico sazonal de dezembro', 'não verificada', 'historico'],
  ],
  forecast: { values: ['1.165', '1.180', '1.195', '1.200'], low: '1.080', high: '1.320' },
  scenarios: [
    ['Contratar', 'Condicional', 'Prazo de chegada, mentoria e cobertura N1'],
    ['Temporários', 'Exploratório', 'Modalidade, custo e prazo'],
    ['Realocar ou capacitar', 'Condicional', 'Impacto na equipe de origem'],
    ['Redesenhar turnos', 'Exploratório', 'Repousos e cobertura obrigatória'],
    ['Não agir', 'Referência', 'Backlog e pressão operacional'],
  ],
};

export function mountAgent(ctx) {
  const screen = document.querySelector('[data-screen="agente"]');
  const thread = screen.querySelector('[data-agent-thread]');
  const form = screen.querySelector('[data-agent-form]');
  const input = screen.querySelector('[data-agent-input]');
  const send = screen.querySelector('[data-agent-send]');
  const answering = screen.querySelector('[data-agent-answering]');
  const answeringText = screen.querySelector('[data-agent-answering-text]');
  const note = screen.querySelector('[data-agent-note]');
  const sourceList = screen.querySelector('[data-agent-sources]');
  const more = screen.querySelector('[data-agent-more]');

  const state = {
    busy: false,
    pending: null, // { runId|null, question, index, total }
    answeringActive: false,
    cited: new Map(),
    demoAnswered: false,
    quiet: false,
  };

  const connected = () => Boolean(ctx.session.token);

  /* --- Fontes ------------------------------------------------------------ */
  function cite(key, evidence) {
    state.cited.set(key, evidence);
    renderSources();
    return evidence;
  }

  function renderSources() {
    if (!state.cited.size) {
      sourceList.replaceChildren(node('li', 'agent-context__empty', 'Nenhuma fonte citada ainda'));
      return;
    }
    sourceList.replaceChildren(...[...state.cited.values()].map((evidence) => {
      const item = node('li');
      const button = node('button', 'agent-source', evidence.title);
      button.type = 'button';
      button.addEventListener('click', () => ctx.openEvidence(evidence, button));
      item.append(button);
      return item;
    }));
  }

  /* --- Turnos ------------------------------------------------------------ */
  function scrollToEnd() {
    if (state.quiet) return;
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: reduceMotion ? 'auto' : 'smooth' });
  }

  // Trecho de texto: string ou { value, src, evidence, tone }.
  function rich(parts) {
    const paragraph = node('p');
    parts.forEach((part) => {
      if (typeof part === 'string') {
        paragraph.append(part);
        return;
      }
      const value = node('strong', part.tone === 'deficit' ? 'num num--deficit' : 'num', part.value);
      paragraph.append(value);
      if (part.evidence) {
        const badge = node('button', 'src', part.src || 'fonte');
        badge.type = 'button';
        badge.setAttribute('aria-label', `Ver fonte: ${part.evidence.title}`);
        badge.addEventListener('click', () => ctx.openEvidence(part.evidence, badge));
        paragraph.append(' ', badge);
      }
    });
    return paragraph;
  }

  function userTurn(text, label) {
    const article = node('article', 'turn turn--user');
    if (label) article.append(node('p', 'turn__context', label));
    article.append(node('div', 'turn__bubble', text));
    thread.append(article);
    scrollToEnd();
  }

  function agentTurn() {
    const article = node('article', 'turn turn--agent');
    const who = node('p', 'turn__who');
    const mark = node('span', 'turn__mark');
    mark.setAttribute('aria-hidden', 'true');
    mark.append(node('i'), node('i'), node('i'));
    who.append(mark, 'Alinia');
    const body = node('div', 'turn__body');
    const thinking = node('p', 'turn__thinking', 'Lendo os dados');
    body.append(thinking);
    article.append(who, body);
    thread.append(article);
    scrollToEnd();

    let steps = null;
    let list = null;
    let summary = null;
    let count = 0;
    const started = performance.now();

    const add = (element) => {
      thinking.remove();
      body.append(element);
      scrollToEnd();
      return element;
    };

    const turn = {
      step(label, detail) {
        if (!steps) {
          steps = node('details', 'turn__steps');
          steps.open = true;
          summary = node('summary', null, 'Consultando');
          list = node('ol');
          steps.append(summary, list);
          body.insertBefore(steps, thinking.isConnected ? thinking : body.firstChild);
        }
        count += 1;
        const item = node('li', 'is-running');
        const markBox = node('span', 'step-mark');
        markBox.setAttribute('aria-hidden', 'true');
        const text = node('span', 'step-text');
        text.append(node('span', null, label));
        if (detail) text.append(node('code', null, detail));
        const time = node('span', 'step-time');
        item.append(markBox, text, time);
        list.append(item);
        scrollToEnd();
        const t0 = performance.now();
        return {
          done() {
            item.className = 'is-done';
            markBox.replaceChildren(icon('i-check'));
            time.textContent = `${Math.max(1, Math.round(performance.now() - t0))} ms`;
          },
          fail(message) {
            item.className = 'is-failed';
            markBox.replaceChildren(icon('i-x'));
            time.textContent = message || 'falhou';
          },
        };
      },
      async run(label, detail, task) {
        const handle = turn.step(label, detail);
        try {
          const [result] = await Promise.all([task(), pause(220)]);
          handle.done();
          return result;
        } catch (error) {
          handle.fail(ctx.errorText(error));
          throw error;
        }
      },
      say(...parts) { return add(rich(parts)); },
      list(rows) {
        const ul = node('ul', 'turn__list');
        ul.append(...rows.map((parts) => {
          const li = node('li');
          li.append(rich(parts));
          return li;
        }));
        return add(ul);
      },
      card({ kind = 'info', label, title, text, actions = [] }) {
        const card = node('div', `agent-card agent-card--${kind}`);
        if (label) {
          const head = node('p', 'agent-card__label');
          head.append(icon(kind === 'question' ? 'i-message' : kind === 'handoff' ? 'i-arrow-right' : 'i-alert'), label);
          card.append(head);
        }
        if (title) card.append(node('p', 'agent-card__title', title));
        if (text) card.append(node('p', 'agent-card__text', text));
        if (actions.length) {
          const row = node('div', 'agent-card__actions');
          actions.forEach((action) => {
            const element = action.href ? node('a', `button${action.primary ? ' button--dark' : ''}`, action.label) : node('button', `button${action.primary ? ' button--dark' : ''}`, action.label);
            if (action.href) element.href = action.href;
            else {
              element.type = 'button';
              element.addEventListener('click', () => action.onClick(element));
            }
            row.append(element);
          });
          card.append(row);
        }
        return add(card);
      },
      suggest(prompts) {
        const row = node('div', 'agent-suggestions');
        prompts.forEach((prompt) => row.append(chip(prompt)));
        return add(row);
      },
      block(element) { return add(element); },
      finish() {
        thinking.remove();
        if (steps) {
          const seconds = ((performance.now() - started) / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
          summary.textContent = `${count} ${count === 1 ? 'passo' : 'passos'} · ${seconds} s`;
          steps.open = false;
        }
        if (!body.children.length) body.append(node('p', null, 'Não há o que mostrar para esta pergunta.'));
      },
    };
    return turn;
  }

  function chip(prompt) {
    const button = node('button', 'chip', prompt);
    button.type = 'button';
    button.addEventListener('click', () => submit(prompt));
    return button;
  }

  /* --- Contexto ---------------------------------------------------------- */
  async function refreshContext() {
    const scope = ctx.scope();
    screen.querySelector('[data-agent-unit]').textContent = connected() ? (scope.teamName || 'Equipe não escolhida') : DEMO.unit;
    screen.querySelector('[data-agent-mode]').textContent = connected() ? 'API conectada' : 'Simulação com dados de exemplo';
    screen.querySelector('[data-agent-mode-dot]').classList.toggle('dot--live', connected());
    screen.querySelector('[data-agent-scope]').textContent = connected()
      ? (scope.snapshotId ? `Recorte ${scope.snapshotId}` : 'Nenhum recorte escolhido')
      : 'demanda_centro.csv · janela de 4 semanas';
    let runLabel = connected() ? 'Nenhuma aberta neste recorte' : (state.demoAnswered ? RUN_STATES.AWAITING_HUMAN : RUN_STATES.WAITING_INPUT);
    if (connected() && ctx.session.runId) {
      const known = ctx.session.runs.find((run) => run.run_id === ctx.session.runId);
      runLabel = known ? (RUN_STATES[known.state] || known.state) : 'Carregada';
    }
    screen.querySelector('[data-agent-run]').textContent = runLabel;
    note.textContent = connected()
      ? 'Respostas montadas a partir da API, com a fonte de cada número. O modelo de linguagem ainda não está ligado.'
      : 'Simulação com os dados de exemplo da Unidade Centro. Nada é enviado ou salvo.';
    // Só o número: o rótulo do menu já é longo.
    const meta = document.querySelector('[data-agent-nav-meta]');
    meta.textContent = state.pending ? '1' : '';
    meta.title = state.pending ? 'Pergunta ao gestor aguardando resposta' : '';
  }

  /* --- Modo de resposta a pergunta do gestor ----------------------------- */
  function setAnswering(active) {
    state.answeringActive = active && Boolean(state.pending);
    answering.hidden = !state.answeringActive;
    if (state.answeringActive) {
      answeringText.textContent = state.pending.question.text;
      input.placeholder = 'Escreva a resposta do gestor';
      input.focus();
    } else {
      input.placeholder = 'Pergunte sobre demanda, capacidade, previsão ou cenários';
    }
  }

  function ask(turn, question, index, total, runId) {
    state.pending = { question, index, total, runId };
    turn.card({
      kind: 'question',
      label: total > 1 ? `Pergunta ao gestor · ${index} de ${total}` : 'Pergunta ao gestor',
      title: question.text,
      text: 'A resposta entra como relato do gestor, não como fato verificado. Ela não muda a capacidade calculada.',
      actions: [{ label: 'Responder agora', primary: true, onClick: () => setAnswering(true) }],
    });
    setAnswering(true);
  }

  /* --- Escopo e investigação (modo conectado) ---------------------------- */
  function needScope(turn) {
    const scope = ctx.scope();
    if (scope.teamId && scope.snapshotId) return scope;
    turn.say('Você está conectado, mas ainda não escolheu a equipe e o recorte de dados que devo ler.');
    turn.card({ kind: 'info', label: 'Falta escolher o recorte', actions: [{ label: 'Escolher recorte', primary: true, onClick: () => ctx.openConnect() }] });
    return null;
  }

  async function readRun(turn) {
    const scope = ctx.scope();
    const runId = ctx.session.runId
      || ctx.session.runs.find((run) => run.team_id === scope.teamId && run.snapshot_id === scope.snapshotId)?.run_id;
    if (!runId) return null;
    const run = await turn.run('Lendo a investigação', `GET /api/investigations/${shortId(runId)}`,
      () => ctx.api(`/api/investigations/${encodeURIComponent(runId)}`));
    if (ctx.session.runId !== run.run_id) await ctx.syncRun(run);
    return run;
  }

  async function openRun(turn, scope) {
    const opened = await turn.run('Abrindo a investigação do recorte', 'POST /api/investigations', () => ctx.api('/api/investigations', {
      method: 'POST',
      body: { team_id: scope.teamId, snapshot_id: scope.snapshotId, idempotency_key: `ui-${scope.teamId}-${scope.snapshotId}`, cycle_limit: 3 },
    }));
    return advanceRun(turn, opened);
  }

  async function advanceRun(turn, run) {
    const next = await turn.run('Executando o ciclo de investigação', `POST /api/investigations/${shortId(run.run_id)}/advance`,
      () => ctx.api(`/api/investigations/${encodeURIComponent(run.run_id)}/advance`, { method: 'POST' }));
    await ctx.syncRun(next);
    return next;
  }

  function offerInvestigation(turn) {
    turn.say('Ainda não há investigação aberta neste recorte. Sem ela, não tenho previsão nem cenários para mostrar.');
    turn.card({
      kind: 'info',
      label: 'Próximo passo',
      title: 'Abrir a investigação deste recorte',
      text: 'Eu leio o recorte, levanto hipóteses e pergunto ao gestor o que faltar. Nada é decidido nessa etapa.',
      actions: [{ label: 'Abrir investigação', primary: true, onClick: (button) => { button.disabled = true; submit('Abra a investigação deste recorte'); } }],
    });
  }

  function runEvidence(run) {
    return cite(`run-${run.run_id}`, {
      title: 'Investigação',
      intro: 'Estado e relatório lidos da API. Hipóteses não verificadas não viram fato.',
      items: [
        ['Endpoint', `GET /api/investigations/${run.run_id}`],
        ['Recorte', run.snapshot_id],
        ['Estado', RUN_STATES[run.state] || run.state],
        ['Ciclo', `${run.cycle_count} de ${run.cycle_limit}`],
        ['Limitações', (run.report?.limitations || []).join(' ') || 'Nenhuma informada'],
      ],
    });
  }

  function pendingQuestions(run) {
    return (run.report?.questions || []).filter((question) => question.status === 'pending');
  }

  /* --- Ferramentas: modo conectado --------------------------------------- */
  const live = {
    async overview(turn) {
      const scope = needScope(turn);
      if (!scope) return;
      const base = `/api/teams/${encodeURIComponent(scope.teamId)}`;
      const query = `snapshot_id=${encodeURIComponent(scope.snapshotId)}`;
      const metrics = await turn.run('Lendo as métricas do recorte', `GET ${base}/metrics`, () => ctx.api(`${base}/metrics?${query}`));
      const flow = await turn.run('Lendo o fluxo de demanda', `GET ${base}/demand-flow`, () => ctx.api(`${base}/demand-flow?${query}`).catch((error) => {
        if (error.status === 404) return null;
        throw error;
      }));
      const block = metrics.homogeneous;
      const rows = (metrics.demand || []).filter((item) => item.quantity != null);
      const demand = rows.length ? rows.reduce((total, item) => total + Number(item.quantity), 0) : null;
      const metricEvidence = (title, value) => cite(`metric-${title}-${scope.snapshotId}`, {
        title, intro: 'Valor lido da API para o recorte escolhido. Arquivo agregado, sem pessoas identificadas.',
        items: [['Endpoint', `GET ${base}/metrics`], ['Recorte', scope.snapshotId], ['Valor', value], ['Limitações', (metrics.limitations || []).join(' ') || 'Nenhuma informada']],
      });

      if (demand == null) turn.say('O recorte não traz quantidade de demanda. Sem ela, não calculo pressão de demanda nem déficit.');
      else turn.say('No recorte ', { value: scope.snapshotId }, ', a demanda agregada é de ',
        { value: ctx.formatApi(demand), src: 'CSV', evidence: metricEvidence('Demanda do recorte', `${ctx.formatApi(demand)} casos no período`) }, ' casos no período.');

      if (block) {
        const ipd = Number.parseFloat(block.ipd);
        const share = Math.round(Math.abs(ipd - 1) * 100);
        turn.say('A capacidade do bloco homogêneo é de ',
          { value: ctx.formatApi(block.capacity_cases), src: 'cálculo', evidence: metricEvidence('Capacidade do bloco homogêneo', `${ctx.formatApi(block.capacity_cases)} casos no período`) },
          ' casos. A pressão de demanda (IPD) fica em ',
          { value: ctx.formatApi(block.ipd), src: 'cálculo', evidence: metricEvidence('Pressão de demanda (IPD)', `demanda ÷ capacidade = ${ctx.formatApi(block.ipd)}`) },
          Number.isFinite(ipd) ? (share === 0 ? ': demanda e capacidade estão no mesmo nível.' : `: a demanda está ${share}% ${ipd > 1 ? 'acima' : 'abaixo'} da capacidade.`) : '.');
        if (block.headcount_gap != null) {
          turn.say('No agregado, o quadro de referência é ', { value: String(block.required_headcount) }, ' pessoas e faltam ',
            { value: String(block.headcount_gap), tone: Number(block.headcount_gap) > 0 ? 'deficit' : undefined, src: 'cálculo', evidence: metricEvidence('Gap agregado', `${block.headcount_gap} posições sobre quadro de referência ${block.required_headcount}`) },
            '. Esse número não diz quais competências nem quais turnos estão descobertos.');
        }
      } else {
        turn.say('Este recorte não forma um bloco homogêneo, então não converto horas em casos. As horas de pool, contadas uma vez, somam ',
          { value: metrics.pool_hours ? ctx.formatApi(metrics.pool_hours) : 'valor ausente', src: 'cálculo', evidence: metricEvidence('Horas de pool', metrics.pool_hours ? `${ctx.formatApi(metrics.pool_hours)} h` : 'ausente') }, '.');
      }

      const latest = flow?.items?.at(-1);
      if (latest && latest.demand_semantics === 'incoming_plus_unmet') {
        const flowEvidence = cite(`flow-${scope.snapshotId}`, {
          title: 'Fluxo da demanda',
          intro: 'Entradas, conclusões e backlog do último período do recorte.',
          items: [['Endpoint', `GET ${base}/demand-flow`], ['Período', `${latest.start} a ${latest.end}`], ['Entradas', ctx.formatApi(latest.incoming_cases)], ['Concluídos', ctx.formatApi(latest.completed_cases)], ['Backlog', `${ctx.formatApi(latest.backlog_start)} → ${ctx.formatApi(latest.backlog_end)}`], ['Limitações', (flow.limitations || []).join(' ')]],
        });
        const grew = Number(latest.backlog_end) - Number(latest.backlog_start);
        turn.say('No último período, entraram ', { value: ctx.formatApi(latest.incoming_cases) }, ' casos e foram concluídos ',
          { value: ctx.formatApi(latest.completed_cases) }, '. O backlog foi de ', { value: ctx.formatApi(latest.backlog_start) }, ' para ',
          { value: ctx.formatApi(latest.backlog_end), tone: grew > 0 ? 'deficit' : undefined, src: 'CSV', evidence: flowEvidence }, '.');
      } else if (latest) {
        turn.say('O fluxo deste recorte está em formato legado: não comprova entradas, conclusões nem backlog.');
      }

      const run = await readRun(turn);
      if (!run) {
        turn.suggest(['Por que a equipe não dá conta da demanda?', 'Quais regras se aplicam?']);
        return;
      }
      turn.say('A investigação deste recorte está em: ', { value: RUN_STATES[run.state] || run.state, src: 'API', evidence: runEvidence(run) }, '.');
      turn.suggest(['Por que a equipe não dá conta da demanda?', 'Quanto a demanda deve crescer?', 'Quais são as alternativas?']);
    },

    async investigate(turn) {
      const scope = needScope(turn);
      if (!scope) return;
      let run = await readRun(turn);
      if (!run) run = await openRun(turn, scope);
      else if (!SETTLED.includes(run.state)) run = await advanceRun(turn, run);
      const report = run.report;
      if (!report) {
        turn.say('A investigação ainda não produziu relatório. Estado: ', { value: RUN_STATES[run.state] || run.state, src: 'API', evidence: runEvidence(run) }, '.');
        return;
      }
      const evidence = runEvidence(run);
      turn.say('Comecei pelo sinal do recorte: ', { value: report.trigger, src: 'API', evidence }, '. Estas são as hipóteses e o que cada uma tem de apoio:');
      turn.list(report.hypotheses.map((item) => [
        { value: item.statement }, ' — ',
        item.verification === 'supported' ? 'sustentada pelo recorte' : 'ainda não verificada',
      ]));
      if (report.missing_data?.length) turn.say(`Para avançar com segurança, faltam: ${report.missing_data.join(', ')}.`);
      if (run.failure) turn.say(`A investigação parou: ${run.failure}.`);
      const pending = pendingQuestions(run);
      if (pending.length) {
        turn.say('Antes de comparar alternativas, preciso de uma resposta do gestor.');
        ask(turn, pending[0], 1, pending.length, run.run_id);
        return;
      }
      await describeOutcome(turn, run);
    },

    async answer(turn, text) {
      const { runId, question } = state.pending;
      state.pending = null;
      setAnswering(false);
      await turn.run('Registrando a resposta como relato do gestor', `POST /api/investigations/${shortId(runId)}/answers`,
        () => ctx.api(`/api/investigations/${encodeURIComponent(runId)}/answers`, {
          method: 'POST',
          body: { question_id: question.question_id, answer: text, idempotency_key: `${runId}-${question.question_id}` },
        }));
      let run = await turn.run('Relendo a investigação', `GET /api/investigations/${shortId(runId)}`,
        () => ctx.api(`/api/investigations/${encodeURIComponent(runId)}`));
      const pending = pendingQuestions(run);
      if (pending.length) {
        await ctx.syncRun(run);
        turn.say('Registrei a resposta como relato. Ainda falta uma informação:');
        const total = (run.report?.questions || []).length;
        ask(turn, pending[0], total - pending.length + 1, total, run.run_id);
        return;
      }
      run = await advanceRun(turn, run);
      turn.say('Registrei a resposta como relato do gestor e refiz o ciclo. O relato não muda a capacidade calculada; ele aparece como dependência não verificada nos cenários.');
      await describeOutcome(turn, run);
    },

    async forecast(turn) {
      if (!needScope(turn)) return;
      const run = await readRun(turn);
      if (!run) return offerInvestigation(turn);
      const forecast = run.forecast;
      if (!forecast) {
        turn.say('A previsão ainda não foi calculada. Ela sai quando o ciclo de investigação avança.');
        return;
      }
      const evidence = cite(`forecast-${run.run_id}`, {
        title: 'Previsão de demanda',
        intro: 'Resultado do método determinístico do backend. Faixa empírica não é P10/P90 nem garantia.',
        items: [
          ['Método', forecast.method === 'moving_median_4' ? 'Mediana móvel de 4 semanas' : forecast.method],
          ['Estado', forecast.status],
          ['Backtest', forecast.backtest ? `MAE ${forecast.backtest.mae ?? 'indefinido'} · WAPE ${forecast.backtest.wape ?? 'indefinido'}` : 'Sem backtest'],
          ['Faixa', forecast.interval_description || 'Sem faixa validada'],
          ['Limitações', (forecast.limitations || []).join(' ') || 'Nenhuma informada'],
        ],
      });
      if (forecast.status === 'abstained') {
        turn.say('A previsão ', { value: 'se absteve', src: 'API', evidence }, '. Não há base para dizer quanto a demanda vai crescer neste recorte.');
      } else {
        const points = (forecast.points || []).slice(0, 4);
        const known = points.filter((point) => point.point_estimate != null);
        turn.say('A previsão usa ', { value: forecast.method === 'moving_median_4' ? 'mediana móvel de 4 semanas' : forecast.method }, ' e está ',
          { value: forecast.status === 'calibrated' ? 'com faixa validada' : 'sem faixa validada', src: 'API', evidence }, '.');
        if (known.length) {
          turn.list(points.map((point, index) => [
            `Semana ${index + 1}: `,
            { value: point.point_estimate == null ? 'sem estimativa' : ctx.formatApi(Math.round(point.point_estimate)) },
            point.lower != null && point.upper != null ? ` (faixa de ${ctx.formatApi(Math.round(point.lower))} a ${ctx.formatApi(Math.round(point.upper))})` : '',
          ]));
        }
      }
      if (forecast.limitations?.length) turn.say(forecast.limitations.join(' '));
      turn.card({ kind: 'handoff', label: 'Na tela de previsão', text: 'O gráfico mostra os pontos e a faixa, quando ela existe.', actions: [{ label: 'Ver previsão', href: '#previsao' }] });
    },

    async scenarios(turn, { hireOnly = false } = {}) {
      if (!needScope(turn)) return;
      const run = await readRun(turn);
      if (!run) return offerInvestigation(turn);
      if (!['AWAITING_HUMAN', 'COMPLETED'].includes(run.state)) {
        turn.say('Os cenários só são montados depois que as perguntas pendentes forem respondidas.');
        const pending = pendingQuestions(run);
        if (pending.length) ask(turn, pending[0], 1, pending.length, run.run_id);
        return;
      }
      const result = await turn.run('Lendo os cenários da versão atual', `GET /api/investigations/${shortId(run.run_id)}/scenarios`,
        () => ctx.api(`/api/investigations/${encodeURIComponent(run.run_id)}/scenarios`));
      const items = result.items || [];
      if (hireOnly) return describeHire(turn, items);
      const evidence = cite(`scenarios-${run.run_id}`, {
        title: 'Cenários A–E',
        intro: 'Cenários da versão atual do ciclo, como o backend os montou.',
        items: items.map((item) => [ctx.kindTitle[item.kind] || item.kind, `${ctx.scenarioStatus(item)} · ${ctx.validation(item).label}`]),
      });
      const validated = items.filter((item) => ctx.validation(item).ok).length;
      turn.say('Há ', { value: String(items.length), src: 'API', evidence }, ` cenários na versão ${items[0]?.version ?? 1}. ${validated ? `${validated} passaram na validação independente.` : 'Nenhum passou na validação independente.'}`);
      turn.list(items.map((item) => {
        const reason = ctx.readableGap((item.legal_flags || [])[0] || item.gaps?.[0] || item.dependencies?.[0] || item.assumptions?.[0] || '');
        const sentence = reason ? `. ${reason.charAt(0).toUpperCase()}${reason.slice(1)}` : '';
        return [{ value: ctx.kindTitle[item.kind] || item.kind }, ` — ${ctx.scenarioStatus(item).toLowerCase()}`, sentence];
      }));
      turn.say('Comparar é com você e com o RH. Eu não escolho entre eles.');
      turn.card({ kind: 'handoff', label: 'Comparação lado a lado', actions: [{ label: 'Ver cenários', href: '#cenarios' }, { label: 'Ir para revisão', href: '#revisao', primary: true }] });
    },

    async hire(turn) { return live.scenarios(turn, { hireOnly: true }); },

    async rules(turn) {
      const scope = needScope(turn);
      if (!scope) return;
      const today = new Date();
      const onDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
      const keys = Object.keys(RULE_LABELS).map((key) => `rule_keys=${encodeURIComponent(key)}`).join('&');
      const result = await turn.run('Consultando as regras vigentes', 'GET /api/policies/resolve',
        () => ctx.api(`/api/policies/resolve?team_id=${encodeURIComponent(scope.teamId)}&on_date=${onDate}&${keys}`));
      const evidence = cite(`rules-${scope.teamId}-${onDate}`, {
        title: 'Regras vigentes',
        intro: `Resolução de regras da equipe na data ${onDate}. A Alinia não interpreta a lei; aplica regras cadastradas e aprovadas.`,
        items: result.items.map((item) => [RULE_LABELS[item.rule_key] || item.rule_key, item.status === 'resolved'
          ? `Vigente · versão ${item.version}${item.source_reference ? ` · ${item.source_reference}` : ''}`
          : `Revisão necessária: ${RULE_REASONS[item.reason] || item.reason}`]),
      });
      const resolved = result.items.filter((item) => item.status === 'resolved').length;
      turn.say('Para esta equipe, hoje, ', { value: `${resolved} de ${result.items.length}`, src: 'API', evidence }, ' regras estão vigentes:');
      turn.list(result.items.map((item) => [{ value: RULE_LABELS[item.rule_key] || item.rule_key }, ' — ', item.status === 'resolved'
        ? `vigente, versão ${item.version}`
        : `revisão necessária: ${RULE_REASONS[item.reason] || item.reason}`]));
      turn.say('Mesmo com regra geral vigente, o backend exige que RH e jurídico validem categoria, contrato e instrumento coletivo antes de tratar a regra como aplicável a um cenário. Eu não interpreto a lei.');
    },

    async decide(turn) {
      turn.say('Eu não aprovo, não rejeito e não adio cenários. Essa decisão é do RH, registrada com motivo e só depois que o cenário passa pela validação independente.');
      const decisions = [...ctx.session.decisions.values()];
      if (decisions.length) {
        const names = { approve: 'aprovação', reject: 'rejeição', defer: 'adiamento' };
        turn.say('Decisões já registradas nesta investigação:');
        turn.list(decisions.map((record) => [{ value: names[record.decision] || record.decision }, ` · ${shortId(record.decision_id)}`]));
      }
      turn.card({ kind: 'handoff', label: 'Decisão humana', title: 'Revisão do RH', text: 'Lá ficam as premissas, a validação de cada cenário e o registro da decisão.', actions: [{ label: 'Ir para revisão', href: '#revisao', primary: true }] });
    },
  };

  async function describeOutcome(turn, run) {
    if (run.state === 'AWAITING_HUMAN' || run.state === 'COMPLETED') {
      turn.say('A investigação chegou à etapa de decisão: ', { value: RUN_STATES[run.state], src: 'API', evidence: runEvidence(run) }, '.');
      if (run.forecast?.status === 'abstained') turn.say('A previsão se absteve por falta de histórico suficiente, então nenhum cenário recomenda número de vagas.');
      turn.suggest(['Quais são as alternativas?', 'Posso contratar 3 pessoas?', 'Quanto a demanda deve crescer?']);
    } else {
      turn.say('Estado atual: ', { value: RUN_STATES[run.state] || run.state, src: 'API', evidence: runEvidence(run) }, '.');
    }
  }

  function describeHire(turn, items) {
    const hire = items.find((item) => item.kind === 'hire');
    if (!hire) {
      turn.say('A API não devolveu um cenário de contratação para esta versão.');
      return;
    }
    const check = ctx.validation(hire);
    const evidence = cite(`hire-${hire.scenario_id}`, {
      title: 'Cenário de contratação',
      intro: 'Cenário A da versão atual, como o backend o montou.',
      items: [
        ['Versão', String(hire.version)],
        ['Conclusivo', hire.conclusive ? 'Sim' : 'Não'],
        ['Validação independente', check.label],
        ['Headcount agregado', hire.headcount_delta == null ? 'Não calculado' : String(hire.headcount_delta)],
        ['Lacunas', (hire.gaps || []).map(ctx.readableGap).join(' · ') || 'Nenhuma declarada'],
      ],
    });
    if (hire.conclusive && check.ok) {
      turn.say('O cenário de contratação passou na validação independente. O cálculo aponta ',
        { value: hire.headcount_delta == null ? 'headcount não calculado' : `+${hire.headcount_delta}`, src: 'API', evidence }, '. A decisão continua com o RH.');
    } else {
      turn.say('Não posso recomendar um número de vagas agora.');
      if (hire.headcount_delta != null) {
        turn.say('O cálculo agregado chega a ', { value: `+${hire.headcount_delta}`, src: 'API', evidence }, ' pessoas, mas isso é o efeito aritmético do gap, não uma recomendação.');
      }
      const reasons = [
        hire.conclusive ? null : 'a simulação não é conclusiva',
        check.ok ? null : `validação independente: ${check.label.toLowerCase()}`,
        ...(hire.gaps || []).map(ctx.readableGap),
        ...(hire.dependencies || []).map(ctx.readableGap),
      ].filter(Boolean);
      const unique = [...new Set(reasons)].slice(0, 5);
      if (unique.length) {
        turn.say('O que impede uma recomendação:');
        turn.list(unique.map((reason) => [reason]));
      }
    }
    turn.card({ kind: 'handoff', label: 'Decisão humana', text: 'Aprovar exige cenário conclusivo e validação independente válida.', actions: [{ label: 'Ir para revisão', href: '#revisao', primary: true }] });
  }

  /* --- Ferramentas: simulação -------------------------------------------- */
  const demo = {
    async overview(turn) {
      await turn.run('Lendo a demanda', 'demanda_centro.csv', () => pause(260));
      await turn.run('Calculando a capacidade', 'cálculo determinístico', () => pause(220));
      turn.say('Na Unidade Centro, a demanda atual é de ', { value: '1.150', src: 'CSV', evidence: cite('demanda', ctx.evidence.demanda) },
        ' atendimentos por semana. Com 11 pessoas em jornada simulada de 42h, a capacidade fica perto de ',
        { value: '954', src: 'cálculo', evidence: cite('calculo', ctx.evidence.calculo) }, '.');
      turn.say('A pressão de demanda é de ', { value: '1,21', src: 'cálculo', evidence: ctx.evidence.calculo },
        ': a demanda está 21% acima da capacidade. No agregado, faltam ', { value: '3', tone: 'deficit', src: 'cálculo', evidence: ctx.evidence.calculo },
        ' posições, sem dizer quais competências nem quais turnos estão descobertos.');
      turn.suggest(['Por que a equipe não dá conta da demanda?', 'Quanto a demanda deve crescer?']);
    },
    async investigate(turn) {
      await turn.run('Lendo o recorte', 'demanda_centro.csv', () => pause(240));
      await turn.run('Levantando hipóteses', 'investigação', () => pause(320));
      await turn.run('Separando o que tem fonte do que falta', 'evidências', () => pause(220));
      turn.say('O sinal é a pressão de demanda de ', { value: '1,21', src: 'cálculo', evidence: cite('calculo', ctx.evidence.calculo) }, ' em 42h. Estas são as hipóteses:');
      turn.list(DEMO.hypotheses.map(([statement, status, key]) => [{ value: statement, src: 'fonte', evidence: cite(key, ctx.evidence[key]) }, ` — ${status}`]));
      turn.say('O número de três posições é uma aproximação agregada. Para saber se ela fecha o problema, preciso de uma resposta do gestor.');
      if (!state.demoAnswered) ask(turn, DEMO.question, 1, 1, null);
      else turn.suggest(['Quais são as alternativas?', 'Posso contratar 3 pessoas?']);
    },
    async answer(turn) {
      state.pending = null;
      setAnswering(false);
      await turn.run('Registrando a resposta como relato do gestor', 'simulação: nada é enviado', () => pause(260));
      await turn.run('Refazendo o ciclo com a resposta', 'investigação', () => pause(360));
      state.demoAnswered = true;
      turn.say('Registrei a resposta como relato do gestor, não como fato. Ela não muda a capacidade calculada, mas entra como dependência a verificar nos cenários de contratar e realocar.');
      turn.say('A investigação chegou à etapa de decisão. Há cinco cenários comparáveis; nenhum é recomendação.');
      turn.suggest(['Quais são as alternativas?', 'Posso contratar 3 pessoas?', 'Quanto a demanda deve crescer?']);
    },
    async forecast(turn) {
      await turn.run('Lendo o histórico', 'demanda_centro.csv', () => pause(240));
      await turn.run('Projetando 4 semanas', 'mediana móvel', () => pause(300));
      turn.say('Na faixa provável, a demanda vai a ', { value: DEMO.forecast.values[3], src: 'cálculo', evidence: cite('historico', ctx.evidence.historico) },
        ` atendimentos na semana 4. A faixa ilustrativa vai de ${DEMO.forecast.low} a ${DEMO.forecast.high}.`);
      turn.list(DEMO.forecast.values.map((value, index) => [`Semana ${index + 1}: `, { value }]));
      turn.say('O histórico do exemplo é curto. Isso não separa um pico sazonal de um déficit estrutural.');
      turn.card({ kind: 'handoff', label: 'Na tela de previsão', actions: [{ label: 'Ver previsão', href: '#previsao' }] });
    },
    async scenarios(turn) {
      await turn.run('Montando os cenários A–E', 'cenários', () => pause(360));
      turn.say('Estes são os cinco cenários do exemplo. Nenhum passou pela validação independente, então nenhum pode ser aprovado ainda:');
      turn.list(DEMO.scenarios.map(([name, status, risk]) => [{ value: name }, ` — ${status.toLowerCase()}. ${risk}.`]));
      turn.say('Comparar é com você e com o RH. Eu não escolho entre eles.');
      turn.card({ kind: 'handoff', label: 'Comparação lado a lado', actions: [{ label: 'Ver cenários', href: '#cenarios' }, { label: 'Ir para revisão', href: '#revisao', primary: true }] });
    },
    async hire(turn) {
      await turn.run('Lendo o cenário de contratação', 'cenário A', () => pause(300));
      turn.say('Não posso recomendar um número de vagas agora.');
      turn.say('O cálculo agregado chega a ', { value: '+3', src: 'cálculo', evidence: cite('calculo', ctx.evidence.calculo) }, ' pessoas, mas isso é o efeito aritmético do gap, não uma recomendação.');
      turn.say('O que impede uma recomendação:');
      turn.list([
        ['falta a matriz de horas por competência e turno'],
        ['a previsão não tem histórico suficiente para validar a faixa'],
        ['prazo de recrutamento, ramp-up e mentoria ainda não informados'],
        ['categoria, contrato e instrumento coletivo ainda não validados'],
      ]);
      turn.card({ kind: 'handoff', label: 'Decisão humana', text: 'Aprovar exige cenário conclusivo e validação independente válida.', actions: [{ label: 'Ir para revisão', href: '#revisao', primary: true }] });
    },
    async rules(turn) {
      await turn.run('Consultando as regras vigentes', 'regras da equipe', () => pause(280));
      turn.say('No exemplo, só há uma premissa: jornada de ', { value: '42h', src: 'premissa', evidence: cite('jornada', ctx.evidence.jornada) }, ' semanais, usada apenas para simular.');
      turn.say('Categoria, vigência e instrumento coletivo precisam ser confirmados com RH e jurídico. Eu não interpreto a lei.');
    },
    async decide(turn) { return live.decide(turn); },
  };

  /* --- Respostas fixas --------------------------------------------------- */
  function intro(turn) {
    turn.say('Eu leio os dados já calculados da equipe, mostro de onde vem cada número e paro antes da decisão.');
    turn.say('Não aprovo cenários, não avalio pessoas e não afirmo número que a fonte não trouxe.');
    turn.suggest(SUGGESTIONS);
  }

  const fixed = {
    greet(turn) { intro(turn); },
    help(turn) { intro(turn); },
    injection(turn) {
      turn.say('Trato o texto das mensagens e dos dados como conteúdo, não como instrução. Não revelo credenciais e não mudo minhas permissões.');
      turn.suggest(['Qual é a situação da equipe?', 'Quais regras se aplicam?']);
    },
    people(turn) {
      turn.say('Não avalio, comparo nem indico pessoas, e não uso dado individual como salário, CPF ou saúde. Trabalho só com agregados da equipe.');
      turn.suggest(['Por que a equipe não dá conta da demanda?', 'Quais são as alternativas?']);
    },
    sources(turn) {
      if (!state.cited.size) {
        turn.say('Ainda não citei nenhuma fonte nesta conversa.');
        turn.suggest(['Qual é a situação da equipe?']);
        return;
      }
      turn.say('Estas são as fontes que usei até aqui. Toque em uma para ver valores e limites:');
      const row = node('div', 'agent-suggestions');
      [...state.cited.values()].forEach((evidence) => {
        const button = node('button', 'src src--wide', evidence.title);
        button.type = 'button';
        button.addEventListener('click', () => ctx.openEvidence(evidence, button));
        row.append(button);
      });
      turn.block(row);
    },
    fallback(turn) {
      turn.say('Não tenho uma ferramenta para responder isso com segurança. Esta versão da Alinia responde por ferramentas fixas; o modelo de linguagem ainda não está ligado.');
      turn.suggest(SUGGESTIONS.slice(0, 4));
    },
  };

  /* --- Envio ------------------------------------------------------------- */
  async function submit(raw) {
    const text = raw.trim();
    if (!text || state.busy) return;
    state.busy = true;
    send.disabled = true;
    input.value = '';
    resize();

    const answeringNow = state.answeringActive && state.pending;
    userTurn(text, answeringNow ? `Resposta a: ${state.pending.question.text}` : null);
    await pause(160);
    const turn = agentTurn();
    const tools = connected() ? live : demo;
    try {
      if (answeringNow) {
        await tools.answer(turn, text);
      } else {
        const intent = detectIntent(text);
        if (tools[intent]) await tools[intent](turn);
        else await fixed[intent](turn);
      }
    } catch (error) {
      turn.say(`Não consegui concluir: ${ctx.errorText(error)}.`);
      if (error.status === 401) turn.card({ kind: 'info', label: 'Sessão expirada', actions: [{ label: 'Conectar de novo', primary: true, onClick: () => ctx.openConnect() }] });
    } finally {
      turn.finish();
      state.busy = false;
      send.disabled = false;
      refreshContext();
      if (!state.answeringActive) input.focus({ preventScroll: true });
    }
  }

  function resize() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  }

  function reset({ greet = true } = {}) {
    state.pending = null;
    state.cited.clear();
    state.demoAnswered = false;
    setAnswering(false);
    thread.replaceChildren();
    renderSources();
    if (greet) {
      // A saudação não rola a página: o aviso do topo continua visível.
      state.quiet = true;
      const turn = agentTurn();
      intro(turn);
      turn.finish();
      state.quiet = false;
    }
    refreshContext();
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    submit(input.value);
  });
  input.addEventListener('input', resize);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      submit(input.value);
    }
  });
  screen.querySelector('[data-agent-answering-cancel]').addEventListener('click', () => {
    setAnswering(false);
    input.focus();
  });
  screen.querySelector('[data-agent-reset]').addEventListener('click', () => reset());

  // Ferramentas e limites ficam abertos no desktop e recolhidos no celular.
  const wide = window.matchMedia('(min-width: 1181px)');
  const syncMore = () => { more.open = wide.matches; };
  wide.addEventListener('change', syncMore);
  syncMore();

  // Novo login apaga a conversa: nada de um usuário fica visível para outro.
  document.addEventListener('alinia:login', () => reset());
  // Troca de equipe ou recorte cancela a pergunta pendente daquele recorte.
  document.addEventListener('alinia:reset', () => {
    if (state.pending && state.pending.runId) {
      state.pending = null;
      setAnswering(false);
    }
    refreshContext();
  });
  document.addEventListener('alinia:context', () => refreshContext());
  document.addEventListener('alinia:route', (event) => {
    if (event.detail === 'agente') {
      refreshContext();
      if (!state.answeringActive) input.focus({ preventScroll: true });
    }
  });

  reset();
}
