# Backend Alinia

Base COM-02 com Python 3.12, FastAPI, SQLAlchemy e Alembic. **Para uma instalação completa, incluindo a diferença entre servidor estático e frontend integrado, veja primeiro o [README principal](../README.md).** Este arquivo detalha os contratos, permissões e módulos internos. As seções de histórico abaixo descrevem também limitações da implementação anterior à reconciliação PRD v4.2. Execute os comandos na raiz do repositório. Em PowerShell:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements.lock.txt
backend/.venv/Scripts/python -m alembic -c backend/alembic.ini upgrade head
backend/.venv/Scripts/python -m uvicorn backend.app.main:create_app --factory --reload
```

Em Linux/macOS use `backend/.venv/bin/python` no lugar do caminho acima. A configuração padrão usa SQLite local (`alinia.db` na raiz, ignorado pelo Git). Abra `http://127.0.0.1:8000/health` e `http://127.0.0.1:8000/docs`; o OpenAPI está em `/openapi.json`. O health confirma que o processo responde, não a disponibilidade do banco. Migrações são explícitas e não rodam na inicialização.

Para PostgreSQL, configure `DATABASE_URL` no ambiente antes das migrações e do servidor, no formato SQLAlchemy `postgresql+psycopg://usuario:senha@host:5432/banco`; faça percent-encoding de caracteres especiais na senha. Use credenciais locais ou um gerenciador de segredos, sem gravá-las no repositório. Exemplo PowerShell sem valor: `$env:DATABASE_URL = '<URL fornecida pelo ambiente>'`. Para voltar ao SQLite remova a variável. SQLite é destinado a desenvolvimento e testes.

```powershell
backend/.venv/Scripts/python -m pytest backend/tests
```

## Extensão

Cada domínio declara um `DomainModule` em `app/core/modules.py`, com seus `APIRouter`s e `JobDefinition`s, e o adiciona a `DOMAIN_MODULES`. O registro apenas disponibiliza definições em `app.state.jobs`: não agenda nem executa trabalhos; fila, worker e recuperação pertencem a P1-07. Nomes duplicados são rejeitados. Cada aplicação possui configuração, engine, fábrica de sessões e registro próprios. Use `app.state.session_factory` para criar sessões de curta duração e fechá-las após o uso.

Modelos futuros herdam de `Base` em `app/core/database.py`; importe os módulos de modelos em `migrations/env.py` antes de gerar revisões. Gere com `python -m alembic -c backend/alembic.ini revision --autogenerate -m "descricao"`, revise o arquivo e aplique com `upgrade head`. A revisão inicial é uma baseline vazia; cada domínio cria sua própria migração.

## Identidade, permissões e auditoria (P2-01)

**Configuração.** Defina `ALINIA_AUTH_SECRET` (mínimo 32 caracteres, gerado localmente, nunca versionado) antes de subir o servidor; sem ela o login responde 503 e as rotas autenticadas respondem 401. `ALINIA_ACCESS_TOKEN_TTL_SECONDS` (padrão 3600) controla a validade do token. Exemplo PowerShell: `$env:ALINIA_AUTH_SECRET = '<segredo local>'`.

**Primeiro acesso.** Após `upgrade head`, crie a empresa e o administrador pela CLI. A senha vem de `ALINIA_BOOTSTRAP_PASSWORD` ou do prompt, nunca da linha de comando:

```powershell
backend/.venv/Scripts/python -m backend.app.auth.cli create-tenant --tenant-id empresa-a --name "Empresa A"
backend/.venv/Scripts/python -m backend.app.auth.cli create-user --tenant-id empresa-a --email admin@empresa-a.example --role admin
```

**Autenticação.** `POST /api/auth/login` (`tenant_id`, `email`, `password`) devolve um token HS256 assinado no servidor; envie `Authorization: Bearer <token>`. `GET /api/auth/me` mostra a identidade; `POST /api/auth/logout` revoga todos os tokens do usuário. A cada requisição, usuário, empresa, versão do token e vínculos são lidos do banco: desativar um usuário ou trocar seus vínculos vale imediatamente. Identidade e empresa nunca vêm do corpo da requisição, de argumentos de ferramenta ou de texto do LLM.

