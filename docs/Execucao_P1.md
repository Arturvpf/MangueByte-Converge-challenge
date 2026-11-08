# Execução P1 — registro de andamento

Registro desta execução; não substitui a entrega operacional INT-03.

## Responsabilidades e revisão

| Papel | Modelo | Responsabilidade |
|---|---|---|
| Supervisão | Root | Coordenação geral e gates |
| Orquestração técnica | GPT-6.1 Terra, high | Dependências e registro de andamento |
| COM-01 — autor | GPT-6.1 Terra, high | Contratos e fixtures |
| COM-01 — revisor | GPT-6.1 Sol, high | Revisão técnica independente |
| COM-02 — autor | GPT-6.1 Terra, high | Base executável do backend |
| COM-02 — revisor | GPT-6.1 Sol, high | Revisão técnica independente |
| P1-01 — autor | GPT-6.1 Terra, high | Cadastro e snapshots |
| P1-01 — revisor | GPT-6.1 Sol, high | Revisão técnica independente |
| P1-07 — autor | GPT-6.1 Terra, high | Núcleo de execução e mocks |
| P1-07 — revisor | GPT-6 Astra, high | Revisão técnica independente |
| P1-04 — autor | GPT-6.1 Terra, high | Núcleo de métricas |
| P1-04 — revisor | GPT-6 Astra, high | Revisão técnica independente |

Cada dependente começa somente após a aprovação do predecessor pertinente. Uma revisão reprovada retorna ao autor para correção e nova revisão; alterações de código feitas na revisão recebem commit próprio.

## Estado das entregas

### COM-01 — contratos e fixtures

- **Estado:** revisão técnica independente aprovada no commit `30fb18c`.
- **Commits registrados:** `548540b`, `d8f2870`, `30fb18c`.
- **Verificação informada:** 12 testes passaram.
- **Validação humana da Pessoa 2:** pendente, separada da aprovação técnica dos agentes. O plano original prevê validação das duas pessoas sobre os mesmos exemplos.
- Os contratos de cenários e revisão pertencem à Pessoa 2; interfaces compartilhadas propostas não transferem essa autoria.

### COM-02 — base executável do backend

- **Estado:** entregue e aprovada em revisão independente; implementação em `4ee5eb3` e revisão do README em `a858db1`.
- **Verificação:** autor e revisor executaram 25 testes, migrações em bancos SQLite e PostgreSQL 16.15 vazios, Uvicorn real com health check, documentação e OpenAPI, build do frontend e `pip check`. O revisor também confirmou autogeração de migração futura e sessão real em PostgreSQL.
- P2-01 permanece pendente; COM-02 não implementa identidade, autorização ou auditoria de P2-01.

### P1-01 — cadastro e snapshots

- **Estado:** implementação parcial aprovada em revisão independente em `179630c` (correção UTC). Commits `d709d4d`, `4a37404`, `058cebe` e `179630c`. A suíte registrou 51 testes passando, incluindo 19 de dados; migração e isolamento foram verificados em PostgreSQL 16.15.
- **Gate integrado:** aguarda P2-01 para autorização; aprovação técnica parcial não libera P1-02 nem encerra a subtask.

### P1-07 — execução durável

- **Estado:** núcleo com mocks aprovado por revisão independente em `0737745`, após implementação em `8ed6caa`. A revisão registrou 42 testes passando.
- **Pendente:** migração, registro, API e integração com nós reais; o núcleo aprovado não equivale ao fluxo completo.

### P1-04 — Metrics Engine

- **Estado:** núcleo parcial aprovado em revisão independente no commit `dfddd99`. A subtask completa permanece pendente.
- **Escopo do núcleo:** funções determinísticas e testes matemáticos com fixtures de COM-01. A implementação está em `8c8dce6` e a correção de precisão decimal, teto/orçamento e distinção entre demanda atual para IPD e projetada para dimensionamento em `dfddd99`. Autor, supervisor e revisor executaram 23 testes com sucesso. Verificações independentes confirmaram o exemplo 954,3534/14/3 e o comportamento com precisão decimal de ambiente 1 e traps.
- **Pendente:** integração com P1-01, persistência, API por snapshot, autorização e aceite completo. O núcleo é uma entrega parcial, não a conclusão da subtask.

