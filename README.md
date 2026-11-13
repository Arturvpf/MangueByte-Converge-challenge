# Alinia — Workforce Intelligence

A Alinia ajuda equipes de serviços a investigar aumentos de demanda, localizar gargalos por competência e turno e comparar intervenções antes de uma decisão de RH. O painel conecta histórico operacional, previsão semanal, otimização de capacidade e simulação de filas. Cada investigação registra os dados e as premissas usados no cálculo.

[Executar localmente](#executar-localmente) · [Percorrer a demonstração](#percorrer-a-demonstração) · [Consultar a API](#api-e-integrações) · [Executar os testes](#testes-e-build)

## Executar localmente

O painel de planejamento usa **Git, Python 3.12 e SQLite**. A demonstração funciona sem Jira, Node.js ou credenciais de IA. Use **Node.js 22.13+ e npm** para o chat opcional e o build do frontend.

### 1. Obter o código

```bash
git clone https://github.com/Arturvpf/MangueByte-Converge-challenge.git
cd MangueByte-Converge-challenge
```

Para reproduzir a versão do [PR #7](https://github.com/Arturvpf/MangueByte-Converge-challenge/pull/7) enquanto a entrega está em revisão, rode também os comandos abaixo. Eles criam um checkout local a partir do PR.

```bash
git fetch origin refs/pull/7/head
git switch -c demo-pr-7 FETCH_HEAD
```

Em um checkout que já tem `demo-pr-7`, use `git switch demo-pr-7` para voltar a ele. Execute os comandos seguintes na raiz do repositório.

### 2. Instalar dependências e configurar o ambiente

**Windows · PowerShell**

```powershell
py -3.12 -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.lock.txt
$env:DATABASE_URL = "sqlite:///./alinia.db"
$env:ALINIA_AUTH_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Linux e macOS**

```bash
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.lock.txt
export DATABASE_URL="sqlite:///./alinia.db"
export ALINIA_AUTH_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

Mantenha as variáveis no terminal que inicia a API. Reutilize a chave de autenticação se quiser preservar a validade dos tokens após reiniciar. O [exemplo de ambiente do backend](backend/.env.example) serve como referência. Exporte as variáveis no ambiente do processo e mantenha os valores de segredos fora do Git.

### 3. Migrar o banco e criar a conta de demonstração

```bash
python -m alembic -c backend/alembic.ini upgrade head
python -m backend.app.auth.cli create-tenant --tenant-id demo --name "Empresa Demo"
python -m backend.app.auth.cli create-user --tenant-id demo --email rh@demo.example --role rh
```

Os dois comandos de criação são executados uma vez por banco. Escolha uma senha quando o terminal solicitar. Ao atualizar um banco já existente, rode a migração e use a conta cadastrada. A conta com perfil `rh` permite investigar, recalcular e registrar decisões de demonstração.

### 4. Subir a aplicação

```bash
python -m uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8000
```

| Endereço | O que abre |
| --- | --- |
| [Painel](http://127.0.0.1:8000/prototype/app/) | Visão geral, investigação, previsão, cenários e revisão do RH |
| [Página inicial](http://127.0.0.1:8000/prototype/) | Apresentação do projeto |
| [OpenAPI e Swagger](http://127.0.0.1:8000/docs) | Esquemas e rotas da API |
| [Saúde do servidor](http://127.0.0.1:8000/health) | Resposta esperada `{"status":"ok"}` |

Se a porta 8000 estiver ocupada, escolha outra no comando e use a mesma porta nos links locais. Use `Ctrl+C` no terminal do Uvicorn para encerrar.

## Percorrer a demonstração

1. No painel, clique em **Conectar dados**. Entre com a empresa `demo`, o e-mail `rh@demo.example` e a senha escolhida no terminal.
2. Abra **Carregar dados sintéticos**, mantenha **Pico sazonal e retomada** e clique em **Carregar demonstração**. A carga cria um recorte com origem sintética. Em uma empresa vazia, a equipe de demonstração será `team-demo`.
3. Clique em **Abrir investigação**. O backend calcula a previsão e os cinco cenários. Para ver o histórico e o backlog na **Visão geral**, use **Conectar dados → Carregar métricas** no mesmo recorte.
4. Em **Previsão**, compare P10, P50 e P90 da equipe e use o seletor para abrir uma competência ou turno. Em **Cenários**, veja custo, prazo, SLA simulado, backlog e o comparativo semanal. Selecione uma alternativa para ver horas disponíveis e o déficit por competência e turno.
5. Em **Revisão do RH**, experimente **Replanejar com evidências revisadas** e informe um teto hipotético de contratação. Para acompanhar a operação de referência, selecione E, registre **Adiar** com uma justificativa e abra **Resultados observados**.

O perfil padrão reúne **88 semanas, três competências, dois turnos e cinco pools**. A demanda sobe durante duas semanas e depois recua. Os valores abaixo são reproduzidos no horizonte original, com as premissas do recorte padrão.

| Semana de 2026 | P50 da equipe (casos) | A · Permanente | B · Temporária | C · Realocação | D · Redesenho | E · Referência |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 09/11 | 339 | 0 h | 0 h | 0 h | 0 h | 0 h |
| 16/11 | 428 | 25 h | 0 h | 21 h | 19 h | 21 h |
| 23/11 | 479 | 4 h | 0 h | 47 h | 43 h | 47 h |
| 30/11 | 361 | 0 h | 0 h | 0 h | 0 h | 0 h |
| **Déficit no horizonte** | — | **29 h** | **0 h** | **68 h** | **62 h** | **68 h** |

As colunas A–E mostram horas de demanda descobertas. Nesse recorte, o contrato temporário cobre as duas semanas de pico e termina antes da retomada. Em E, o déficit semanal volta a zero na última semana e ainda restam cerca de 128 casos equivalentes de backlog. Custos e indicadores são hipóteses da simulação.

### Outros perfis e exportação

| Perfil | O que demonstra |
| --- | --- |
| `pico-e-retomada` | Concentração temporária de demanda e queda depois do pico |
| `gargalo` | Déficit em suporte especializado e atendimento noturno |
| `pico` | Aumento da carga noturna em parte do ciclo |
| `estrutural` | Pressão persistente sobre a competência especializada |
| `turnos` | Demanda de atendimento deslocada para o turno da noite |

Gere o mesmo histórico em CSV com a semente fixa do gerador.

```bash
python -m backend.app.ingestion.demo --profile pico-e-retomada --output alinia-demo.csv
```

O carregador da demonstração e o gerador usam os mesmos dados. O endpoint dedicado registra a origem como `synthetic`. O upload genérico registra a origem como `csv`.

## Como o planejamento funciona

```mermaid
flowchart LR
    S["CSV, Jira somente leitura ou dados sintéticos"] --> I["Recorte versionado e investigação"]
    I --> F["Forecast por competência e turno"]
    F --> O["CP-SAT · cenários A–E"]
    O --> Q["SimPy quando há parâmetros de fila"]
    O --> V["Verificação matemática"]
    Q --> R["Revisão do RH"]
    V --> R
    R --> M["Acompanhamento de resultados"]
    R -->|"Novas evidências"| I
```

- **Demanda e capacidade.** O histórico distingue entradas, conclusões, cancelamentos, reaberturas, demanda fora do registro e backlog. O solver compartilha as horas dos pools elegíveis entre competências e turnos.
- **Previsão.** O horizonte da demonstração é de quatro semanas. O forecast compara baselines, publica métricas de backtest e disponibiliza percentis quando o histórico e a avaliação sustentam a calibração.
- **Alternativas.** A contratação permanente considera recrutamento, admissão e aumento gradual de produtividade. A temporária tem prazo de início e término. Realocação e redesenho usam horas dos pools existentes e incluem transição. E mantém a capacidade de referência.
- **Filas.** Com produtividade, variabilidade, SLA e backlog inicial disponíveis, SimPy estima distribuição de SLA e backlog em 12 execuções com sementes reproduzíveis.
- **Revisão.** O RH pode usar um recorte confirmado ou ajustar premissas, registrar justificativa e gerar uma nova versão dos cenários. Resultados observados são vinculados à decisão e à versão correspondente.

A API FastAPI coordena as etapas quantitativas. O Investigador dispõe de uma ferramenta tipada de leitura dos resultados. A seleção autônoma das etapas pelo LLM segue como objetivo do produto.

### Limites operacionais

A verificação matemática do solver é independente da autorização operacional. A aprovação exige comprovação de jornada, repouso, categoria, contrato, modalidade, instrumento vigente e orçamento. A demonstração usa cenários exploratórios e mantém a aprovação bloqueada. Relatos do gestor são registrados como evidências não verificadas e ficam fora dos cálculos até que haja uma fonte confirmada.

Os dados são isolados por empresa e equipe. O resumo voltado ao Investigador usa totais e campos controlados, com supressão de séries operacionais de baixo volume. O fluxo registra decisões humanas e pode preparar rascunhos internos quando elegíveis. A execução administrativa fica sob responsabilidade da organização.

## API e integrações

O [OpenAPI](http://127.0.0.1:8000/docs) mostra os formatos de cada rota. Em chamadas protegidas, envie `Authorization: Bearer <access_token>` com o token devolvido pelo login. Para reproduzir a demonstração por API, execute a sequência abaixo na mesma conta.

| Ordem | Método e rota | Entrada ou resultado |
| --- | --- | --- |
| 1 | `POST /api/auth/login` | Envie `tenant_id`, `email` e `password`. Guarde `access_token` para as próximas chamadas. |
| 2 | `POST /api/imports/synthetic` | Envie `{"team_id":"team-demo","profile":"pico-e-retomada"}`. Guarde `snapshot_id`. |
| 3 | `POST /api/investigations` | Envie `team_id`, `snapshot_id`, `idempotency_key` e `cycle_limit`. Guarde `run_id`. |
| 4 | `POST /api/investigations/{run_id}/advance` | Avança a investigação. Para o perfil padrão, o estado esperado é `AWAITING_HUMAN`. |
| 5 | `GET /api/investigations/{run_id}/forecast` e `GET /api/investigations/{run_id}/scenarios` | Retornam previsão e os cinco cenários da versão atual. |

Para deslocar a janela da previsão, acrescente de 1 a 8 semanas ao histórico com `extra_weeks` no carregamento. Se a investigação retornar `WAITING_INPUT`, consulte as perguntas do relatório, registre os relatos em `POST /api/investigations/{run_id}/answers` e avance novamente. Para dados próprios, envie o conteúdo CSV como texto com `team_id` e `filename` em `POST /api/imports`, confira o status e confirme em `POST /api/imports/{import_id}/confirm`. Consulte [os contratos e campos do CSV](backend/CONTRATOS.md).

A coleta Jira Cloud trabalha em modo somente leitura e grava contagens semanais com checkpoint. A configuração real exige credenciais limitadas ao projeto, mapeamento de competências e um recorte de capacidade autorizado. A integração foi exercitada com transporte simulado. Consulte [a configuração do Jira, do worker, do replanejamento e do Investigador](docs/PLANEJAMENTO_QUANTITATIVO.md).

## Chat opcional com DeepSeek

O chat de apresentação usa o caso fictício **Unidade Centro**, com histórico mensal próprio. O painel de planejamento na porta 8000 usa o FastAPI e a investigação autenticada. Para abrir o chat de apresentação com o proxy do agente, use Node.js e execute os comandos a partir da raiz.

**Terminal do agente**

```bash
npm --prefix alinia-investigator ci
npm --prefix alinia-investigator run index
npm run agent
```

Configure `FEATHERLESS_API_KEY` no ambiente desse terminal antes de iniciar o agente para obter respostas do modelo. A demonstração oferece uma resposta local quando o modelo está indisponível. A variável `FEATHERLESS_MODEL` é opcional. Consulte [o exemplo de ambiente do agente](alinia-investigator/.env.example).

**Terminal do frontend estático**

```bash
npm run dev
```

Abra [a conversa de apresentação](http://127.0.0.1:5173/app/#agente). O servidor Node na porta 5173 repassa `/agent/*` ao agente na porta 3141. Para usar as rotas `/api/*` e os snapshots autenticados, acesse o painel servido pelo FastAPI na porta 8000.

## Testes e build

**Backend e migrações**

```bash
python -m pip check
python -m pytest backend/tests -q
python -m alembic -c backend/alembic.ini upgrade head
```

Para rodar a migração em PostgreSQL, aponte `DATABASE_URL` para um banco disponível usando o formato `postgresql+psycopg://usuario:senha@host:5432/banco`.

**Frontend e Investigador**

```bash
node --check src/app/app.js
node --check src/app/agent.js
npm run build
npm --prefix alinia-investigator ci
npm --prefix alinia-investigator run check
npm --prefix alinia-investigator test
```

O build copia `src/` para `dist/`. O [CI do repositório](.github/workflows/p1-p2-integration.yml) roda a suíte Python, migrações SQLite e PostgreSQL, sintaxe do painel e build estático. A verificação TypeScript e os testes do Investigador são executados pelos comandos acima.

## Evolução do produto

O foco inicial são operações com solicitações recorrentes, como suporte técnico, serviços compartilhados, backoffice e BPO. A meta é que o agente formule hipóteses, escolha ferramentas autorizadas, peça esclarecimentos e explique o que mudou entre cenários. Os motores de cálculo e os validadores mantêm a responsabilidade por previsão, custos, cobertura e restrições.

A avaliação proposta compara o processo atual da equipe, o planejamento determinístico e o planejamento assistido pelo agente sobre os mesmos dados. Os principais indicadores são tempo até a decisão, retrabalho, erro de previsão, backlog, SLA, custo e cobertura por turno. A validação em uma operação real depende de evidências e regras aplicáveis à empresa.

## Organização do repositório

| Caminho | Conteúdo |
| --- | --- |
| [`src/`](src/) e [`dist/`](dist/) | Fontes do painel e arquivos estáticos gerados |
| [`backend/app/`](backend/app/) | FastAPI, ingestão, forecast, CP-SAT, SimPy, políticas e workflow |
| [`backend/migrations/`](backend/migrations/) | Esquema versionado com Alembic |
| [`backend/tests/`](backend/tests/) | Testes unitários e de integração |
| [`alinia-investigator/`](alinia-investigator/) | Agente TypeScript, ferramentas, recuperação de regras e histórico mensal sintético |
| [`scripts/`](scripts/) | Build estático e servidor Node com proxy do agente |
| [`docs/`](docs/) | Arquitetura, integração, requisitos e documentação técnica |

- [Planejamento quantitativo, hipóteses e resultados](docs/PLANEJAMENTO_QUANTITATIVO.md)
- [Backend, autenticação e políticas](backend/README.md)
- [Integração entre frontend, backend e chat](docs/INTEGRACAO_FRONTEND_BACKEND.md)
- [Abordagem do produto e identidade visual](docs/ABORDAGEM.md)
