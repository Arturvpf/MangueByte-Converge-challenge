# Backend Alinia

Base COM-02 com Python 3.12, FastAPI, SQLAlchemy e Alembic. Execute os comandos na raiz do repositório. Em PowerShell:

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
