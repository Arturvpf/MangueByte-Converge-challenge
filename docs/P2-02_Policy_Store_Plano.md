# P2-02 — Policy Store: plano de implementação

Plano para executar a P2-02 com o Cursor. Responsável: Pessoa 2. Revisão: Pessoa 1.
Fontes: PRD v4.1 (seções 5, 11, 12, 13 e 14), `docs/Divisao_IA_Backend_Alinia.md` (P2-02, seções 7 e 8) e o código da branch `p2/identidade-permissoes-auditoria`.

---

## 0. Como usar este plano no Cursor

1. Crie a branch (seção 2) e abra a pasta do repositório no Cursor.
2. No chat do Cursor (modo Agent), cole o prompt abaixo e anexe este arquivo com `@docs/P2-02_Policy_Store_Plano.md`.
3. Execute **uma etapa por vez** (seção 5). Ao fim de cada etapa, rode os testes, revise o diff e faça o commit você mesmo.

Prompt inicial sugerido:

```text
Você vai implementar a tarefa P2-02 (Policy Store) seguindo @docs/P2-02_Policy_Store_Plano.md.
Leia o plano inteiro e os arquivos citados na seção 3 antes de escrever código.
Faça somente a Etapa 1 agora. Ao terminar, rode
backend\.venv\Scripts\python -m pytest backend\tests -q
e me mostre o resultado e um resumo das mudanças. Não faça commit nem push.
Siga as regras da seção 8 do plano.
```

Para as etapas seguintes: `Agora faça a Etapa N do plano. Mesmas regras.`

---

## 1. Objetivo

Criar o **repositório de regras trabalhistas versionadas** que o planejador (P2-03), o solver (P2-04), o crítico (P2-05) e a decisão do RH (P2-06) vão consultar. Cada regra tem escopo, fonte, categoria, vigência, versão e responsável, e passa pelos estados rascunho → revisão → aprovado → revogado.

O PRD exige (seção 11): "os limites não são codificados em prompts. Cada regra tem responsável, fonte, validade, testes e aprovação jurídica antes de ativação."

**Aceite do plano do projeto (P2-02):**
- Regra ausente ou em conflito retorna `POLICY_REVIEW_REQUIRED`.
- Versões antigas são preservadas.
- A ativação exige aprovação autorizada.
- O conteúdo jurídico depende de validação de domínio. Nenhum valor jurídico é ativado automaticamente a partir do PRD.
- Limites não ficam fixados em prompts nem em código.

**Entregável:** tabelas e migração, API, ferramenta tipada de consulta de regras e testes.

---

## 2. Pré-requisitos e branch

A P2-02 depende da P2-01. Enquanto o PR da P2-01 não for aceito, crie a branch a partir dela:

```bash
git switch p2/identidade-permissoes-auditoria
```
```bash
git pull
```
```bash
git switch -c p2/policy-store
```
```bash
backend\.venv\Scripts\python -m pytest backend\tests -q
```

O último comando deve mostrar 96 passed antes de começar. Quando a P2-01 for aceita na `p1/dados-investigacao`, faça `git rebase p1/dados-investigacao` nesta branch e abra o PR da P2-02 contra a mesma base.

---

## 3. O que já existe e deve ser reutilizado

