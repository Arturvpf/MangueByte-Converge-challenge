# Alinia / Workforce Intelligence
## Divisão em subtasks para duas pessoas

Versão 2 — 7 de novembro de 2026. Planejamento de implementação; nenhuma alteração no código.

**Pessoa 1: dados, diagnóstico e investigação. Pessoa 2: planejamento, cenários e decisão do RH.** Cada pessoa implementa os agentes, ferramentas, APIs, persistência e testes do seu domínio. Os nomes podem ser substituídos pelos integrantes da equipe.

### 1. Contexto e escopo

Fontes: Workforce_IA_PRD_Final.pdf, PRD v4.1, páginas 1–13, e repositório Arturvpf/MangueByte-Converge-challenge, commit `1f5bce47527d7c823b3496f337067cc974974a4a`.

O repositório oferece uma landing page e cinco telas de protótipo. `src/app/app.js` usa previsões, cenários e evidências fixos; a revisão do RH apenas muda um texto na sessão. `scripts/serve.mjs` serve arquivos estáticos. Agentes, APIs de negócio, banco, autenticação e integrações ainda precisam ser implementados.

Meta do MVP: duas equipes; CSV e Jira somente leitura; indicadores; investigação adaptativa; previsão baseline; três cenários com OR-Tools; comparação e decisão humana persistida. O rascunho de requisição permanece interno. Integrações WFM/ponto/ATS, alteração de escala e simulação detalhada com SimPy ficam para evolução.

Tecnologias propostas: Python, FastAPI, PostgreSQL, LangGraph e OR-Tools, mantendo a interface HTML/CSS/JS. Essas escolhas ainda não estão implementadas. Regras jurídicas citadas pelo PRD são entradas de domínio sujeitas à validação competente; não serão ativadas automaticamente com base no documento.

### 2. Mapa de responsabilidade

| Camada | Pessoa 1 | Pessoa 2 |
|---|---|---|
| Agentes | Orquestrador, investigador e mapeador de competências | Planejador de cenários e agente crítico |
| Ferramentas determinísticas | Métricas de capacidade e previsão | Otimização, custos e sensibilidade |
| Backend de domínio | Ingestão, snapshots, investigação, evidências e perguntas | Políticas, cenários, simulações, decisões e rascunhos |
| Infraestrutura principal | Worker, checkpoints e execução retomável | Base da aplicação, autenticação e auditoria comum |
| Interface | Visão geral, investigação e previsão | Cenários e revisão do RH |
| Qualidade | Ingestão, forecast e evals de investigação | Permissões, solver e evals de planejamento/crítica |

Uma pessoa é responsável pela entrega de cada subtask; a outra revisa. Ambas implementam autorização nos próprios endpoints usando o componente comum da Pessoa 2. O responsável pela infraestrutura não implementa automaticamente todos os módulos que a utilizam.

### 3. Acordos iniciais

#### COM-01 — Fixar contratos e fixtures compartilhadas

- **Responsável:** Pessoa 1. **Revisão:** Pessoa 2.
- **Subtasks:** definir unidades, períodos, moeda, timezone, identificadores e campos ausentes; criar schemas versionados; preparar duas equipes sintéticas; documentar erros tipados.
- **Entregável:** contratos de entrada/saída e fixtures usadas por ambos.
- **Dependência:** nenhuma.
- **Aceite:** as duas pessoas validam os mesmos exemplos automaticamente; dados sintéticos estão identificados; campos desconhecidos não viram zero.

#### COM-02 — Criar base executável do backend

- **Responsável:** Pessoa 2. **Revisão:** Pessoa 1.
- **Subtasks:** configurar aplicação, banco, migrações, testes, health check, configuração por ambiente e OpenAPI; definir como módulos de domínio registram rotas e jobs.
- **Entregável:** backend mínimo executável e README de desenvolvimento.
- **Dependência:** acordo inicial de COM-01; implementação pode ocorrer em paralelo às fixtures.
- **Aceite:** banco vazio recebe migrações; aplicação sobe pelo README; segredos não estão no repositório.

### 4. Pessoa 1 — Dados e investigação

#### P1-01 — Implementar cadastro e snapshots

