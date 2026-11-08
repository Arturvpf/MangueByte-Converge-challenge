# Alinia — Workforce Intelligence

**Plataforma experimental de inteligência de força de trabalho**, desenvolvida para investigar desequilíbrios entre demanda e capacidade operacional, comparar alternativas de dimensionamento e apoiar decisões **com revisão humana**.

Este repositório reúne a landing page, um protótipo de cinco telas, uma API FastAPI e motores determinísticos de análise e otimização. O documento funcional vigente é o **Workforce Intelligence PRD v4.2**. **O MVP não está concluído, não é um serviço de contratação autônoma e não deve processar dados pessoais reais sem validações adicionais.**

## 1. Problema

Operações de serviços precisam decidir quando **contratar, realocar, capacitar, redesenhar turnos ou não intervir**, frequentemente com informações dispersas entre sistemas e planilhas. A quantidade de solicitações recebidas não equivale à quantidade concluída: backlog, cancelamentos, reaberturas e demanda não atendida mudam o diagnóstico.

Uma média geral de produtividade também pode ocultar déficit de **competências e turnos específicos**. Decisões tomadas apenas com médias e relatos não verificados podem levar a custos desnecessários, cobertura insuficiente e recomendações incompatíveis com jornadas, modalidades contratuais ou regras aplicáveis.

**O desafio:** transformar dados operacionais auditáveis em cenários comparáveis, com premissas explícitas, incerteza, segurança e decisão final humana — sem confundir previsão ou opinião do gestor com fato comprovado.

## 2. Solução proposta

A Alinia busca organizar esse processo em uma sequência verificável:

1. **Receber e validar dados:** importar informações agregadas por equipe, competência e período; distinguir entradas, conclusões, backlog e demanda não atendida.
2. **Diagnosticar a operação:** calcular disponibilidade, capacidade efetiva, IPD e lacunas; registrar evidências, hipóteses não verificadas e perguntas.
3. **Prever a demanda:** aplicar um baseline com backtesting temporal, intervalos empíricos quando justificáveis e abstenção se o histórico for insuficiente.
4. **Comparar cinco famílias de cenário (A–E):** contratação permanente; contratação temporária; realocação/capacitação; redesenho de turnos/processos; nenhuma intervenção.
5. **Validar e decidir:** verificar restrições rígidas de forma independente, apresentar limitações ao RH e registrar decisões versionadas; nunca executar contratações ou alterações de escala automaticamente.

O PRD v4.2 prevê **um agente investigador-planejador com ferramentas delimitadas**. O código atual possui investigação determinística e uma experiência experimental de LangGraph, **mas ainda não um agente LLM produtivo integrado ao fluxo**.

### O que funciona e o que permanece pendente

| Capacidade | Estado na branch de correções |
| --- | --- |
| Landing e interface com cinco telas | Implementadas; dados ilustrativos coexistem com dados carregados da API |
| Autenticação, papéis e escopo por empresa/equipe | Implementados para o ambiente de desenvolvimento, com limitações de segurança documentadas |
| Importação CSV, snapshots, ledger agregado e métricas | Implementados com validação e testes |
| Jira | Fixture sintética funciona; cliente GET tem escopo por projeto; **sincronização real e mapeamento operacional pendentes** |
| Investigação e retomada | Fluxo determinístico com checkpoints; respostas são relatos não verificados; agente LLM e worker produtivo pendentes |
| Previsão | Baseline de mediana móvel e backtesting; **a previsão não alimenta quantitativamente o solver por skill/turno** |
| Otimização | Solver anterior no fluxo; módulo **OR-Tools CP-SAT v4.2** existe e é testado, mas **não está integrado ao workflow** |
| Cenários A–E | Cinco categorias na API; B/C/D ainda são exploratórios, não simulações completas das intervenções |
| Revisão e decisões do RH | Registro de rejeição/adiamento e histórico; **aprovação conclusiva v4.2 bloqueada** até validação independente integrada |
| Execução externa | **Desabilitada**: sem contratação, alteração de escala, ponto ou salário |

As pendências, evidências e critérios de aceite estão em [Correções da auditoria v4.2](docs/CORRECOES_AUDITORIA_V42.md) e [Rebaseline do PRD v4.2](docs/REBASELINE_PRD_V42.md).

## 3. Tecnologias e organização