| Componente | Onde | Como usar |
|---|---|---|
| Permissões | `backend/app/auth/permissions.py` | `Permission.POLICY_READ` (gestor, RH, admin), `POLICY_WRITE` e `POLICY_APPROVE` (RH). `principal.can(p, team_id)`, `principal.tenant_wide(p)`, `principal.team_ids(p)` |
| Dependências de rota | `backend/app/auth/dependencies.py` | `require_permission(p)`, `require_team_permission(p)` (lê só o path param `team_id`), `require_tenant_permission(p)` e `deny(request, principal, permission, target_team=None)`, que devolve 403 auditado |
| Autorização de ferramenta | `backend/app/auth/tools.py` | `authorize_tool(principal, p, tenant_id=..., team_id=...)` lança `ToolForbidden` |
| Auditoria | `backend/app/audit/log.py` | `record_event(session, action=..., outcome=..., tenant_id=..., actor_user_id=..., team_id=..., resource_type=..., resource_id=..., details=...)`: adiciona na sessão, e quem chama faz o commit na mesma transação |
| Contratos | `backend/app/contracts/v1.py` | `Scope`, `ToolRequest` (já tem `policy_version_ids`), `ToolResponse[T]` (já tem `rule_versions`), `ContractError`, `ErrorCode.POLICY_REVIEW_REQUIRED` e `FORBIDDEN_SCOPE`. Regras em `backend/CONTRATOS.md` |
| Registro de rotas | `backend/app/core/modules.py` | Adicionar `DomainModule(routers=(policies_router,))` em `DOMAIN_MODULES` |
| Migrações | `backend/migrations/` | Nova revisão `0005` com `down_revision = '0004'` (a `0004` é a correção de auditoria da P2-01). Importar os models em `migrations/env.py` |
| Padrão de teste | `backend/tests/test_p2_integration.py` | Banco migrado com Alembic, usuários pela CLI (`create_tenant`, `create_user`), login real via `/api/auth/login` |

Leia também `backend/README.md` (seção P2-01) e `backend/CONTRATOS.md`.

---

## 4. Decisões de desenho

### 4.1 Modelo de dados

**`policies`**: a regra como identidade estável.

| Coluna | Tipo | Observação |
|---|---|---|
| `policy_id` | str(36) PK | uuid4 |
| `tenant_id` | str(128) | índice |
| `rule_key` | str(64) | chave do catálogo (4.4), ex.: `workweek.max_hours` |
| `category` | str(32) | derivada do catálogo, nunca livre |
| `team_id` | str(128) nullable | `NULL` = empresa inteira |
| `employee_category` | str(64) nullable | ex.: `clt_geral`; `NULL` = todas |
| `title` | str(200) | |
| `created_by`, `created_at` | | |

Unique: `(tenant_id, rule_key, team_id, employee_category)`. Lembre que `NULL` não conflita em UNIQUE, então valide também no código.

**`policy_versions`**: cada versão é imutável depois de sair do rascunho.

| Coluna | Tipo | Observação |
|---|---|---|
| `version_id` | str(36) PK | uuid4. É este ID que vai em `policy_version_ids` e `rule_versions` |
| `policy_id` | FK | |
| `tenant_id` | str(128) | redundante de propósito, para filtrar por empresa |
| `version` | int > 0 | sequencial por policy; unique `(policy_id, version)` |
| `status` | str(16) | `draft`, `in_review`, `approved`, `revoked` (CHECK no banco) |
| `parameters` | JSON | validado pelo schema da `rule_key` (4.4) |
| `source_kind` | str(16) | `lei`, `emenda`, `cct`, `act`, `politica_interna`, `sintetico` |
| `source_reference` | str(500) | texto ou URL da fonte |
| `valid_from` | date | inclusivo |
| `valid_until` | date nullable | exclusivo; CHECK `valid_until > valid_from` |
| `content_hash` | str(64) | sha256 do conteúdo canônico (parâmetros, fonte e vigência) |
| `revision` | int | controle de concorrência otimista; incrementa a cada mudança |
| `author_user_id`, `created_at` | | |
| `submitted_by`, `submitted_at` | nullable | |
| `approved_by`, `approved_at`, `legal_review_reference` | nullable | `legal_review_reference` é obrigatório para aprovar |
| `review_note` | str(1000) nullable | motivo da rejeição |
| `revoked_by`, `revoked_at`, `revocation_reason` | nullable | |
| `idempotency_key` | str(128) nullable | unique `(policy_id, idempotency_key)` |

### 4.2 Ciclo de vida

```
draft ──submit──▶ in_review ──approve──▶ approved ──revoke──▶ revoked
  ▲                   │
  └──────reject───────┘ (com review_note)
```