- **Subtasks de backend:** criar equipes, skills, funções, turnos, demanda, disponibilidade e faixas de custo; implementar consultas autorizadas; preservar versões dos dados e sua origem.
- **Entregável:** modelos, migrações, repositórios e API de consulta de dados/snapshots.
- **Dependências:** COM-01, COM-02; componente de autorização P2-01 para aceite integrado.
- **Aceite:** consultas distinguem empresas, equipes, períodos e unidades; uma análise antiga continua acessando seu snapshot; dados pessoais desnecessários não entram no contexto analítico.

#### P1-02 — Implementar importação CSV

- **Subtasks de backend:** upload, pré-validação, erros por linha, confirmação de importação, deduplicação e registro de origem; suprimir ou agregar detalhes que possam identificar indivíduos.
- **Entregável:** importador e endpoints de criação/acompanhamento de importação.
- **Dependência:** P1-01.
- **Aceite:** repetir arquivo não duplica registros; unidades ausentes/incompatíveis são reportadas; importação parcial não aparece como completa; motivos de afastamento e salários individuais são excluídos.

#### P1-03 — Implementar Jira somente leitura

- **Subtasks de backend:** conector com paginação, credenciais no servidor, escopo autorizado, checkpoint e tratamento de indisponibilidade; mapear dados para o mesmo contrato do CSV.
- **Entregável:** conector e testes de contrato com fixtures.
- **Dependência:** P1-02; credenciais autorizadas para validação real.
- **Aceite:** reimportação não duplica eventos; nenhuma escrita no Jira; indisponibilidade é visível. Sem credenciais, registrar integração real como pendente, mesmo que os testes com fixtures passem.

#### P1-04 — Construir Metrics Engine

- **Subtasks de ferramenta:** calcular capacidade, disponibilidade efetiva, IPD, FTE e gap homogêneo; tratar capacidade zero, dados ausentes e unidades incompatíveis; preparar matriz skill/turno para o solver.
- **Subtasks de backend:** persistir resultado, versão e evidências; expor métricas por snapshot.
- **Entregável:** funções determinísticas, API e testes matemáticos.
- **Dependências:** COM-01; integração com P1-01.
- **Aceite:** 11 × 42 × 0,91 × 2,27 = 954,3534 atendimentos/semana; demanda projetada 1.200 implica 14 pessoas e gap agregado 3 no exemplo homogêneo. Isso não determina três vagas de um cargo específico. Horas não são contadas em duplicidade entre skills.

#### P1-05 — Construir previsão baseline

- **Subtasks de ferramenta:** baseline sazonal quando adequado ou mediana móvel; horizonte inicial de 4–8 semanas; backtesting com origem rolante; MAE/WAPE e tratamento de denominador zero; faixas de incerteza justificadas.
- **Subtasks de backend:** salvar método, janelas, métricas, versão e limitações; disponibilizar previsão por investigação.
- **Entregável:** forecaster, resultados persistidos e relatório de backtesting.
- **Dependências:** COM-01; séries de P1-01/P1-02.
- **Aceite:** sem vazamento temporal; histórico insuficiente produz abstenção ou cenários explicitamente não calibrados; valores arbitrários não são apresentados como P10/P50/P90.

#### P1-06 — Implementar agente investigador e mapeador

- **Subtasks de agentes:** levantar hipóteses de sazonalidade, capacidade, processo e skills; consultar ferramentas autorizadas; solicitar evidências; mapear tarefas/competências com confiança e ressalvas, sem pontuar indivíduos.
- **Subtasks de backend:** persistir hipóteses, evidências, perguntas e respostas; implementar endpoints de leitura e resposta.
- **Entregável:** InvestigationReport, matriz de competências e fluxo de perguntas.
- **Dependências:** P1-04; P1-05 para hipóteses temporais; P1-07 para execução integrada.
- **Aceite:** toda hipótese crítica possui evidência ou marcação de não verificada; falta de dados gera pergunta; dois casos demonstram caminhos diferentes de investigação; instruções maliciosas em dados não alteram permissões.

#### P1-07 — Implementar orquestrador e execução durável