| Camada | Tecnologias |
| --- | --- |
| Frontend | HTML, CSS e JavaScript ES Modules; landing com Lenis vendorizado |
| API | Python 3.12, FastAPI e Pydantic |
| Dados | SQLAlchemy, Alembic; SQLite no desenvolvimento, PostgreSQL suportado |
| Otimização | Solver de fluxo máximo no workflow; OR-Tools CP-SAT v4.2 isolado |
| Orquestração | Fluxo persistido síncrono; LangGraph experimental com nós simulados |
| Qualidade | Pytest, testes de integração, CI com migrações SQLite/PostgreSQL e build Node.js |

```text
src/                     Landing e protótipo (/app/)
scripts/                 Servidor estático e build sem dependências
backend/app/             API, auth, ingestão, dados, métricas, previsão, cenários
backend/migrations/      Revisões Alembic
backend/tests/           Testes unitários, integração e regressão
backend/fixtures/        Dados sintéticos de exemplo
docs/                    Arquitetura, abordagem e auditoria
```

O fluxo atual é aproximadamente **CSV → snapshot → métricas/investigação → previsão → cenários exploratórios (solver anterior) → revisão humana**. O CP-SAT v4.2 e seu validador independente existem como módulos próprios, mas ainda precisam ser conectados a esse fluxo antes de qualquer aprovação operacional.

## 4. Como rodar o projeto localmente

### Pré-requisitos

- **Git**
- **Python 3.12** (a versão utilizada no CI)
- **Node.js 22** e npm, para o site estático e seu build
- Não é necessário instalar PostgreSQL para começar: o backend usa **SQLite local** por padrão.

Execute os comandos **a partir da raiz do repositório**. Não rode o Python de dentro da pasta `backend/`, pois os imports utilizam `backend.app`.

### 4.1. Clonar e selecionar a branch

```bash
git clone https://github.com/Arturvpf/MangueByte-Converge-challenge.git
cd MangueByte-Converge-challenge
git switch fix/auditoria-v42-p1-p2-2026-11-08
```