- **Só `draft` pode ser editado.** Depois disso, conteúdo, fonte e vigência são imutáveis. Para mudar uma regra aprovada, crie uma **nova versão**.
- **Nada é apagado.** Não existe DELETE de policy nem de versão.
- **Quatro olhos:** quem aprova precisa ter `POLICY_APPROVE` no escopo da regra e **não pode ser o autor nem quem submeteu**. Com um único RH, ninguém aprova, e isso é intencional (documentar).
- **Aprovar exige** `legal_review_reference` não vazio, que referencia o parecer jurídico ou de RH (PRD seção 11).
- **Revogar exige** `revocation_reason`. Versão revogada continua consultável por ID, para reproduzir análises antigas.
- **Concorrência:** toda transição e edição recebe `expected_revision`. Se não bater, responde 409 `STALE_REVISION` e nada muda.
- **Guarda no ORM:** um listener `before_flush` impede alterar conteúdo de versão fora de `draft` e impede DELETE, no mesmo estilo de `backend/app/audit/models.py`.

### 4.3 Resolução de regras ("qual regra vale?")

Função `resolve(session, *, tenant_id, team_id, employee_category, on_date, rule_keys) -> PolicyResolution`:

1. Para cada `rule_key`, considere só as versões `approved` em que `valid_from <= on_date < valid_until` (ou `valid_until` nulo) e cujo escopo combina: `team_id` igual ou nulo, `employee_category` igual ou nula.
2. **Especificidade:** equipe + categoria > equipe > categoria > empresa inteira. Fica a versão do nível mais específico que tiver candidatas.
3. **Conflito:** duas ou mais versões aprovadas no mesmo nível de especificidade (sobreposição de vigência) → `review_required`, motivo `conflict`.
4. **Ausência:** nenhuma candidata → `review_required`, motivo `missing`. **Nunca use valor padrão.** Rascunho ou revisão não contam.
5. **Versões fixadas** (`policy_version_ids` do `ToolRequest`): `resolve_pinned(session, tenant_id, version_ids)` devolve exatamente essas versões, conferindo empresa, `content_hash` e escopo. Fixada revogada → `review_required`, motivo `pinned_revoked`. ID desconhecido ou de outra empresa → `pinned_not_found`, que **não revela** se existe em outra empresa.

O resultado deve ser determinístico: mesma entrada e mesmo banco, mesma saída e mesma ordem.

### 4.4 Catálogo de regras (`rule_key`)

Arquivo `backend/app/policies/catalog.py`: um dicionário `rule_key → (categoria, schema Pydantic dos parâmetros)`. Os schemas usam `Contract` (strict, `extra='forbid'`) e **não têm valores padrão para limites**. MVP com 5 chaves:

| `rule_key` | Categoria | Parâmetros |
|---|---|---|
| `workweek.max_hours` | `jornada` | `max_hours: Decimal` (> 0) |
| `workday.max_hours` | `jornada` | `max_hours: Decimal` (> 0), `requires_collective_agreement: bool` |
| `rest.weekly_min_days` | `repouso` | `min_days: int` (1..7) |
| `contract.modality` | `modalidade_contratual` | `modality: Literal['indeterminado','temporario','determinado','intermitente','estagio','aprendiz']`, `allowed: bool`, `max_duration_days: int \| None`, `requires_legal_review: bool` |
| `internship.counts_as_capacity` | `estagio_aprendizagem` | `allowed: bool` |

Chave desconhecida ou parâmetros inválidos → 422. O catálogo é extensível, mas **os valores só existem no banco, em versões aprovadas**.

### 4.5 Permissões

| Ação | Permissão | Escopo |
|---|---|---|
| Listar e ler regras e versões | `POLICY_READ` | regras da empresa inteira + regras das equipes em `team_ids(POLICY_READ)` (todas, se `tenant_wide`) |
| Criar regra, criar e editar rascunho, submeter | `POLICY_WRITE` | regra de equipe: `can(POLICY_WRITE, team_id)`; regra da empresa inteira: `tenant_wide(POLICY_WRITE)` |
| Aprovar, rejeitar, revogar | `POLICY_APPROVE` | mesmo critério de escopo |
| Resolver (API e ferramenta) | `POLICY_READ` | `can(POLICY_READ, team_id)` |

