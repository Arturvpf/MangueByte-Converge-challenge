# Correções pós-auditoria — PRD v4.2 (2026-11-08)

> Esta branch é uma continuação **incremental** da branch `audit/p1-p2-reconciliacao-2026-11-08`.
> O PRD v4.2 continua sendo a fonte de verdade. **Não há aceite do MVP nem autorização para uso com dados pessoais reais.**

## Alterações implementadas

| Auditoria | Resultado | Arquivos principais |
|---|---|---|
| BUG-006 — checkpoints Jira cruzam equipes | **Corrigido no código**: identidade agora inclui tenant, equipe, origem e issue; estado legado sem equipe fica em tabela separada e nunca alimenta deduplicação | `flow/models.py`, `ingestion/service.py`, migração `0009`, `test_jira_scope_v42.py` |
| BUG-008 — revisão não cria novo plano | **Corrigido o versionamento**: novo ciclo gera novo conjunto de 5 cenários; histórico permanece; aprovar versão obsoleta retorna conflito | `workflow/service.py`, `workflow/api.py`, `planning/planner.py`, `decisions/service.py`, migração `0010` |
| BUG-002 — previsão não entra no solver | **Mitigado por abstenção**: o workflow informa que a previsão não foi convertida para necessidade por skill/turno, e não marca cenários como conclusivos | `workflow/service.py`, `planning/planner.py` |
| BUG-009 — escopo jurídico desconhecido | **Mitigado por bloqueio**: política global não prova regra aplicável a categoria/contrato desconhecidos; requer revisão humana antes de conclusão | `workflow/service.py` |
| BUG-010 — sessão volátil no frontend | **Corrigida a retomada após novo login**, mediante índice de execuções restrito por tenant/equipe. Token nunca é persistido no navegador | `workflow/api.py`, `src/app/app.js`, `test_int02.py` |
| BUG-011 — cobertura da previsão otimista | **Melhorado**: calibração separada e validação de erro simultâneo em todas as quatro semanas, ao menos oito origens de holdout, com embargo temporal para evitar sobreposição | `forecast/engine.py`, `test_forecast.py` |
| BUG-005 — exposição de metadados do Jira | **Mitigado**, não concluído: leitura restrita a projeto explícito, sem campo `summary`, paginação limitada e falhas tipadas; importação real continua indisponível | `ingestion/jira.py`, `core/config.py` |
| Defeito adicional no CP-SAT | **Corrigido**: hora de contratação renovada por bucket temporal disjunto, não consumida uma vez por horizonte inteiro | `optimization/cpsat_v42.py`, `test_cpsat_v42.py` |
| Informação de UI | **Corrigido**: déficit desconhecido não é mostrado como zero; altura da barra usa estimativa real | `src/app/app.js` |

## Limites que permanecem — não rotular como implementados

1. **BUG-001** — CP-SAT v4.2 ainda não está acoplado à orquestração produtiva; a implementação testada continua sendo um motor isolado. Para integração é necessária matriz temporal autorizada com competências, habilidades e limites jurídicos.
2. **BUG-002** — ainda não existe série de demanda futura por skill e turno suficiente para planejamento conclusivo; apenas a classificação de segurança foi corrigida. Nenhuma contratação pode ser indicada a partir do forecast agregado.
3. **BUG-003** — cenários B/C/D continuam propostas exploratórias, não alterações matematicamente simuladas. Cenário A carece de custos/lead time reais. E é baseline.
4. **BUG-004** — validação independente válida ainda não é produzida de ponta a ponta. **Não retirar** o bloqueio de aprovação; exigir hash, versões, política, cobertura e comprovantes independentes.
5. **BUG-005** — integração Jira live **não faz ingestão**, apesar de cliente GET seguro. Falta mapear eventos/semântica, juntar disponibilidade autorizada e registrar sync idempotente.
6. **BUG-007** — LangGraph atual ainda é mock separado. Não existe agente LLM operacional, tool calling seguro, evals ou prova incremental de valor.
7. **BUG-008** — versões e histórico são atualizados, mas respostas de gestor não alteram números sem fontes verificadas; ainda falta uma interface de revisão material que obtenha novos dados.
8. **BUG-009** — não existe cadastro operacional de categoria/contrato/CCT assinado por RH/jurídico para desbloqueio seguro. Bloqueio deve continuar.
9. **BUG-011** — intervalos continuam empíricos, nunca P10/P50/P90 probabilísticos. Ganho contra baseline sazonal, deriva, validação por horizonte e piloto ainda precisam de evidência.

## Migrações

- `0009_jira_checkpoint_scope`: renomeia tabela legada para `jira_checkpoints_legacy_unscoped` e cria nova tabela com PK composta. Não tenta adivinhar a equipe de checkpoints históricos. Downgrade é bloqueado quando existem novos checkpoints ativos.
- `0010_scenario_cycle_versions`: substitui UNIQUE(run_id,kind) por UNIQUE(run_id,kind,version), conservando versões anteriores. Downgrade é bloqueado quando existem revisões múltiplas.

## Testes novos ou alterados

- Importação Jira para duas equipes distintas de um mesmo tenant.
- Preservação de checkpoints legados durante upgrade Alembic.
- Recuperação do índice de investigações entre tenants após login.
- Replanejamento de 5 para 10 cenários históricos com 5 atuais, com bloqueio de aprovação de versão antiga.
- Jira sem leitura de `summary` e sem consulta ampla quando falta projeto.
- Intervalos de quatro semanas sem vazamento temporal, histórico curto e drift.
- CP-SAT: contratação atende duas semanas disjuntas com capacidade por intervalo.

Executar:

```sh
python -m pytest backend/tests -q
python -m alembic -c backend/alembic.ini upgrade head
npm run build
```

CI de PR valida as três tarefas, mas **não** valida PostgreSQL povoado, Jira real, LLM, privacidade contextual, requisitos jurídicos, saída adversarial nem piloto em três braços.

## Critérios obrigatórios para seguir

- Implementar dados/fonte de capacidade por turno e previsão por skill com versões.
- Integrar CP-SAT v4.2 e validador externo real a cenários A–E e persistir evidência verificável vinculada ao hash do cenário.
- Ensaio E2E: ingestão autorizada → forecast → solver → validação independente → revisão efetiva, inclusive falhas e revogação.
- Manter escrita externa, requisições e mudanças de escala **desativadas** até aceite formal de RH, jurídico, Operações, Financeiro e privacidade.

**Status:** alterações incrementais com limites declarados; PR continua **draft**.