**Perfis.** Vínculos (`memberships`) ligam o usuário a um perfil e a uma equipe; equipe vazia significa a empresa inteira (só RH e admin). A matriz está em `app/auth/permissions.py`:

| Permissão | gestor | rh | admin |
|---|---|---|---|
| `data:read`, `investigation:run`, `investigation:answer`, `scenario:read` | sim | sim | — |
| `decision:write`, `requisition:draft`, `policy:write`, `policy:approve` | — | sim | — |
| `policy:read` | sim | sim | sim |
| `audit:read` | — | sim | sim |
| `user:manage` | — | — | sim |

`/api/admin/users` (criar, listar, trocar vínculos, desativar) exige `user:manage` na empresa inteira e só enxerga a própria empresa.

**Como proteger um endpoint.** Use as dependências de `app/auth/dependencies.py`: `require_permission(P)` (qualquer vínculo com P), `require_team_permission(P)` (lê o parâmetro de rota `team_id`) e `require_tenant_permission(P)` (vínculo de empresa inteira). Elas devolvem o `Principal`; o escopo de consulta sai dele (`principal.tenant_id`, `principal.team_ids(P)`, `principal.tenant_wide(P)`), como em `get_data_scope` de `app/data/api.py`. Toda negativa 403 dessas dependências gera evento `authz.denied`. Negativas lançadas dentro dos próprios handlers devem ser auditadas pelo módulo dono.

**Ferramentas e worker.** `app/auth/tools.py` oferece `authorize_tool(principal, P, tenant_id=..., team_id=...)`, que confere o envelope da ferramenta contra o principal, e `PrincipalBoundary`, que implementa `IntegrationBoundary` de `app/jobs/engine.py` (operação desconhecida é negada).

**Auditoria.** `record_event(session, action=..., outcome=..., tenant_id=..., ...)` de `app/audit/log.py` adiciona o evento na mesma transação da mudança (quem chama faz o commit). Os detalhes passam por `sanitize_details`: chaves e valores com dados pessoais (e-mail, CPF, nome, salário, saúde, prompt etc.) são removidos ou mascarados. A tabela `audit_events` é somente inclusão: o ORM e triggers do banco (SQLite e PostgreSQL) bloqueiam UPDATE, DELETE e sobrescrita por `INSERT OR REPLACE`/upsert. As colunas `team_id`, `resource_id` e `trace_id` não passam pelo filtro de detalhes, então só aceitam identificadores opacos: `team_id` e `resource_id` no formato `[A-Za-z0-9._~-]{1,128}`. `GET /api/audit` exige `audit:read` e filtra por empresa e equipes do leitor; a própria leitura também é auditada. Cada resposta traz `X-Trace-Id`: o valor do cliente só é aceito se for um ID opaco (32 caracteres hexadecimais ou UUID, guardado como 32 hex minúsculos); qualquer outro valor é trocado por um ID gerado. Erros 422 nunca devolvem o valor enviado, só `type`, `loc` e `msg`. O trace correlaciona os eventos; fora de requisições use `use_trace_id()`.

**Limitações conhecidas.**
- Não há limite de tentativas de login nem refresh token. Cada falha de login em empresa existente grava um evento de auditoria, então um rate limit é necessário antes do piloto.
- O token não é revogável individualmente: logout revoga todos os tokens do usuário.
- Os IDs de equipe nos vínculos não são validados contra um cadastro de equipes.
- Dois admins que se rebaixam ao mesmo tempo podem deixar a empresa sem admin. A proteção atual vale por requisição.
- As negativas por equipe lançadas dentro dos handlers de dados (`ForbiddenScope`) ainda não são auditadas. Cabe à P1 instrumentar.

## Policy Store (P2-02)

