# Rebaseline P1/P2 — PRD Workforce Intelligence v4.2

**Data:** 2026-11-08  
**Referência vigente:** `Workforce_Intelligence_PRD_v4.2.pdf` (24 páginas, 08/11/2026).  
**Referência histórica:** `Workforce_IA_PRD_Final.pdf` — PRD v4.1 (13 páginas).  
**Planejamento anterior:** `requisitos/docs/Divisao_IA_Backend_Alinia.md` (v2, baseado na v4.1).  
**Base de código auditada:** branches P1/P2 integradas em `audit/p1-p2-reconciliacao-2026-11-08`.  
**Estado deste documento:** nova matriz de requisitos e aceites; não comprova conclusão nem execução de testes.

## 1. Mudanças de produto que prevalecem sobre a v4.1

1. **Um agente, não cinco:** o MVP utiliza um investigador-planejador com ferramentas delimitadas. Um agente crítico pode existir como revisão complementar, mas **não é o verificador de segurança**. Validações independentes, determinísticas e fail-closed bloqueiam cenários ilegais/incompletos (v4.2 pp. 1, 6, 18).
2. **Ordem de entrega:** dados auditáveis → métricas → previsão com intervalos → otimização e cenários sem LLM → um agente instrumentado → experimentação de ganho incremental (pp. 19–21).
3. **Público inicial limitado:** operações de serviços com solicitações padronizadas, dois times e decisões recorrentes. Setores heterogêneos ficam fora do piloto inicial (pp. 3, 20).
4. **Demanda ≠ produção:** distinguir entradas, concluídos, cancelamentos, backlog e demanda não atendida. O baseline não pode inferir demanda apenas a partir de tickets resolvidos (pp. 8–10).
5. **Capacidade multidimensional:** intervalo, skill, turno, produtividade sustentável validada, retrabalho e qualidade; horas partilhadas não são somadas duas vezes (pp. 9–11).
6. **Restrições rígidas distintas de SLA:** cobertura mínima obrigatória e habilitação são hard constraints; meta de SLA é soft e déficit residual precisa ser declarado. Lead time de admissão, capacitação, mentoria e ramp-up afetam a eficácia do cenário (pp. 11–12).
7. **Cinco famílias de cenário A–E:** contratação permanente, temporários, realocação/capacitação, redesenho de turnos/processos, sem intervenção. O protótipo de três cenários da v4.1 não satisfaz esse requisito (pp. 11, 20).
8. **Revisão humana efetiva:** aprovador examina premissas, riscos, alternativas descartadas, versões e pode solicitar alteração; considerar Operações/Finanças quando aplicável. Aprovação não dispensa legislação ou revisão de privacidade (pp. 5, 7, 16–17).
9. **Privacidade por fluxo:** minimização pré-LLM, art. 11 para dados sensíveis, risco de reidentificação contextual, retenção, titular, fornecedores, RIPD e transferência internacional; módulo individual de jornada separado do agregado (pp. 15–16).
10. **Evidência de valor, não número de agentes:** experimento em três braços: processo atual, métricas/otimização sem LLM e solução com um LLM. Se o braço 3 não demonstrar ganho, manter solução determinística (pp. 18–20).

## 2. Veredito por task original (mesmo ID, aceite novo)