- **Subtasks de agente:** definir transições entre diagnóstico, perguntas, planejamento e crítica; limites de passos, custo e tempo; integrar os nós da Pessoa 2 por contrato.
- **Subtasks de backend:** fila durável, worker, checkpoints, heartbeat, tentativas e idempotência; registrar traces no componente comum de auditoria.
- **Entregável:** execução assíncrona retomável e endpoint de acompanhamento.
- **Dependências:** COM-02; COM-01 para contratos; P2-02/P2-04 para fluxo completo.
- **Aceite:** reinício retoma ou reporta falha sem perder estado; perguntas suspendem a execução; respostas retomam a versão correta; reenvio não duplica cenários nem efeitos. Antes dos nós reais, usar mocks claramente identificados.

#### P1-08 — Conectar três telas e avaliar investigação

- **Subtasks:** integrar visão geral, investigação e previsão; mostrar carregamento, falha, falta de dados e baixa confiança; testar ingestão, investigação, previsão e retomada.
- **Entregável:** três telas consumindo APIs e suite de evals do domínio.
- **Dependências:** P1-04 a P1-07.
- **Aceite:** recarga preserva resultados; fixtures não aparecem como dados reais; tentativas de prompt injection no CSV/Jira não desviam o fluxo; nenhuma contratação exata é sugerida sem dados suficientes.

### 5. Pessoa 2 — Cenários e decisão

#### P2-01 — Implementar identidade, permissões e auditoria comum

- **Subtasks de backend:** autenticação verificável; perfis gestor, RH e administrador; escopo por empresa/equipe; dependências de autorização para rotas e ferramentas; armazenamento de eventos de auditoria e correlação por trace_id.
- **Entregável:** componentes comuns de acesso/auditoria e testes negativos.
- **Dependência:** COM-02.
- **Aceite:** identidade não é aceita apenas do corpo da requisição; acesso entre empresas é negado; segredos permanecem no servidor; logs evitam dados pessoais e prompts brutos desnecessários. Pessoa 1 instrumenta seus próprios módulos.

#### P2-02 — Implementar Policy Store

- **Subtasks de backend:** escopo, fonte, categoria, vigência, versão e responsável; estados rascunho, revisão, aprovado e revogado; consulta de regras aplicáveis à data do cenário.
- **Entregável:** banco, API e ferramenta tipada de consulta de regras.
- **Dependência:** P2-01.
- **Aceite:** ausência/conflito de regra retorna revisão requerida; versões antigas são preservadas; ativação exige aprovação autorizada; conteúdo jurídico depende de validação de domínio. Limites não são fixados em prompts.

#### P2-03 — Implementar agente planejador e backend de cenários

- **Subtasks de agente:** consumir InvestigationReport, previsão e matriz de competências; propor contratar, realocar/capacitar e não agir; registrar premissas, dependências, lacunas e justificativas.
- **Subtasks de backend:** persistir ScenarioCandidate versionado; criar, listar e consultar cenários; controlar concorrência/idempotência.
- **Entregável:** nó de planejamento e API de cenários.
- **Dependências:** COM-01 e P2-02; usar fixtures da Pessoa 1 até P1-06 ficar pronto.
- **Aceite:** três alternativas estruturadas; cenário sem intervenção presente; números finais vêm de ferramentas; dependências não satisfeitas impedem recomendação conclusiva.

#### P2-04 — Construir solver e simulação de sensibilidade

- **Subtasks de ferramenta:** OR-Tools para alocação skill/turno, funções e contratação inteira; restrições de disponibilidade, regras aprovadas, orçamento, mentoria e ramp-up; cálculo de custo e cobertura; testes de demanda alta, ausência de skill e atraso de contratação.
- **Subtasks de backend:** persistir SimulationResult, parâmetros, versões e status; disponibilizar resultados por cenário.
- **Entregável:** motor determinístico e resultados reproduzíveis.
- **Dependências:** P2-02, P2-03 e contrato de métricas P1-04.
- **Aceite:** mesma hora não é alocada duas vezes; solução liberada respeita restrições duras; déficit residual aparece explicitamente; ótimo, viável, inviável e timeout/resultado desconhecido são distintos. Timeout sem solução não prova inviabilidade. Simulação simples de backlog declara suas premissas.

#### P2-05 — Implementar agente crítico e revisão do plano