Regras trabalhistas ficam no banco, nunca como limite padrão no código. O catálogo em `app/policies/catalog.py` só define a forma dos parâmetros. Uma regra nasce `draft`, vai a `in_review`, só fica `approved` com `POLICY_APPROVE`, referência de revisão e aprovador diferente do autor e de quem submeteu. Com um único RH, ninguém aprova: isso é proposital. Versão aprovada não é editada; a mudança é uma versão nova. Revogada continua consultável pelo id.

`GET /api/policies/resolve` e a ferramenta `get_applicable_policies` devolvem a versão aprovada vigente mais específica (equipe+categoria, equipe, categoria, empresa). Ausência, conflito, pin revogado ou hash adulterado não trazem parâmetros. A ferramenta, nesse caso, responde `POLICY_REVIEW_REQUIRED` sem resultado parcial. Empresa e equipe vêm do principal; outra empresa recebe 404 na API ou `FORBIDDEN_SCOPE` na ferramenta.

As fixtures em `backend/fixtures/policies/synthetic.json` são sintéticas (`source_kind=sintetico`, referência `SINTÉTICO — não é regra jurídica validada`). Não validam a EC 141/2026 nem qualquer teto legal. O carregamento passa pelo serviço (`app/policies/fixtures.py`), com dois usuários de RH.

## Fluxo do piloto (P1-02 a P1-07 e P2-03 a P2-06)

O fluxo principal ainda utiliza o solver de fluxo máximo determinístico em horas inteiras. Há também um **OR-Tools CP-SAT v4.2** em `app/optimization/cpsat_v42.py`, testado isoladamente e ainda **não conectado ao workflow**. Não apresente o solver do fluxo principal como CP-SAT. O forecast é mediana móvel: menos de oito períodos abstém, e nenhuma faixa é chamada de P10, P50 ou P90. O investigador em `app/investigation` só marca hipótese como sustentada quando há evidência; texto dentro dos dados não muda permissão.

Importação CSV em `POST /api/imports` e confirmação em `POST /api/imports/{id}/confirm`. Repetir o arquivo não cria outro snapshot. Colunas de salário, CPF, e-mail, nome ou motivo de afastamento rejeitam o arquivo, e a resposta não devolve o valor da célula. Unidade ausente ou incompatível fica no erro da linha; importação inválida não fica `complete`. `POST /api/imports/jira` lê só a fixture sintética. `POST /api/imports/jira/sync` não escreve no Jira. A leitura externa requer `JIRA_BASE_URL`, `JIRA_PROJECT_KEY` e `JIRA_API_TOKEN` e evita o campo pessoal `summary`; mesmo com essas variáveis, **a sincronização ainda responde 503**, porque não há mapeamento e persistência dos eventos. A validação contra um Jira real continua pendente.

`GET /api/teams/{team_id}/metrics?snapshot_id=` soma cada pool uma vez. O bloco homogêneo só aparece quando o arquivo trouxe headcount, jornada, disponibilidade, produtividade e demanda; o exemplo 954,3534 / 14 / 3 sai desses agregados, não de constante escondida.

`POST /api/investigations` responde 202. `POST /api/investigations/{id}/advance` retoma o checkpoint na mesma base: pergunta pendente pausa, resposta continua, reenvio não duplica cenário. Na branch v4.2 há cinco categorias estruturadas de cenário (`hire`, `temporary`, `reallocate`, `redesign`, `do_nothing`). As alternativas sem modelagem completa são inconclusivas. O código pode produzir **headcount exploratório**, mas o fluxo de decisão não considera uma contratação conclusiva enquanto forecast por skill/turno, contexto jurídico e validação independente v4.2 não estiverem conectados. O crítico bloqueia restrição dura e não transforma lacuna em fato. Timeout do solver não é inviabilidade.