A empresa (`tenant_id`) vem **sempre** do principal. Os corpos de requisição usam `extra='forbid'` e não têm campo `tenant_id`. Regra de outra empresa → 404, sem revelar que existe. Negativas usam `deny(...)` para ficarem auditadas.

### 4.6 Auditoria

Cada mudança grava `record_event` **na mesma transação**, com `resource_type='policy_version'` ou `'policy'` e `resource_id` = ID. Ações: `policy.create`, `policy.version.create`, `policy.version.update`, `policy.version.submit`, `policy.version.reject`, `policy.version.approve`, `policy.version.revoke`, `policy.resolve`. Em `details` vão só chaves curtas (`rule_key`, `version`, `from_status`, `to_status`, `outcome_reason`). **Notas, motivos e referências jurídicas ficam na tabela, não na auditoria** (texto livre pode ter dado pessoal).

### 4.7 Idempotência

- `POST` de criação aceita o header `Idempotency-Key`. Mesma chave com o mesmo conteúdo devolve o recurso original (200). Mesma chave com conteúdo diferente devolve 409. Nenhum reenvio cria uma segunda linha nem um segundo evento de auditoria.
- Transições são protegidas por `expected_revision`, então reenviar a mesma transição não duplica efeito.

---

## 5. Etapas (uma por vez no Cursor)

### Etapa 1 — Catálogo e schemas
- **Arquivos:** `backend/app/policies/__init__.py`, `catalog.py`, `schemas.py`.
- **Fazer:** o catálogo da 4.4; schemas de entrada e saída da API (corpos com `extra='forbid'`); `PolicyResolution(Scope)` com `data_snapshot_id`, `on_date`, `items: list[ResolvedRule]` e `complete: bool`, em que `ResolvedRule` tem `rule_key`, `status` (`resolved` ou `review_required`), `version_id`, `version`, `parameters`, `source_reference`, `valid_from`, `valid_until` e `reason`.
- **Testes** (`backend/tests/test_policies_catalog.py`): chave desconhecida; parâmetros fora de faixa; campo extra; ausência de valor padrão.
- **Commit sugerido:** `Add policy rule catalog and schemas (P2-02)`

### Etapa 2 — Modelos e migração
- **Arquivos:** `backend/app/policies/models.py`, `backend/migrations/versions/0005_policy_store.py`, `backend/migrations/env.py` (import).
- **Fazer:** as tabelas da 4.1 com CHECKs (status, vigência, `version > 0`), uniques e índices (`tenant_id`, `rule_key`, `team_id`); o guarda de imutabilidade no ORM (4.2); downgrade completo.
- **Testes:** `upgrade head` em banco vazio; downgrade para `0004`; CHECK rejeita status inválido e vigência invertida; o ORM bloqueia editar versão aprovada e deletar versão.
- **Commit sugerido:** `Add policy store tables and migration (P2-02)`

### Etapa 3 — Serviço de ciclo de vida
- **Arquivo:** `backend/app/policies/service.py`, que recebe `session` e `principal`, sem FastAPI.
- **Fazer:** criar regra com primeiro rascunho; nova versão (opcionalmente copiando outra); editar rascunho; submit, reject, approve e revoke com as regras da 4.2, as permissões da 4.5, a auditoria da 4.6 e a idempotência da 4.7; `content_hash` canônico (JSON com `sort_keys`; `Decimal` como string).
- **Testes** (`backend/tests/test_policies_service.py`): cada transição válida e inválida; quatro olhos (o autor não aprova); aprovar sem `legal_review_reference`; `expected_revision` velho dá 409 sem efeito; nova versão preserva a antiga intacta; gestor não escreve; RH de equipe não aprova regra da empresa inteira; um evento de auditoria por mudança e nenhum em falha.
- **Commit sugerido:** `Add policy lifecycle with four-eyes approval (P2-02)`