- **Subtasks de agente:** verificar evidências, inconsistências, cobertura, impacto na equipe de origem, premissas e resultados adversos; devolver riscos e pedidos de revisão ao planejador; limitar ciclos.
- **Subtasks de backend:** persistir parecer, motivos de descarte e versões revisadas; integrar retorno ao orquestrador da Pessoa 1.
- **Entregável:** nó crítico, parecer estruturado e histórico de revisões.
- **Dependências:** P2-03, P2-04 e contrato P1-07.
- **Aceite:** falha de restrição dura bloqueia cenário; lacunas não viram fatos; revisão pode retornar NEEDS_DATA ao investigador; crítico não substitui aprovação humana nem validação jurídica.

#### P2-06 — Implementar decisão do RH e rascunhos

- **Subtasks de backend:** aprovar, adiar ou rejeitar com justificativa, identidade, timestamp e escopo; vincular decisão à versão exata do cenário/snapshot/regras; criar rascunho interno de requisição mediante solicitação autorizada.
- **Subtasks de agente:** compor explicação e rascunho fundamentados em resultados já validados, incluindo alternativas descartadas e limitações.
- **Entregável:** DecisionRecord, rascunho e histórico consultável.
- **Dependências:** P2-01, P2-05.
- **Aceite:** sem decisão administrativa automática; usuário sem papel recebe negativa; reenvio não duplica registros; mudança material exige nova revisão; aprovação de cenário não autoriza automaticamente futura operação externa.

#### P2-07 — Conectar duas telas e avaliar cenários

- **Subtasks:** integrar cenários e revisão do RH; manter três opções disponíveis e comparação de até duas; apresentar inviabilidade, pendências, erros e confirmação do servidor; testar solver, crítica, acesso e aprovação.
- **Entregável:** duas telas consumindo APIs e suite de evals do domínio.
- **Dependências:** P2-03 a P2-06.
- **Aceite:** recarga mantém decisão; interface não anuncia sucesso antes de persistir; ferramenta maliciosa não induz escrita indevida; nenhuma seleção, demissão ou contratação autônoma é executada.

### 6. Integração entre as pessoas

#### INT-01 — Integrar investigação → planejamento → crítica

- **Responsável:** Pessoa 1. **Revisão:** Pessoa 2.
- **Dependências:** P1-06/P1-07 e P2-03/P2-04/P2-05.
- **Subtasks:** substituir mocks pelos nós reais; validar schemas; propagar snapshot, permissões e versões; testar retorno por falta de dados e revisão de alternativas.
- **Aceite:** fluxo completo mantém evidências e versões; resultado inválido interrompe execução; ciclo não excede limites configurados.

#### INT-02 — Validar fluxo ponta a ponta e isolamento

- **Responsável:** Pessoa 2. **Revisão:** Pessoa 1.
- **Dependências:** INT-01, P1-08 e P2-07.
- **Subtasks:** importar → investigar → responder → prever → comparar → decidir → recarregar; testar empresa errada, duplicação, worker interrompido, regra revogada, histórico curto e solver inviável.
- **Aceite:** nenhum efeito administrativo sem autorização; nenhuma exposição entre empresas; falhas ficam visíveis; dados e decisões sobrevivem à recarga e ao reinício.

#### INT-03 — Preparar entrega do piloto

- **Responsável:** Pessoa 1 pela documentação operacional; Pessoa 2 pelo checklist de liberação. Cada uma entrega o resultado indicado.
- **Subtasks:** README, configuração de exemplo, fixtures, relatório de testes/evals, limitações, procedimento de recuperação e roteiro de demonstração; registrar validações pendentes de RH/operação/jurídico e privacidade.
- **Dependência:** INT-02.
- **Aceite:** execução reproduzível sem segredos; duas equipes demonstradas; reduções de escopo identificadas. Aceite técnico não substitui aceite de domínio para dados reais.

### 7. Contratos que evitam bloqueios

**Envelope de ferramenta:** schema_version, tenant_id, team_id, run_id, data_snapshot_id, policy_version_ids, requested_at e idempotency_key. Identidade e permissões vêm do contexto autenticado; não são confiadas ao texto do LLM.

**Resposta:** status, result, evidence_refs, data_version, model_version quando aplicável, rule_versions, generated_at, limitations e trace_id. Erros mínimos: INSUFFICIENT_DATA, UNIT_MISMATCH, POLICY_REVIEW_REQUIRED, FORBIDDEN_SCOPE, SOLVER_TIMEOUT, INFEASIBLE e INTEGRATION_UNAVAILABLE.