`POST /api/scenarios/{id}/decisions` exige `decision:write`. Aprovar cenário inconclusivo, inviável, com crítica bloqueada, hash diferente, versão de cenário obsoleta ou regra que deixou de estar `approved` responde 409 e não grava a decisão. **O workflow ainda não produz `v42_validation` válida: todas as aprovações operacionais seguem deliberadamente bloqueadas.** Rejeitar ou adiar continua possível. `POST /api/scenarios/{id}/requisition-drafts` só depois de uma aprovação explícita, é idempotente e grava `executed=0`. Não há efeito em sistema externo. `GET /api/investigations/{id}/audit` exige `audit:read` na equipe da investigação. Outra empresa recebe 404. A lista traz os eventos da investigação, dos cenários, das decisões e dos rascunhos; não traz o texto da resposta nem o motivo livre.

O motor em `app/jobs` continua sendo um **LangGraph com nós simulados**, isolado e com tabelas próprias. Ele não é um agente LLM de produção e não está ligado à API de investigação. O fluxo acima usa as tabelas das migrações de domínio. Não há processo worker separado: a retomada operacional é o `advance` lendo o banco.

## Limitações do piloto

Aceite técnico não substitui revisão de RH, operação, jurídico ou privacidade. Valores de fixture não são regra vigente. Sem credencial, o Jira real não foi validado. O solver inteiro não cobre hora fracionária nem prova otimalidade de custo; cobre o máximo de horas sob os tetos e declara o status. O residual de horas é o backlog operacional usado na comparação; não é simulação de fila. Histórico curto abstém em vez de inventar intervalo. A interface em `/prototype/app/index.html` continua capaz de mostrar o protótipo ilustrativo; os números da API só substituem a tela depois de uma resposta persistida. Não há suíte de eval separada do pytest.

## Configuração de exemplo

`backend/.env.example` lista as variáveis e não contém segredo. O processo não lê esse arquivo: exporte as variáveis no ambiente. Sem `ALINIA_AUTH_SECRET` de pelo menos 32 caracteres, o login responde 503. `JIRA_BASE_URL`, `JIRA_PROJECT_KEY` e `JIRA_API_TOKEN` ficam vazios até existir uma integração autorizada; o sync continua indisponível.

No CMD:

```cmd
set ALINIA_AUTH_SECRET=<segredo local com 32 caracteres ou mais>
set DATABASE_URL=sqlite:///./alinia.db
```

## Roteiro de demonstração

1. Rode `upgrade head` e o servidor, como no início deste arquivo.
2. Crie duas empresas e, na primeira, dois usuários de RH. Um único RH não aprova regra. Crie também um RH na segunda empresa e um gestor da equipe `team-aurora`.
3. Importe um CSV para `team-aurora` e outro para `team-mar`. As colunas obrigatórias são `skill_id`, `shift_id`, `pool_id`, `eligible_hours`, `available_hours`, `period_start`, `period_end_exclusive`, `timezone`, `demand_cases`, `hours_unit`, `demand_unit`. Confirme cada importação.
4. A métrica de uma equipe com o snapshot da outra responde 404. A segunda empresa também recebe 404 ao ler a investigação da primeira.
5. Abra a investigação, avance, responda e compare as **cinco categorias A–E**. Com uma semana só, a previsão abstém. Mesmo com histórico longo e políticas sintéticas aprovadas, a contratação continua **não conclusiva** até existir previsão aplicada por competência/turno, validação jurídica e verificação independente. O catálogo em `backend/fixtures/policies/synthetic.json` é apenas exemplo e entra pelo serviço, não por insert direto.
6. Aprove só com o hash atual. Se a jornada usada no cenário for revogada antes, a aprovação responde 409. O rascunho só existe depois de uma aprovação e permanece com `executed` falso.

## Recuperação

`POST /api/investigations/{id}/advance` roda numa transação. Se o processo cai no meio, o banco fica no último advance confirmado. Suba de novo com o mesmo `DATABASE_URL` e chame o advance outra vez. Não há worker separado para reiniciar, e o mock em `app/jobs` não executa este fluxo.

## Checklist de liberação