Esta é a branch do [PR de correções da auditoria](https://github.com/Arturvpf/MangueByte-Converge-challenge/pull/2), baseada na branch de reconciliação P1/P2. As mudanças ainda não estão na `main`.

### 4.2. Ambiente Python e dependências

**Windows — PowerShell**

```powershell
py -3.12 -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.lock.txt
```

**Linux/macOS**

```bash
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.lock.txt
```

Se não conseguir ativar o ambiente, use diretamente `backend/.venv/Scripts/python` no Windows ou `backend/.venv/bin/python` no Linux/macOS para os comandos seguintes.

### 4.3. Configurar variáveis de ambiente

O arquivo [`backend/.env.example`](backend/.env.example) documenta os nomes das variáveis, **mas não é carregado automaticamente**. Configure-as no terminal em que vai executar a API.

**Windows — PowerShell**

```powershell
$env:DATABASE_URL = "sqlite:///./alinia.db"
$env:ALINIA_AUTH_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Linux/macOS**

```bash
export DATABASE_URL="sqlite:///./alinia.db"
export ALINIA_AUTH_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

O segredo precisa ter pelo menos 32 caracteres. **Para manter sessões válidas após reiniciar o servidor, conserve o mesmo segredo em seu ambiente local**; gerar outro invalida os tokens existentes. Não publique o segredo ou credenciais no Git. `ALINIA_BOOTSTRAP_PASSWORD` é opcional: se não estiver definida, a CLI solicita a senha interativamente.

### 4.4. Criar o banco e usuários de demonstração

Com o ambiente Python ativo e as variáveis configuradas:

```bash
python -m alembic -c backend/alembic.ini upgrade head
python -m backend.app.auth.cli create-tenant --tenant-id demo --name "Empresa Demo"
python -m backend.app.auth.cli create-user --tenant-id demo --email admin@demo.example --role admin
python -m backend.app.auth.cli create-user --tenant-id demo --email rh@demo.example --role rh
```

Informe as senhas solicitadas. Use **senhas diferentes e suficientemente fortes**. Esses comandos de criação são para um banco novo; executá-los novamente com os mesmos identificadores retorna conflito.

**Importante:** `admin` gerencia contas, mas **não tem permissão para investigar equipes**. Faça login na plataforma com o usuário `rh@demo.example` para testar análises e decisões. As regras do PRD v4.2 continuam bloqueando aprovações operacionais sem evidência independente e validação jurídica.

### 4.5. Iniciar a API e a aplicação integrada

```bash
python -m uvicorn backend.app.main:create_app --factory --reload
```

O próprio FastAPI serve a API **e** os arquivos de `src/` na mesma origem HTTP. Acesse:

| Endereço | Uso |
| --- | --- |
| [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) | Saúde do processo |
| [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | Documentação interativa da API |
| [http://127.0.0.1:8000/prototype/](http://127.0.0.1:8000/prototype/) | Landing page |
| [http://127.0.0.1:8000/prototype/app/](http://127.0.0.1:8000/prototype/app/) | Plataforma com acesso às APIs |

Na plataforma, abra a seção de conexão e informe a empresa `demo`, o e-mail `rh@demo.example` e a senha configurada. **Para aparecer uma equipe na interface, importe primeiro um snapshot** (etapa seguinte). Até carregar dados pela API, os cartões exibem informações ilustrativas.

### 4.6. Criar um snapshot inicial por CSV (exemplo PowerShell)

Em **outro terminal PowerShell**, com o backend rodando, use apenas os dados sintéticos abaixo. O endpoint recebe **JSON contendo o texto CSV**, e não upload `multipart/form-data`.

```powershell
$base = "http://127.0.0.1:8000"
$senha = Read-Host "Senha do usuário RH"

$login = Invoke-RestMethod -Method Post -Uri "$base/api/auth/login" -ContentType "application/json" -Body (
  @{tenant_id="demo"; email="rh@demo.example"; password=$senha} | ConvertTo-Json
)
$headers = @{Authorization = "Bearer $($login.access_token)"}

$csv = @'
skill_id,shift_id,pool_id,eligible_hours,available_hours,period_start,period_end_exclusive,timezone,demand_cases,hours_unit,demand_unit,cases_per_hour
atendimento,manha,pool-demo,10,10,2026-11-02,2026-11-09,America/Recife,14,hours_per_period,cases_per_period,1
'@

$importacao = Invoke-RestMethod -Method Post -Uri "$base/api/imports" -Headers $headers -ContentType "application/json" -Body (
  @{team_id="team-demo"; filename="demo.csv"; content=$csv} | ConvertTo-Json
)
$importacao

if ($importacao.status -eq "ready") {
  Invoke-RestMethod -Method Post -Uri "$base/api/imports/$($importacao.import_id)/confirm" -Headers $headers
}
```

Após confirmar a importação, **atualize `/prototype/app/` e entre novamente**. Selecione `team-demo`, carregue as métricas e inicie a investigação.

O exemplo contém **uma única semana**: é esperado que a previsão **se abstenha por histórico insuficiente** e que cenários de contratação não sejam considerados conclusivos. Uma resposta `409 NOT_CONCLUSIVE` ao tentar aprovar é um bloqueio deliberado, não um erro de instalação.

Para importar dados com histórico, consulte os contratos de [`backend/CONTRATOS.md`](backend/CONTRATOS.md) e o validador em `backend/app/ingestion/csvparse.py`. Não inclua CPF, nomes, e-mails, salários individuais ou motivos de afastamento.

### 4.7. Rodar somente o frontend estático (opcional)

Em um terminal separado, na raiz do projeto:

```bash
npm run dev
```

Abre a landing em **http://127.0.0.1:5173/** e o protótipo em **http://127.0.0.1:5173/app/**. Esse servidor Node.js **não oferece as rotas `/api`**: a conexão do protótipo com o backend não funciona nessa porta sem um proxy adicional. Para testar a integração, utilize `http://127.0.0.1:8000/prototype/app/` (etapa 4.5).

Comandos adicionais:

```bash
npm run build    # copia src/ para dist/, sem bundler
npm run preview  # build e servidor estático em http://127.0.0.1:4173
```

Os arquivos devem ser servidos via HTTP: não abra o HTML usando `file://`.

### 4.8. Executar testes

Com o ambiente Python ativo, da raiz do repositório:

```bash
python -m pytest backend/tests -q
python -m alembic -c backend/alembic.ini upgrade head
npm run build
```

A suíte cobre contratos, importação, permissões, migrações, planejamento, forecast e regressões. O GitHub Actions também testa a migração de um banco PostgreSQL legado. **Testes passando não equivalem a aceite do PRD ou autorização de uso com dados reais.**

### 4.9. PostgreSQL (opcional)

Para utilizar PostgreSQL em vez de SQLite, crie um banco local, configure `DATABASE_URL` no formato:

```text
postgresql+psycopg://usuario:senha@localhost:5432/alinia
```

Aplique as migrações **nesse banco** antes de iniciar o servidor. Use um gerenciador de segredos ou variável de ambiente para a conexão; codifique caracteres especiais na senha. As migrações `0009` e `0010` preservam checkpoints Jira legados sem equipe e versões antigas dos cenários; valide backups e restore antes de alterar qualquer banco persistente.

## 5. Variáveis de ambiente

| Variável | Necessária? | Descrição |
| --- | --- | --- |
| `DATABASE_URL` | Não | SQLite local (`sqlite:///./alinia.db`) se não configurada |
| `ALINIA_AUTH_SECRET` | **Sim, para login** | Chave local de assinatura dos tokens (mínimo 32 caracteres) |
| `ALINIA_ACCESS_TOKEN_TTL_SECONDS` | Não | Validade do token; padrão: 3600 s |
| `ALINIA_BOOTSTRAP_PASSWORD` | Não | Senha para criação de usuários pela CLI; sem ela a CLI solicita interativamente |
| `JIRA_BASE_URL` | Só para leitura Jira externa | URL HTTPS do Jira autorizado |
| `JIRA_PROJECT_KEY` | Só para leitura Jira externa | Projeto explicitamente autorizado; bloqueia consultas sem escopo |
| `JIRA_API_TOKEN` | Só para leitura Jira externa | Token de leitura; armazenar fora do Git |

**Atenção:** mesmo com as três variáveis Jira, `POST /api/imports/jira/sync` ainda retorna `503 INTEGRATION_UNAVAILABLE`, pois falta transformar e persistir os eventos do Jira. O endpoint `POST /api/imports/jira` usa apenas uma fixture sintética.

## 6. Problemas comuns

- **`503 AUTH_UNAVAILABLE` no login:** configure `ALINIA_AUTH_SECRET` no processo que inicia o backend.
- **`404` em `/api` na porta 5173:** você está no servidor estático. Abra a plataforma em `/prototype/app/` na porta 8000.
- **Nenhuma equipe aparece no painel:** importe e confirme um CSV com o usuário RH; em seguida atualize a página e faça login novamente.
- **`ModuleNotFoundError: backend`:** execute os comandos na raiz do repositório com o ambiente virtual ativo.
- **`no such table` ou erro de schema:** rode `python -m alembic -c backend/alembic.ini upgrade head` usando o mesmo `DATABASE_URL` do servidor.
- **`409 NOT_CONCLUSIVE` ao aprovar:** bloqueio esperado: o fluxo não dispõe ainda de todas as evidências v4.2.
- **`503 INTEGRATION_UNAVAILABLE` no Jira:** a sincronização real ainda não foi implementada; use o CSV ou a fixture sintética no desenvolvimento.

## 7. Segurança, limitações e próximos passos

O sistema **não realiza contratação automática, seleção/desligamento, alteração de jornada, ponto ou salário**. As regras legais devem ser parametrizadas e aprovadas por responsáveis competentes; valores sintéticos não constituem interpretação jurídica validada. O projeto precisa de avaliação de privacidade e segurança antes de dados de clientes.

Para completar o MVP v4.2 faltam: previsão por competência/turno aplicada ao dimensionamento; integração do CP-SAT e da validação independente ao workflow; simulações reais A–D; Jira somente leitura com ingestão operacional; agente investigador-planejador LangGraph com ferramentas seguras; testes de viés, LGPD/RIPD, aprovação de domínio e experimento de valor em três braços.

Documentação adicional:

- [Correções da auditoria v4.2](docs/CORRECOES_AUDITORIA_V42.md)
- [Matriz de requisitos / rebaseline v4.2](docs/REBASELINE_PRD_V42.md)
- [Backend e contratos](backend/README.md)
- [Abordagem visual da landing](docs/ABORDAGEM.md)

**Status:** projeto em desenvolvimento; branch de correções em PR draft, sem validação para produção.
