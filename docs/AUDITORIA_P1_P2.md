# Auditoria de rastreabilidade P1/P2 — 08/11/2026

Base: `requisitos/docs/Divisao_IA_Backend_Alinia.md`; PRD v4.1, MVP 2.5; branches `p1/dados-investigacao` e `p2/policy-store`.

**Legenda:** Parcial = existe implementação, mas não atende integralmente ao aceite. Implementado = código e testes correspondentes identificados; **não é aprovação de execução**. Pendente = componente ou validação importante não entregues.

| ID | Estado auditado | Evidência e lacuna |
|---|---|---|
| COM-01 | Parcial | `backend/app/contracts/v1.py`, fixtures; validação formal conjunta não registrada |
| COM-02 | Implementado | FastAPI, Alembic, banco, OpenAPI, testes; execução local nesta auditoria não realizada |
| P1-01 | Parcial | snapshots e isolamento em `app/data`; cadastros completos de cargos, custos e turnos não são CRUD operacionais |
| P1-02 | Parcial | `ingestion/csvparse.py`, `service.py`; falta UX de importação e validação em operação real |
| P1-03 | Parcial | conector GET e fixture Jira; `/jira/sync` ainda retorna 503 sem ingestão real |
| P1-04 | Parcial | métricas e teste homogêneo; faltam custo, cobertura completa e dimensão temporal |
| P1-05 | Parcial | mediana móvel, MAE e WAPE; sem intervalos calibrados ou comparação sazonal de baseline |
| P1-06 | Parcial | `investigation/report.py` determinístico; sem agente LLM que investigue e atualize hipóteses |
| P1-07 | Parcial | `jobs/graph.py` e poller são mocks; fluxo real em `workflow/service.py` é síncrono |
| P1-08 | Parcial | telas ligadas a APIs; recarga e modos demo/real ainda não completos; falta eval adversarial |
| P2-01 | Parcial | auth/RBAC/audit implementados; rate limiting, concorrência e testes de produção pendentes |
| P2-02 | Parcial | Policy Store versionado com revisão humana; aplicação detalhada por jornada/turno no solver pendente |
| P2-03 | Parcial | três cenários tipados; planejador determinístico sem planejamento contextual por LLM |
| P2-04 | Parcial | max-flow aloca horas; não há OR-Tools CP-SAT, restrições completas ou sensibilidade financeira |
| P2-05 | Parcial | crítico determinístico bloqueia casos básicos; sem análise adaptativa de riscos e revisões |
| P2-06 | Parcial | decisão e rascunhos internos persistidos; explicação dos trade-offs e revisão material ainda limitadas |
| P2-07 | Parcial | UI conectada a cenários/RH, mas não íntegra na recarga, sem evals completos |
| INT-01 | Parcial | fluxo sequencial ligado via APIs; ainda não conecta agentes LangGraph reais com ferramentas verificáveis |
| INT-02 | Parcial | `test_int02.py` cobre restart, isolamento e regra revogada; faltam casos adversariais e concorrência no workflow real |
| INT-03 | Pendente | README e fixtures presentes, mas faltam evidências reproduzidas do piloto e liberações de RH/jurídico/privacidade |

## Correções nesta branch
- Integração em commit de merge preservando ambas as histórias P1 e P2.
- Alembic: merge revision `0007_merge_p1_p2` com pais `0004a` e `0006`; precisa teste real em SQLite e PostgreSQL.
- Respostas 422 sem refletir chaves ou dados controlados pelo usuário.
- Contratação só é conclusiva se a simulação cobre todo déficit e não há bloqueios explícitos; distribuição de pools por skill, sem fingir que isso resolve mix de cargos.
- Custo não estimado continua nulo.
- Forecast: ao menos quatro origens de backtesting antes de marcar baseline calibrado.
- Verificação temporal das políticas durante o horizonte de previsão; conflitos suspendem conclusão.
- Testes atualizados e regressões adicionadas para multi-skill e dados insuficientes.

## Gatilhos de bloqueio
Nenhuma implantação com dados reais, nenhuma requisição automática e nenhuma alteração de escala. Não rotular a solução como OR-Tools ou multiagente LLM. Falta execução independente da suíte e comparação das migrations em bancos existentes.

## Próximas mudanças necessárias
1. Integrar demanda prevista por skill/turno ao solver, com rastreabilidade temporal de cada hipótese.
2. Implementar OR-Tools com limitações de jornada, repouso, custos, mentoria, orçamento e contratação inteira.
3. Orquestração LangGraph real com ferramentas tipadas, checkpoints transacionais, idempotência e limites.
4. Jira real read-only com paginação, tradução de unidades, checkpoint e teste autorizado.
5. Persistência/reidratação de frontend, UX de carregamento e estados reais versus protótipo.
6. Evals de prompt injection, autorização, múltiplos tenants, orçamento, solver inviável e políticas revogadas.
7. Validar com RH/operação/jurídico as regras aplicáveis e documentar privacidade e retenção.