| Contrato | Produtor e persistência | Consumidor |
|---|---|---|
| InvestigationReport: hipóteses, evidências, perguntas pendentes, limitações e confiança | Pessoa 1 | Pessoa 2 |
| ForecastResult: método, horizonte, faixas, backtesting e versão | Pessoa 1 | Pessoa 2 |
| SkillCapacitySnapshot: skills, turnos, horas elegíveis, disponibilidade e custos | Pessoa 1 | Pessoa 2 |
| ScenarioCandidate: ações, composição, premissas, custos preliminares e dependências | Pessoa 2 | Orquestrador da Pessoa 1 |
| SimulationResult: cobertura, custo, backlog, sensibilidade, status e versões | Pessoa 2 | Ambas e interface |
| CriticResult: riscos, bloqueios, revisão solicitada e dados faltantes | Pessoa 2 | Orquestrador/investigador da Pessoa 1 |
| DecisionRecord: aprovador, decisão, motivo, escopo, timestamp e versões | Pessoa 2 | Ambas e auditoria |

Estados do fluxo: CREATED → VALIDATING → INVESTIGATING → PLANNING → SIMULATING → REVIEWING → AWAITING_HUMAN → COMPLETED. WAITING_INPUT permite pausa/retomada; FAILED e BLOCKED são explícitos. NEEDS_DATA retorna à investigação; revisão de cenário retorna ao planejamento, sempre com limite de ciclos. COMPLETED indica conclusão do fluxo, não contratação executada.

Pessoa 1 mantém o schema de estado do orquestrador; Pessoa 2 mantém os schemas de cenários e revisão. Mudança que afete o outro domínio exige revisão da outra pessoa e teste de contrato.

### 8. Endpoints e tabelas por responsável

| Pessoa | Endpoints propostos | Tabelas/módulos principais |
|---|---|---|
| 1 | POST/GET /api/imports; GET /api/teams; GET /api/teams/{id}/metrics | teams, skills, roles, shifts, demand_records, capacity_records, cost_bands, imports, data_snapshots |
| 1 | POST/GET /api/investigations; POST /api/investigations/{id}/answers; GET /api/investigations/{id}/forecast | investigation_runs, questions, answers, evidence, forecasts, jobs, checkpoints |
| 2 | Rotas de autenticação; GET/POST /api/policies e revisão de versões | tenants, users, memberships, policy_versions, audit_events |
| 2 | GET /api/investigations/{id}/scenarios; GET /api/scenarios/{id}; POST /api/scenarios/{id}/decisions | scenarios, simulation_results, critic_reviews, decisions |
| 2 | POST /api/scenarios/{id}/requisition-drafts; GET /api/investigations/{id}/audit | requisition_drafts e consultas de auditoria |

Investigações são assíncronas: criação retorna 202 e run_id. Todas as escritas sensíveis verificam permissão, versão e idempotência. Cada pessoa cria as migrações do próprio domínio; a Pessoa 2 mantém a configuração da ferramenta de migração. Ações analíticas internas podem ser funções tipadas no worker, sem endpoints públicos adicionais.

### 9. Organização de arquivos e trabalho paralelo

- Pessoa 1: `backend/app/investigation/`, `ingestion/`, `metrics/`, `forecast/`, `jobs/`; agentes orquestrador/investigador/mapeador; testes correspondentes.
- Pessoa 2: `backend/app/planning/`, `optimization/`, `policies/`, `decisions/`, `auth/`, `audit/`; agentes planejador/crítico; testes correspondentes.
- Contratos: `backend/app/contracts/`, com autoria por artefato e revisão cruzada.
- Interface proposta: Pessoa 1 cria módulos `overview.js`, `investigation.js`, `forecast.js`; Pessoa 2 cria `scenarios.js`, `review.js` e cliente comum `api.js`.
- `src/app/app.js` e `index.html` continuam sendo os arquivos existentes a integrar. A Pessoa 2 coordena alterações na navegação comum; cada pessoa modifica apenas suas telas em PRs pequenos.