## Dependências e bloqueios

| Entrega | Predecessores e condições relevantes | Estado |
|---|---|---|
| COM-02 | Base do backend | Entregue e aprovada após autorização do usuário |
| P2-01 | COM-02; identidade, autorização e auditoria da Pessoa 2 | Externo; ainda não disponível neste repositório |
| P1-01 | COM-01 e COM-02; P2-01 para aceite integrado | Implementação parcial aprovada; aceite integrado aguarda P2-01 |
| P1-02 | P1-01 aprovado | Bloqueada |
| P1-03 | P1-02 aprovado; credenciais autorizadas para validação real | Bloqueada; testes com fixtures não equivalem a validação real |
| P1-04 completa | COM-01 e integração com P1-01 | Núcleo parcial aprovado; integração e aceite completo bloqueados |
| P1-05 | COM-01 e séries de P1-01/P1-02 | Bloqueada pelas séries e seus predecessores |
| P1-07 | COM-01 e COM-02; P2-02/P2-04 para fluxo completo | Núcleo com mocks aprovado; migração, registro, API e nós reais pendentes |
| P1-06 | P1-04, P1-05 e P1-07 para execução integrada | Bloqueada pelos predecessores |
| P1-08 | P1-04 a P1-07 | Bloqueada pelos predecessores |
| INT-01 | P1-06/P1-07 e P2-03/P2-04/P2-05 | Bloqueada pelos predecessores de ambas as pessoas |
| INT-02 | INT-01, P1-08 e P2-07; responsabilidade da Pessoa 2 | Bloqueada |
| INT-03 | INT-02 | Bloqueada; este registro não é a entrega |

COM-02 foi autorizada pelo usuário para desbloquear P1; P2-01 e as demais entregas de P2 permanecem fora desta execução. Dependências externas adicionais incluem dados e unidades aprovados, histórico, credenciais Jira, políticas e ambiente do piloto, conforme o plano. Fixtures e mocks devem ser identificados e não representam integrações reais.

## Fila proposta de agentes

As atribuições abaixo são propostas; agentes ainda não foram criados para essas tarefas. Cada subtask terá autor próprio, revisão independente, commit de conclusão e nova revisão após eventual retrabalho pelo autor. O limite de quatro agentes simultâneos inclui a supervisão e a orquestração.

| Entrega futura | Autor proposto | Revisor proposto | Gate de início |
|---|---|---|---|
| P1-02 — CSV | GPT-6.1 Terra, high | GPT-6.1 Sol, high | P1-01 aprovado, inclusive aceite integrado aplicável |
| P1-03 — Jira | GPT-6.1 Terra, high | GPT-6.1 Sol, high | P1-02 aprovado; validação real exige credenciais autorizadas |
| P1-04 — integração | GPT-6.1 Terra, high | GPT-6 Astra, high | P1-01 aprovado |
| P1-05 — previsão | GPT-6.1 Terra, high | GPT-6 Astra, high | Séries de P1-01/P1-02 e aprovação dos predecessores |
| P1-06 — investigador | GPT-6.1 Terra, high | GPT-6 Astra, high | P1-04, P1-05 e P1-07 para execução integrada |
| P1-08 — telas e evals | GPT-6.1 Terra, high | GPT-6.1 Sol, high | P1-04 a P1-07 aprovadas |
| INT-01 — integração | GPT-6.1 Terra, high | GPT-6 Astra, high | P1-06/P1-07 e P2-03/P2-04/P2-05 aprovadas |

Migrações e registro em arquivos comuns devem ser integrados em sequência, com uma única cadeia de revisões e nova verificação do diff integrado. Nós simulados são identificados e não contam como integração real.