### Etapa 4 — Resolução
- **Arquivo:** `backend/app/policies/resolver.py`.
- **Fazer:** `resolve` e `resolve_pinned` (4.3).
- **Testes** (`backend/tests/test_policies_resolver.py`): ausência dá `missing`; só rascunho dá `missing`; duas aprovadas sobrepostas dão `conflict`; regra de equipe vence a da empresa; categoria; borda da vigência (`valid_until` exclusivo); data antes de `valid_from`; revogada não resolve; fixada revogada dá `pinned_revoked`; fixada de outra empresa dá `pinned_not_found`; `content_hash` adulterado direto no banco é detectado; resultado determinístico.
- **Commit sugerido:** `Add deterministic policy resolution (P2-02)`

### Etapa 5 — API
- **Arquivo:** `backend/app/policies/api.py` (`router`, prefixo `/api/policies`, tag `policies`) e registro em `backend/app/core/modules.py`.

| Método e rota | Descrição |
|---|---|
| `GET /api/policies` | lista as regras visíveis, com filtros `rule_key`, `category`, `team_id` e `status` |
| `POST /api/policies` | cria regra + rascunho v1 (`Idempotency-Key`) |
| `GET /api/policies/{policy_id}` | regra com todas as versões |
| `POST /api/policies/{policy_id}/versions` | novo rascunho (`Idempotency-Key`, `copy_from_version_id` opcional) |
| `GET /api/policies/{policy_id}/versions/{version_id}` | uma versão |
| `PATCH /api/policies/{policy_id}/versions/{version_id}` | edita rascunho (`expected_revision`) |
| `POST .../versions/{version_id}/submit` | `expected_revision` |
| `POST .../versions/{version_id}/reject` | `expected_revision`, `review_note` |
| `POST .../versions/{version_id}/approve` | `expected_revision`, `legal_review_reference` |
| `POST .../versions/{version_id}/revoke` | `expected_revision`, `revocation_reason` |
| `GET /api/policies/resolve` | `on_date`, `team_id`, `employee_category`, `rule_keys` (lista) → `PolicyResolution` completo para leitura humana |

- **Erros:** 401 sem login; 403 `FORBIDDEN_SCOPE` (via `deny`); 404 para outra empresa; 409 `STALE_REVISION` ou `INVALID_TRANSITION`; 422 em validação.
- **Testes** (`backend/tests/test_policies_api.py`, com login real como em `test_p2_integration.py`): fluxo completo rascunho → revisão → aprovado → resolve → revoga → resolve dá `review_required`; isolamento entre empresas; gestor só lê; `tenant_id` no corpo dá 422; reenvio com a mesma `Idempotency-Key` não duplica; trace correlacionado na auditoria.
- **Commit sugerido:** `Expose policy store API (P2-02)`

### Etapa 6 — Ferramenta tipada para os agentes
- **Arquivo:** `backend/app/policies/tools.py`.
- **Fazer:** `get_applicable_policies(session, principal, request: ToolRequest, *, on_date, employee_category, rule_keys) -> ToolResponse[PolicyResolution]`.
  - Autorize com `authorize_tool(principal, POLICY_READ, tenant_id=request.tenant_id, team_id=request.team_id)`. A empresa e a equipe do envelope são **conferidas** contra o principal, nunca confiadas sozinhas.
  - Se `request.policy_version_ids` vier preenchido, use `resolve_pinned`; senão, `resolve`.
  - Tudo resolvido: `status='ok'`, `rule_versions` = IDs das versões usadas, `data_version = request.data_snapshot_id`.
  - Alguma chave sem resolução: `status='error'` com `ContractError(code=POLICY_REVIEW_REQUIRED, retryable=False, details=[...])`, listando só `rule_key` e motivo. **Não devolva resultado parcial**: o planejador não deve planejar com metade das regras.
  - Permissão negada vira `FORBIDDEN_SCOPE` (não 500).
  - Grava `policy.resolve` na auditoria com `trace_id` do contexto.