| ID | Situação na branch | Critério de aceite atualizado e principal lacuna |
|---|---|---|
| COM-01 | Parcial | Contratos v4.2 versionados: eventos de demanda, qualidade, intervalos, habilitação, lead time/ramp-up, relatos, simulador, revisão e pós-ação. Contratos atuais são v4.1. |
| COM-02 | Base existente, aceite integrado não reexecutado | FastAPI/Alembic existem; acrescentar verificação de migrações reconciliadas, telemetria por braço, versionamento e ambiente de teste reprodutível. |
| P1-01 — dados/snapshots | Parcial | Modelar entradas/concluídos/backlog/cancelados/não atendidos por intervalo e skill; disponibilidade, qualidade, restrições e custos; não só demanda agregada. |
| P1-02 — CSV | Parcial | Importação idempotente com prévia, validação e separação de fluxos; rejeitar amostras identificáveis e faltas de unidade; novos campos v4.2. |
| P1-03 — Jira | Parcial | Conector real somente leitura com paginação e checkpoint; mapear eventos de entrada, conclusão, reabertura/cancelamento e backlog sem conteúdo pessoal; integração atual não persiste sync real. |
| P1-04 — Metrics Engine | Parcial | IPD por intervalo/skill, throughput sustentável com qualidade/retrabalho/mix; separar cobertura obrigatória de SLA; teste independente da disponibilidade do solver. |
| P1-05 — previsão | Parcial | Usar entradas + demanda latente, sazonalidade quando pertinente, backtesting com origem rolante, MAE/WAPE e intervalos calibrados; comparar com baseline e abster quando inadequado. |
| P1-06 — investigação | Parcial, refatorar escopo | Um investigador-planejador compartilhado P1/P2; hipóteses como observado/testado/não verificado; relatos datados e atribuídos como relatos (não fatos); tool calling autorizado. |
| P1-07 — orquestração | Parcial, refatorar | LangGraph para um agente, checkpoints duráveis, limites, revisão humana, erro tipado e idempotência. Grafo existente é mock isolado; fluxo efetivo ainda é síncrono. |
| P1-08 — interface/evals | Parcial | Exibir entradas vs concluídos, backlog, cobertura por turno, confiança, fonte, causas alternativas e motivos de abstenção; teste de contaminação e reidentificação. |
| P2-01 — identidade/auditoria | Parcial | RBAC/ABAC, isolação de módulo individual/agregado, registros de acesso, rate limiting, custo/latência/traces, política de retenção e testes negativos. |
| P2-02 — Policy Store | Parcial | Regras aprovadas por data, categoria, contrato, instrumento coletivo, modalidade e exceções; regra ambígua bloqueia; proteger repousos e salário nos termos do PRD sem presumir validação jurídica. |
| P2-03 — cenários | Parcial, alteração material | Expandir de 3 para A–E, role_mix por função/turno, alternativas temporárias e redesenho, custos conhecidos/desconhecidos, premissas, lead time e ramp-up; não inferir cargo de FTE agregado. |
| P2-04 — solver | Parcial, alteração material | OR-Tools CP-SAT com hard constraints (habilitação, repouso, jornada, orçamento, cobertura obrigatória) e SLA soft; cenário inviável explícito; custos, lead time, mentoria e sensibilidade. Fluxo máximo atual não basta. |
| P2-05 — validação | Parcial, mudar objetivo | Substituir verificador principal por **validador determinístico independente**. Critic LLM opcional para perguntas e riscos, não autoriza nenhuma decisão. |
| P2-06 — decisão/RH | Parcial | Revisão informada com premissas, versões e alternativas rejeitadas; opção de solicitar alteração; justificativa; papéis RH/Operações/Finanças; manter rascunho sem execução. |
| P2-07 — interface/evals | Parcial | Mostrar A–E, custos totais, cobertura mínima, SLA, backlog, capacidade após contratação, inviabilidade, riscos, comparação e validação independente; reidratação de decisões. |
| INT-01 — integração | Parcial, refatorar | Integrar um agente P1/P2 às ferramentas determinísticas e validadores externos, com retorno a investigação/planejamento, versionamento e consentimento humano. |
| INT-02 — teste E2E | Parcial | Testar dois times, conflitos, histórico insuficiente, falha de Jira, solver inviável, lead time depois do pico, habilidades, regra revogada, segregação e cenários A–E. |
| INT-03 — entrega | Pendente | Piloto observacional: nenhum write-back, roteiro reproduzível, indicadores antes/depois, matriz LGPD e gates de RH/jurídico/Operações; experimento em três braços na fase apropriada. |

**Resultado:** nenhuma das 15 tasks P1/P2 possui prova de aceite integral conforme v4.2. A arquitetura existente é aproveitável, mas permanece **uma implementação parcial do escopo anterior**, não o MVP v4.2 completo.

## 3. Mudanças específicas nos contratos

Criar nova versão sem alterar silenciosamente schemas persistidos existentes; definir migrações e testes de contrato.

- **DemandSnapshotV2:** team_id, skill_id, intervalo, entradas, conclusões, backlog_inicial/final, cancelamentos, reaberturas, demanda_nao_atendida, SLA, unidade, origem e versão. Documentar conservação de estoque/backlog e evitar dupla contagem.
- **SkillCapacitySnapshotV2:** pools, elegibilidade por skill/turno/intervalo, disponibilidade real, qualificação concluída, calendário, capacidade sustentável, custos agregados, ausência não clínica e dados faltantes.
- **InvestigationReportV2:** hipótese com status `observed`/`tested`/`unverified`, evidence_refs e `manager_reports[]` (autor, data, relato, origem). Nunca transformar relato em evidência suficiente por si só.
- **ScenarioCandidateV2:** category A/B/C/D/E, role_mix, lead_time_and_ramp_up, legal_flags, dependencies, costs_estimated, ações, premissas e versões.
- **SimulationResultV2:** forecast_version, solver_status, feasible, mandatory_coverage_met, capacity_by_skill, shift_coverage, residual_deficit, backlog, cost_range, sensitivity e limitações.
- **DecisionRecordV2:** human_approver, approved_scope, premises_reviewed, model_and_rule_versions, rationale e timestamp; avaliar autorização/alteração de propostas sem executar ações.
- **PostActionReviewV1:** observed_metrics, forecast_errors, unintended_effects, contestations, next_step e reviewer. Planejar para a fase piloto integrado.