- Segredo e URL do banco só no ambiente local, nunca no repositório.
- `alembic upgrade head` na base que vai ser demonstrada.
- `backend\.venv\Scripts\python -m pytest backend\tests -q` sem falha.
- Duas equipes na mesma empresa, com snapshots que não se misturam, e uma segunda empresa que recebe 404.
- Jira real continua pendente; o sync responde `INTEGRATION_UNAVAILABLE` mesmo com variáveis configuradas, pois não há persistência, e não escreve no Jira.
- O solver do fluxo principal não é OR-Tools; o CP-SAT v4.2 está isolado. As fixtures legais continuam marcadas como sintéticas.
- Decisão e rascunho permanecem com efeito administrativo desligado.
- Aceite de RH, operação, jurídico e privacidade continua pendente para qualquer dado real.


## Status do PRD v4.2 — revisão de 08/11/2026

A matriz de aceitação vigente é [REBASELINE_PRD_V42.md](../docs/REBASELINE_PRD_V42.md).
Este backend **não está pronto para operação empresarial** nem para uso de dados pessoais reais.

**Entregas verificáveis nesta branch:**
- `app/contracts/v42.py`: contrato agregado de entradas, concluídos, cancelamentos,
  reaberturas, backlog e demanda externa não registrada; limites de skill/intervalo,
  qualificação, lead time e relatos não verificados.
- `app/ingestion/csvparse.py`: colunas opcionais do ledger v4.2, reconciliação por
  período e deduplicação por competência entre turnos. Arquivos legados permanecem
  identificados como `legacy_unclassified`, não como demanda registrada.
- `GET /api/teams/{team_id}/demand-flow?snapshot_id=...`: histórico agregado
  autorizado por tenant/equipe, sem identificar trabalhadores.
- `app/forecast/engine.py`: abstenção para séries não semanais ou incomparáveis,
  avaliação temporal rolante e faixa empírica com janela separada de teste para
  histórico suficiente; faixas **não** são P10/P50/P90.
- `app/optimization/cpsat_v42.py`: otimizador CP-SAT de referência com orçamento
  conhecido, cobertura mínima rígida, SLA flexível, skill, turno, disponibilidade,
  treinamento validado, chegada de contratação, ramp-up e consumo de mentoria.
  A modelagem assume buckets explícitos e direitos já verificados por outro módulo.
  Não substitui um motor completo de escalas e **ainda não é chamado pelo workflow**.
- `app/optimization/validator_v42.py`: validadores determinísticos de intervalo,
  competência, prontidão e evidências de políticas, com testes de bloqueio.
- `app/planning/planner.py`: cinco famílias de cenário A–E na API; B, C e D são
  propostas exploratórias, não mudanças simuladas; contratação com prazo e custos
  desconhecidos **não é conclusiva**.
- `app/decisions/service.py`: aprovações exigem registro de validação
  independente v4.2 válido no cenário, além das verificações anteriores.
  O workflow ainda não produz este registro: **aprovações operacionais ficam
  bloqueadas de forma deliberada** até a integração dos dados e validadores.
- Workflow GitHub Actions `.github/workflows/p1-p2-integration.yml`: pytest,
  migrações e build do frontend.

**Limites que ainda impedem o aceite integral:**
- Jira real não importado/mapeado em produção, sem credenciais autorizadas.
- O agente investigador-planejador LLM e seu LangGraph produtivo não estão
  integrados; `jobs/graph.py` continua um mock isolado.
- O CP-SAT v4.2 não está ligado ao fluxo de cenários; faltam validação de repouso,
  cronograma completo por pessoa/turno, granularidade de skills e dados históricos.
- Falta gerar registros `v42_validation` a partir de dados reais validáveis.
- Falta aprovação técnica e jurídica dos parâmetros por categoria/contrato.
- Faltam plano de LGPD/RIPD, isolamento contextual, retenção e avaliações de viés.
- Não há experimento com os três braços e indicadores de valor de clientes reais.

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m alembic -c backend/alembic.ini upgrade head
```

Nenhum recurso novo executa contratação, alteração de escala, ponto ou salário.
A versão exige aceite de RH, Operações, jurídico e privacidade antes de operar.