- **Testes** (`backend/tests/test_policies_tools.py`): ok com tipo validado pelo `ToolResponse`; erro de revisão; envelope de outra empresa dá `FORBIDDEN_SCOPE`; versões fixadas reproduzem resultado antigo mesmo depois de nova versão aprovada; texto malicioso em `source_reference` não muda nada na resposta.
- **Commit sugerido:** `Add typed policy tool for agents (P2-02)`

### Etapa 7 — Fixtures sintéticas e documentação
- **Arquivos:** `backend/fixtures/policies/synthetic.json`, seção nova em `backend/README.md`, `backend/CONTRATOS.md` (contrato `PolicyResolution`).
- **Fazer:** fixtures para as duas empresas sintéticas (`tenant-demo-a`, `tenant-demo-b`) com `source_kind='sintetico'` e referência `"SINTÉTICO — não é regra jurídica validada"`. Pode haver um exemplo de transição de jornada inspirado na EC 141/2026 (PRD seção 11), **só como dado sintético de teste**. Um script de teste carrega as fixtures pelo serviço, nunca direto no banco. No README: ciclo de vida, quatro olhos, como resolver, como os agentes usam a ferramenta e as limitações.
- **Testes:** carregar as fixtures e resolver as 5 chaves das duas empresas; suíte inteira verde.
- **Commit sugerido:** `Add synthetic policy fixtures and docs (P2-02)`

---

## 6. Checklist de aceite (revisar antes do PR)

- [ ] Regra ausente, só em rascunho ou em conflito → `POLICY_REVIEW_REQUIRED` (API e ferramenta).
- [ ] Nenhum limite jurídico fixo em código, prompt ou valor padrão de schema.
- [ ] Versões antigas preservadas; aprovada nunca editada nem apagada (ORM e testes).
- [ ] Aprovação exige `POLICY_APPROVE`, `legal_review_reference` e aprovador diferente do autor e de quem submeteu.
- [ ] Versões fixadas reproduzem análises antigas; revogada fixada é sinalizada.
- [ ] Empresa sempre vem do principal; outra empresa recebe 404 ou `FORBIDDEN_SCOPE`.
- [ ] Toda mudança auditada na mesma transação, sem texto livre em `details`.
- [ ] Reenvio (`Idempotency-Key`, `expected_revision`) não duplica registro nem evento.
- [ ] Migração `0005` sobe e desce em SQLite; testada em PostgreSQL se disponível.
- [ ] Fixtures marcadas como sintéticas; README e CONTRATOS atualizados.
- [ ] `backend\.venv\Scripts\python -m pytest backend\tests -q` todo verde.

---

## 7. Fora do escopo da P2-02

- Validar o conteúdo jurídico das regras: é uma dependência externa (RH e jurídico).
- Consumir as regras no planejador e no solver: P2-03 e P2-04.
- Tela de regras na interface.
- Importação automática de CCT/ACT.
- Notificar responsáveis por vencimento de vigência.

---

## 8. Regras para o Cursor

1. **Não faça commit nem push**, e não adicione linhas `Co-authored-by`. Os commits são feitos pela Pessoa 2.
2. **Não edite arquivos da Pessoa 1** (`backend/app/data`, `jobs`, `metrics`, `contracts/v1.py` e seus testes). Se precisar mudar um contrato compartilhado, pare e explique o motivo.
3. **Não edite** `backend/app/auth` nem `backend/app/audit`, exceto se um bug real for encontrado. Nesse caso, pare e explique antes.
4. **Sem novas dependências.** Use só o que está em `backend/requirements.lock.txt`.
5. **Não use valores jurídicos reais como verdade.** Valores em teste e fixture são sintéticos e marcados como tal.
6. Siga o estilo do código existente: compacto, type hints, Pydantic strict, SQLAlchemy 2.0.
7. Toda mudança vem com teste negativo. Rode a suíte inteira ao fim de cada etapa e mostre o resultado.
8. Use caminhos de Windows nos comandos (`backend\.venv\Scripts\python`).