## 4. Sequência de correção e gates

### P0 — segurança e verdade dos dados (bloqueia recomendação)
- Completar modelo de demanda e testes de reconciliação de entradas, conclusões e backlog.
- Implementar cobertura mínima obrigatória por intervalo/skill e distinguí-la de déficit operacional.
- Implementar validadores independentes fail-closed; nenhuma aprovação sem verificação de restrições rígidas e premissas.
- Endurecer políticas jurídicas parametrizadas por vigência e os controles de privacidade por fluxo.
- Garantir que incapacidade de cumprir lead time/ramp-up jamais apareça como contratação eficaz para o pico.

### P1 — baseline determinístico sem LLM (braço 2)
- Forecast com intervalo e backtesting; solver OR-Tools e custo total; cinco categorias A–E.
- Jira somente leitura e duas equipes de um mesmo segmento.
- Interface que não mistura valores ilustrativos com decisões reais.
- Testes de regressão de infeasibilidade, separação de unidade, custo desconhecido, reidentificação e abstenção.

### P2 — agente único e verificação incremental
- Substituir múltiplos agentes separados por **um agente investigador-planejador** integrado a LangGraph e ferramentas tipadas autorizadas.
- Instrumentar custo, latência, tokens, perguntas, hipóteses e quantidade de correções; executar o mesmo caso no braço 2 e no braço 3.
- Não implementar agente crítico autônomo como verificador determinístico ou autoridade de aprovação.

### P3 — piloto de observação e três braços
- Comparar processo atual, cálculo sem LLM e agente + cálculo; medir SLA, erros, tempo de análise, custo total e efeitos adversos.
- Revisão de jurídico, RH, Operações, Finanças, privacidade e retenção antes de dados reais.
- O modo de observação não muda escalas, ponto ou vagas automaticamente.

## 5. Orientação para a branch de auditoria

- Preservar commits e código reconciliados da v4.1 como base histórica; **não declarar a branch pronta para merge ou implantação**.
- A matriz anterior `docs/AUDITORIA_P1_P2.md` registra apenas a revisão v4.1 e permanece como evidência histórica.
- Este documento é a nova matriz de aceitação. Cada implementação futura deve citar task, campo/critério da v4.2, teste automatizado e versão de schema.
- Atualizar o planejamento `requisitos/docs/Divisao_IA_Backend_Alinia.md` em uma revisão específica; não apagar as decisões históricas da v4.1.
- Priorizar integridade, cálculo e validação antes de criar mais agentes ou UX de funcionalidades sem base de dados.

**Limitações:** revisão estática de documentos e código GitHub. Nenhuma suíte de testes/migração foi executada neste rebaseline; regras jurídicas e bases legais exigem validação competente.

## 6. Execução de correções na branch de auditoria (08/11/2026)

**Status:** baseline v4.2 implementado em módulos; **MVP integral ainda não concluído**.
As alterações foram versionadas em commits da branch
`audit/p1-p2-reconciliacao-2026-11-08`, sem modificar `main`.
Teste automatizado está em `.github/workflows/p1-p2-integration.yml`;
consultar o último commit antes de informar um número de testes aprovado.

| Task | Mudança implementada | Pendência para aceite integral |
|---|---|---|
| COM-01 | Contratos `contracts/v42.py` e validação de demanda | Migrações de schema de domínio e matrizes completas de competência |
| P1-01/P1-02 | CSV com ledger de demanda, deduplicação por skill, endpoint agregado | Conector de eventos real e cobertura horária por competência |
| P1-05 | Baseline com janelas semanais, validação temporal e faixa empírica | Benchmark sazonal, previsão por skill/turno e validação ampla |
| P2-03 | Cinco famílias A–E, lacunas e aprovações bloqueadas se inconclusivas | Simular efetivamente as alternativas B/C/D |
| P2-04 | Solver OR-Tools CP-SAT novo, testado de forma isolada | Integrar ao pipeline, dados de turnos/custos e regras aprovadas |
| P2-05/P2-06 | Validador independente + gate fail-closed em aprovação | Persistir e vincular evidência do verificador ao cenário |
| P2-07 | Cinco opções exibidas na interface | Reidratação completa, UI de orçamento e revisão efetiva |
| INT-02 | Testes novos v4.2 e workflow CI | Testes adversariais e validação interinstitucional |
| INT-03 | README e matrizes atualizadas | Evidências do piloto de observação e validações externas |

**Regra de segurança:** nenhuma task deve ser marcada como concluída apenas
porque um módulo compila ou os testes isolados passam. Para liberar recomendações
operacionais, faltam fontes verificadas, regras e evidências auditadas, integração
end-to-end, avaliação independente e aprovação de domínio.
