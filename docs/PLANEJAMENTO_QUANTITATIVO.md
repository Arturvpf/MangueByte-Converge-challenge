# Planejamento quantitativo e demonstração

Prepare o backend e a conta RH seguindo o [README](../README.md). Abra a [plataforma local](http://127.0.0.1:8000/prototype/app/), clique em **Conectar dados**, entre e use **Carregar dados sintéticos → Carregar demonstração → Abrir investigação**. Uma conta RH de uma empresa vazia pode criar o recorte `team-demo`. Selecione **Previsão**, **Cenários** e **Revisão do RH** para ver os resultados. O fluxo funciona com SQLite e sem Jira ou provedor de LLM.

A mesma carga autenticada está disponível em `POST /api/imports/synthetic` com `{"team_id":"team-demo","profile":"pico-e-retomada"}`. Um novo `profile` ou `extra_weeks` de 1 a 8 produz outro snapshot. Repetir os parâmetros retorna o mesmo recorte no mesmo escopo.

Para gerar um CSV reproduzível na raiz do repositório:

```bash
python -m backend.app.ingestion.demo --profile pico-e-retomada --output alinia-demo.csv
```

O endpoint sintético usa o mesmo parser e confirma o recorte com origem `synthetic` definida pelo servidor. O upload genérico registra origem CSV mesmo se o arquivo tiver o mesmo nome.

## Dados e resultados

O gerador usa a semente fixa 4115. São 88 semanas, três competências, dois turnos, cinco pools e cinco perfis. `gargalo` concentra o déficit em suporte especializado e atendimento noturno, `pico` aumenta a carga noturna em parte do ciclo, `estrutural` eleva a carga especializada e `turnos` desloca demanda de atendimento para a noite. A série contém variação, ciclo de 13 semanas, tendência suave e mudança histórica de nível. O histórico mensal do Investigador continua disponível no chat Centro, com granularidade mensal própria.

**Pico sazonal e retomada** é o perfil selecionado inicialmente no painel. A cada 13 semanas, o volume aumenta por duas semanas, principalmente em atendimento noturno e suporte especializado diurno. O gerador calcula o backlog de cada turno a partir das chegadas registradas, reaberturas, cancelamentos e atendimento possível com os pools compartilhados. Ao fim do pico, as folgas de capacidade permitem reduzir o backlog histórico. O modelo de forecast e o solver processam esse perfil pela mesma API usada pelos demais recortes.

| Semana | P50 da equipe (casos) | A · Permanente | B · Temporária | C · Realocação | D · Redesenho | E · Referência |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 09/11 | 339 | 0 h | 0 h | 0 h | 0 h | 0 h |
| 16/11 | 428 | 25 h | 0 h | 21 h | 19 h | 21 h |
| 23/11 | 479 | 4 h | 0 h | 47 h | 43 h | 47 h |
| 30/11 | 361 | 0 h | 0 h | 0 h | 0 h | 0 h |

As horas da tabela são o déficit de cada cenário. O temporário cobre as duas semanas do pico e termina antes da retomada. No cenário E, a quarta semana cobre a demanda semanal e ainda carrega cerca de 128 casos equivalentes de backlog. Os valores são projeções sintéticas exploratórias.

O ledger soma chegadas e demanda fora do registro para estimar demanda total. O backlog registrado conserva `inicial + entradas + reaberturas − conclusões − cancelamentos = final`. A projeção usa as reaberturas recentes como carga adicional de serviço e apresenta backlog em casos equivalentes. O saldo inicial observado entra na primeira semana. As semanas seguintes carregam o saldo residual sob as horas de serviço comprometidas. O arquivo não contém registros individuais.

| Perfil gargalo | Déficit em quatro semanas | Ganho frente a E | Faixa de custo incremental | Início de capacidade adicional ou redistribuída |
| --- | ---: | ---: | ---: | ---: |
| A · Permanente | 115 h | 97 h | R$ 5.680–9.480 | 14 dias |
| B · Temporária | 119 h | 93 h | R$ 5.019,20–8.271,20 | 7 dias |
| C · Realocação e capacitação | 207 h | 5 h | R$ 480–900 | 14 dias |
| D · Redesenho de turnos | 174 h | 38 h | R$ 320–620 | 7 dias |
| E · Não intervir | 212 h | 0 h | R$ 0 | Imediato |

As faixas acima são hipóteses agregadas. A e B consideram horas pagas dentro do horizonte e custo de admissão e capacitação. A contratação permanente passa por recrutamento, admissão, formação e ramp-up de 60%, 85% e 100%. O contrato temporário dura duas semanas, com ramp-up de 85% e 100%. A formação consome horas de mentoria na semana anterior à entrada. C reduz horas na origem durante a capacitação e transfere parte do orçamento do mesmo pool após a transição. D redistribui horas do mesmo pool entre turnos dentro de um limite. Custos ausentes são nulos. O custo de E é incremental e exclui o custo da operação já existente.

## Previsão, solver e filas

- **Forecast.** Compara mediana móvel de quatro semanas com baselines sazonais de 13 e 52 semanas quando há histórico anterior suficiente. A seleção usa origens de calibração. Os resíduos são calculados para cada antecedência. As janelas-alvo da calibração e do holdout são disjuntas. O backtest publica MAE, WAPE, cobertura e perdas quantílicas. Os percentis são publicados quando o holdout passa os limites de cobertura e de caudas. Oito origens de avaliação dão evidência limitada. Lacunas e histórico curto geram abstenção. Uma mudança recente de nível superior a 50% bloqueia o uso da estimativa no planejamento. Se ainda não houver origens suficientes para calibrar, o baseline pontual pode alimentar uma simulação exploratória. Se houver holdout suficiente e a avaliação falhar, a série fica fora do planejamento.
- **CP-SAT.** Usa a mesma matriz de demanda em A–E e prioriza o déficit no horizonte, com o custo de contratação como desempate. O limite semanal do pool é compartilhado por todas as competências e turnos. A capacidade do último recorte semanal se repete no horizonte na ausência de outra evidência. O campo CSV opcional `mandatory_hours` insere mínimos de cobertura na simulação como restrições rígidas. As metas operacionais admitem déficit. As projeções guardam origem, snapshot, horizonte, versão do forecast, versão do solver, semente, status e premissas.
- **Validação.** A verificação independente confere cobertura, elegibilidade, orçamentos de horas e prazos matemáticos. A aprovação operacional segue bloqueada na ausência de comprovação de jornada, repouso, categoria, contrato, modalidade, instrumento vigente e orçamento aprovado. O cenário exploratório não pode ser aprovado mesmo se o solver encontrar a solução ótima. O modelo semanal não representa uma escala diária.
- **SimPy.** Usa chegadas Poisson por competência e turno e tempos de serviço Gamma com produtividade e variabilidade explícitas. Cada fila usa horas comprometidas distribuídas ao longo da semana. São 12 execuções com sementes comuns aos cenários, médias e amplitudes. A idade do backlog inicial é desconhecida, e o denominador do SLA só inclui chegadas cujo prazo de SLA teve tempo para vencer. Sem backlog inicial, SLA, produtividade e variabilidade adequados, a saída é indisponível.

## Revisão e observações

O RH pode revisar um snapshot confirmado da mesma equipe e registrar uma justificativa em `POST /api/investigations/{run_id}/replan`, com `snapshot_id`, `expected_version`, `idempotency_key` e `reason`. A revisão usa o novo forecast e recalcula A–E. A API aceita `premises.hiring_budget_brl` e `premises.mobility` com pool, competência e turno de destino, semanas de transição, horas de treinamento/mentoria, limite de horas transferíveis e custo opcional. As premissas são exploratórias e validadas contra o recorte. O painel permite alterar o teto de contratação ou escolher outro snapshot. Relatos livres não entram no cálculo. `GET /api/investigations/{run_id}/evidence` lista as revisões.

Na demonstração, selecione E na revisão do RH e registre **Adiar**. Abra **Resultados observados** para registrar chegadas, backlog final, SLA, custo, efeito adverso, contestação e justificativa. O backend compara a semana com a projeção e sinaliza desvios para nova investigação. Esse fluxo acompanha a decisão humana de adiar, com a operação de referência. Observações sobre uma intervenção requerem uma decisão de aprovação vinculada à versão.

## Coleta Jira e interface do agente

Configure no servidor `JIRA_BASE_URL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `ALINIA_JIRA_TENANT_ID`, `ALINIA_JIRA_TEAM_ID`, `ALINIA_JIRA_CAPACITY_SNAPSHOT_ID` e `ALINIA_JIRA_SKILL_MAP` (JSON com ID de tipo de chamado e competência). Use um token compatível com autenticação Bearer e limitado à leitura do projeto. Configure um snapshot semanal da equipe com capacidade e produtividade autorizadas.

`POST /api/imports/jira/sync` verifica o escopo antes de ler páginas do Jira Cloud. A coleta refaz a janela de 88 semanas fechadas para admitir correções, elimina duplicatas da paginação e grava apenas contagens semanais. O checkpoint registra o último sucesso e o snapshot por empresa, equipe e fonte. Falhas de paginação ou mapeamento deixam o checkpoint anterior intacto. Chegadas são contadas pela data de criação. Jira não fornece evidência de turnos, produtividade, demanda não registrada ou retrabalho nesta integração. [Referência do endpoint Jira Cloud](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/).

Para automatizar a coleta, execute `python -m backend.app.ingestion.jira_worker --interval-seconds 3600` com `ALINIA_JIRA_API_BASE`, `ALINIA_JIRA_TENANT_ID`, `ALINIA_JIRA_WORKER_EMAIL` e `ALINIA_JIRA_WORKER_PASSWORD` de uma conta restrita à equipe. O worker obtém um token novo a cada ciclo. Para uma execução avulsa, omita o intervalo e use `ALINIA_JIRA_WORKER_TOKEN` se o agendador já fornecer um token. O Jira real requer configuração e validação na instalação.

O endpoint `GET /api/investigations/{run_id}/planning-summary` exige acesso a dados e cenários na equipe. Retorna totais e campos controlados para a ferramenta tipada `read-planning`, sem relatos, nomes de fonte ou IDs de pools. Séries operacionais de baixo volume são suprimidas. O canal `/v1/channels/workflow/investigate` exige `ALINIA_WEBHOOK_TOKEN` para investigações operacionais e lê a API com `ALINIA_API_BASE` e um `ALINIA_API_TOKEN` de escopo restrito. Sirva esse canal apenas para operadores com o mesmo escopo do token de serviço. Cada parecer quantitativo abre uma sessão própria. O agente consome resultados calculados pelo workflow e a orquestração integral do LLM continua fora deste fluxo.

## Verificação

```bash
python -m pytest backend/tests -q
python -m alembic -c backend/alembic.ini upgrade head
node --check src/app/app.js
npm run build
npm --prefix alinia-investigator ci
npm --prefix alinia-investigator run check
npm --prefix alinia-investigator test
```