As pastas novas são propostas e ainda não foram criadas. Evitar que ambas editem um arquivo monolítico de agentes ou rotas. Compartilhar fixtures no início permite à Pessoa 2 construir planejamento sem aguardar ingestão real; a Pessoa 1 pode integrar o orquestrador com nós simulados até os contratos reais estarem prontos.

### 10. Ordem de execução e estimativa

Estimativa preliminar: 6–8 semanas, duas pessoas em dedicação integral, revisável após a primeira semana. Credenciais, dados históricos e validações externas podem ampliar o prazo. Não é uma promessa de duração igual por subtask: previsão e solver têm maior incerteza técnica.

| Período | Pessoa 1 | Pessoa 2 | Marco |
|---|---|---|---|
| Semana 1 | COM-01, P1-01 e início P1-04 | COM-02 e P2-01 | Contratos, fixtures e base executável |
| Semana 2 | P1-02 e P1-04 | P2-02 e P2-03 com fixtures | Dados importados e cenários estruturados |
| Semana 3 | P1-05 e base P1-07 | P2-04 | Forecast e solver verificáveis |
| Semana 4 | P1-06, integração P1-07 e P1-03 | P2-05 e P2-06 | Perguntas, crítica e revisão persistida |
| Semana 5 | P1-08 e INT-01 | P2-07 e apoio INT-01 | Cinco telas e fluxo real integrado |
| Semana 6 | Regressões, documentação e apoio INT-02 | INT-02 e checklist INT-03 | Gates técnicos aprovados |
| Semanas 7–8 | Ajustes com dados e feedback do piloto | Ajustes de cenários, segurança e operação | Aceite do piloto |

Revisar carga semanalmente pelo esforço restante, não pela quantidade de tickets. Se a Pessoa 1 ficar sobrecarregada com dados, a implementação do conector Jira pode ser transferida integralmente à Pessoa 2 após o solver, registrando mudança de responsável. Não dividir uma subtask entre duas pessoas sem separar entregáveis.

### 11. Definição de pronto e gates

Uma subtask está pronta quando código, migrações quando aplicáveis, testes relevantes, documentação do contrato e tratamento de falhas foram revisados. Mock validado não equivale a integração real concluída. Cada pessoa demonstra seu agente e seu backend funcionando juntos.

Gates obrigatórios do MVP:

- Fórmulas reproduzíveis, sem dupla contagem de horas; previsão sem vazamento temporal.
- Hipóteses críticas com evidência ou marcação de não verificadas; falta de dados causa abstenção/pergunta.
- Três cenários, incluindo não agir; solver não libera violações de restrições duras.
- Isolamento por empresa/equipe, minimização de dados e testes de reidentificação por cruzamento; grupo de cinco não é garantia de anonimato.
- Nenhuma decisão administrativa autônoma; aprovação versionada, autorizada e auditável.
- Reenvios e reinícios não duplicam efeitos; recarga mantém o histórico.
- Evals de prompt injection e saída maliciosa executados nos agentes de ambas as pessoas.

Dependências externas a registrar: duas equipes e unidades aprovadas; histórico e matriz de skills; credenciais Jira; provedor/modelo e orçamento; aprovadores RH; políticas validadas; ambiente do piloto e regras de retenção. Enquanto pendentes, desenvolver com fixtures identificadas. Adiar Jira ou solver deve ser declarado como redução do escopo do MVP do PRD.

### 12. Rastreabilidade ao PRD

| Referência | Subtasks |
|---|---|
| Seções 2–4: AI-native, agentes e workflow | P1-06, P1-07, P2-03, P2-05, INT-01 |
| Seção 5: dados e integrações | P1-01, P1-02, P1-03 |
| Seções 6–8: métricas, previsão e competências | P1-04, P1-05, P1-06, P2-04 |
| Seções 9–10: cenários e exemplo numérico | P2-03, P2-04 e testes P1-04 |
| Seções 11–13: regras, autonomia e privacidade | P2-01, P2-02, P2-06, P1-02 |
| Seção 14: contratos e avaliações | COM-01, P1-08, P2-07, INT-02 |
| Seções 15–17: MVP, roadmap e gates | Cronograma, definição de pronto e INT-03 |

Repositório analisado: https://github.com/Arturvpf/MangueByte-Converge-challenge/tree/1f5bce47527d7c823b3496f337067cc974974a4a
