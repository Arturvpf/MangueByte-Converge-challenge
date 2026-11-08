# Alinia — Workforce Intelligence

**Um agente de IA para investigar a demanda, entender a capacidade das equipes e construir alternativas de planejamento com evidências.**

A **Alinia** é uma proposta de plataforma **AI-native de Workforce Intelligence** para operações de serviços: em vez de exigir que gestores cruzem planilhas, investiguem desvios e montem cenários manualmente, **um agente investigador-planejador coordena a jornada de ponta a ponta** — recebe sinais operacionais, consulta fontes autorizadas, formula hipóteses, solicita informações, aciona modelos e ferramentas de cálculo, compara intervenções e apresenta recomendações verificáveis para decisão humana.

> **Nossa proposta:** um agente de IA que conduz a investigação de ponta a ponta, com acesso controlado a ferramentas de coleta, previsão, otimização e análise. Os cálculos e as verificações continuam independentes do modelo; a decisão permanece humana. **A versão disponível já permite demonstrar o frontend e a base de análise com dados sintéticos; a autonomia completa do agente é a próxima etapa.**

## O problema que queremos resolver

Uma equipe pode receber mais trabalho do que consegue absorver, mas isso nem sempre significa que a solução seja contratar. A causa pode envolver um pico sazonal, backlog acumulado, competências indisponíveis em horários críticos, mudanças de processo ou capacidade distribuída incorretamente.

A análise tradicional costuma depender de indicadores fragmentados, planilhas e perguntas feitas manualmente. Isso dificulta:

- **Enxergar a demanda real:** entradas, entregas concluídas, reaberturas, cancelamentos, backlog e solicitações não atendidas são informações diferentes.
- **Encontrar a causa:** uma média semanal esconde gargalos de competência, turno e disponibilidade.
- **Comparar respostas:** contratar, trazer temporários, capacitar, realocar ou reorganizar a operação têm custo, prazo, dependências e efeitos distintos.
- **Justificar decisões:** recomendações precisam citar dados e premissas, sinalizar incertezas e respeitar regras trabalhistas e de privacidade.

**Nossa pergunta central:** *e se um agente de IA pudesse conduzir essa investigação, buscar as evidências necessárias e preparar a melhor comparação possível antes de o RH decidir?*

### Público inicial

A Alinia foi concebida inicialmente para **operações de serviços que trabalham com solicitações recorrentes, indicadores de atendimento e histórico disponível** — como suporte técnico, serviços compartilhados, backoffice e BPO. Nesse contexto, é possível comparar volume recebido, trabalho concluído, backlog, cobertura de turnos e qualidade. A aderência e o retorno financeiro ainda precisam ser comprovados com empresas parceiras.

## A solução: um agente investigador-planejador

Na arquitetura final, o usuário não precisa executar manualmente cada cálculo ou escolher, por conta própria, a sequência das análises. **O agente conduz o processo** dentro de permissões, ferramentas e regras verificáveis.

| Etapa | Atuação planejada do agente de IA | Ferramentas e controles envolvidos |
| --- | --- | --- |
| **1. Receber** | Identificar uma nova demanda, aumento de backlog, alteração de capacidade ou solicitação do gestor | Eventos, CSV e Jira somente leitura; WFM e ponto em fases futuras |
| **2. Coletar e validar** | Consultar fontes autorizadas, identificar inconsistências e pedir dados que faltam | Conectores tipados, validação de esquemas, unidades, origem, versão e deduplicação |
| **3. Investigar** | Elaborar hipóteses sobre sazonalidade, competências, turnos, processos e disponibilidade; confrontá-las com evidências | Métricas, histórico, memória de execução e perguntas ao gestor |
| **4. Prever** | Escolher quando a previsão é necessária, solicitar o cálculo e interpretar a incerteza | Demand Forecaster com baseline, backtesting, intervalos e abstenção |
| **5. Planejar** | Propor intervenções adequadas ao diagnóstico e suas combinações | Cenários A–E, dados de custo, cobertura, lead time e treinamento |
| **6. Simular** | Acionar ferramentas para testar viabilidade, picos e ausência de recursos; comparar resultados | OR-Tools CP-SAT; SimPy **se houver filas** e dados adequados; Policy Engine |
| **7. Revisar e explicar** | Rever hipóteses, reconstruir cenários inválidos e apresentar trade-offs, riscos e fontes | Validadores **determinísticos independentes**, trilha de auditoria e guardrails |
| **8. Encaminhar e acompanhar** | Preparar o resultado estruturado para RH, Operações e Finanças e, após decisões autorizadas, monitorar os indicadores | Aprovação humana efetiva, rascunho de requisição, métricas pós-decisão |

O fluxo é **iterativo**, não uma sequência rígida: se uma ferramenta identificar dados insuficientes, regra conflitante ou cenário inviável, o agente volta a investigar e planejar antes de apresentar uma recomendação.

**Relato não é fato.** Respostas de gestores são registradas como relatos, com origem e data, e precisam ser confrontadas com fontes. Uma hipótese sem evidência permanece explicitamente não verificada.

### Alternativas comparadas

| Cenário | Questão investigada |
| --- | --- |
| **A · Contratar permanentemente** | Existe déficit estrutural persistente que justifique ampliar o quadro, considerando custo, recrutamento, admissão e ramp-up? |
| **B · Contratação temporária** | O problema é transitório, a modalidade é permitida e a capacidade chega a tempo? |
| **C · Realocar ou capacitar** | É possível redistribuir ou desenvolver competências sem criar um déficit na equipe de origem? |
| **D · Redesenhar turnos ou processos** | Uma reorganização melhora a cobertura e o SLA respeitando jornadas, repousos e requisitos operacionais? |
| **E · Não intervir** | O que acontece com backlog, cobertura, risco e custo se nada mudar? |

O agente **propõe e interpreta**. Os motores determinísticos calculam disponibilidade, capacidade, custo e viabilidade. Nenhuma alternativa é considerada aprovada apenas porque o modelo de linguagem a sugeriu.

## Arquitetura: IA para investigar, ferramentas para validar

**Um único agente investigador-planejador** coordena a jornada. Ele decide quais informações buscar, quando aprofundar uma hipótese e quais análises solicitar, mas **não substitui os motores de cálculo, as regras de autorização ou os validadores independentes**. Essa separação permite aproveitar a flexibilidade do modelo de linguagem sem depender dele para resultados matemáticos ou decisões sensíveis.

```mermaid
flowchart TD
    E["Eventos operacionais ou solicitação humana"]
    C["Conectores autorizados<br/>CSV / Jira somente leitura<br/>WFM e ponto: futuro"]
    O["Orquestração<br/>estado, memória, permissões e checkpoints"]
    A["AGENTE ÚNICO DE IA<br/>investigador-planejador"]
    M["Metrics Engine<br/>demanda e capacidade"]
    F["Demand Forecaster<br/>baseline e incerteza"]
    S["Solver / Simulação<br/>CP-SAT e SimPy se aplicável"]
    P["Policy Engine<br/>regras aprovadas e versionadas"]
    V{"Validadores independentes<br/>restrições, consistência e privacidade"}
    H["RH + Operações + Finanças<br/>revisão efetiva e aprovação"]
    R["Decisão auditada<br/>monitoramento posterior"]

    E --> O
    O --> A
    A <--> C
    A <--> M
    A <--> F
    A <--> S
    A <--> P
    A -->|"cenários, fontes e premissas"| V
    V -->|"erro, bloqueio ou evidência ausente"| A
    V -->|"opções verificadas"| H
    H -->|"ajustar ou solicitar revisão"| A
    H -->|"decisão autorizada"| R
```

### Separação de responsabilidades

| Agente de IA (LLM) | Ferramentas e serviços determinísticos |
| --- | --- |
| Planeja a investigação, formula hipóteses e escolhe quais ferramentas chamar | Calculam demanda, FTE, capacidade, custos e previsão |
| Busca contexto autorizado e solicita informações faltantes | Impõem isolamento por empresa/equipe, validação de unidades e rastreabilidade |
| Normaliza competências **com evidências** e gera alternativas A–E | Resolvem otimização de cobertura por competência e intervalo; verificam viabilidade |
| Explica incertezas, trade-offs e motivos para a recomendação | Aplicam regras jurídicas versionadas, restrições rígidas e testes independentes |
| Volta ao planejamento quando surgem bloqueios ou contradições | Persistem hashes, fontes, versões, decisões e eventos de auditoria |

**Por que combinar IA e métodos determinísticos?** O agente é útil para explorar causas, buscar contexto e organizar possibilidades. Já os cálculos de horas, custos, requisitos, elegibilidade e cobertura devem ser reprodutíveis. Por isso, a Alinia utiliza contratos de dados, ferramentas tipadas, regras versionadas e validação independente para impedir que uma resposta convincente seja confundida com uma recomendação comprovada.

### Memória e limites de autonomia

A arquitetura prevê memória de execução para **hipóteses, evidências, perguntas, versões e decisões**, além de memória organizacional isolada por empresa para regras e premissas aprovadas. **Dados pessoais desnecessários não devem entrar no contexto ou na memória do agente.**

O agente poderá **ler dados autorizados, investigar, calcular por ferramentas, simular, explicar e preparar rascunhos**. Ele **não** poderá selecionar ou desligar candidatos, alterar ponto, salário ou escala no MVP. A criação de requisições e qualquer ação administrativa exigem **aprovação humana explícita**, com acesso às premissas, possibilidade de alteração e justificativa registrada.

Se a previsão se abstiver, faltar uma regra ou a cobertura obrigatória falhar, o sistema deve **pedir revisão ou dados**, não oferecer uma contratação exata como fato. A revisão crítica por outro modelo pode complementar a análise, mas **não substitui os validadores determinísticos**.

## O que já pode ser demonstrado

Construímos primeiro a **base de dados, cálculo, auditoria e interface** que sustenta a experiência. A próxima evolução é permitir que o agente escolha e coordene essas ferramentas conforme cada investigação — sem transformar estimativas em fatos nem ultrapassar os limites de autonomia.

A tela inicial da plataforma é a **conversa com a Alinia**, o agente: a pessoa pergunta em linguagem natural e a Alinia mostra os passos que consultou, o selo de origem de cada número, as perguntas ao gestor e a passagem para a decisão humana. Ao lado da conversa ficam cinco áreas navegáveis: **Visão geral**, **Investigação**, **Previsão**, **Cenários** e **Revisão do RH**. A landing page apresenta o conceito do produto; a plataforma permite autenticação, consulta de recortes persistidos e interação com as APIs de investigação e decisão.

A interface distingue dados ilustrativos de dados recebidos da API. Na revisão, cenários sem validação independente **não podem ser aprovados**. Rejeitar e adiar são decisões registráveis pelo perfil autorizado.

| Componente | Situação atual |
| --- | --- |
| Novo frontend com Visão geral, Investigação, Previsão, Cenários e Revisão do RH | **Implementado e conectado à API** |
| Conversa com a Alinia, tela inicial da plataforma | **Implementada e conectada à API** por ferramentas fixas; o modelo de linguagem ainda não escolhe as ferramentas |
| Autenticação, escopo por empresa/equipe, snapshots, métricas e auditoria | **Implementado para demonstração** |
| CSV e fixture de Jira com dados sintéticos | **Implementado**; coleta ativa pelo agente e Jira real ainda pendentes |
| Investigação com checkpoints, perguntas e retomada | **Implementada de forma determinística**; não é ainda a orquestração autônoma do LLM |
| Previsão com mediana móvel, backtesting e abstenção | **Baseline implementado**; faltam previsões aplicadas por skill e turno |
| Cenários A–E | **Estruturados na API**; B/C/D ainda não são simulações quantitativas completas |
| Otimizador CP-SAT e validador independente | **Módulos existentes e testados**, ainda não conectados ao workflow principal |
| **Agente único conduzindo coleta → investigação → planejamento → simulação** | **Próxima etapa: integração ao fluxo principal** |
| Sincronização operacional com Jira real | **Pendente** |
| Aprovação definitiva e requisição operacional | **Bloqueadas** até validação independente e revisão autorizada |

Um **protótipo separado do investigador de IA** está disponível na branch [`agent/alinia-investigator`](https://github.com/Arturvpf/MangueByte-Converge-challenge/tree/agent/alinia-investigator), explorando consultas a dados, recuperação de regras e filtros de privacidade. Ele ainda não coordena o fluxo principal de ponta a ponta; por isso, seus resultados não são apresentados como uma integração concluída.

### Como vamos medir o valor da IA

Para avaliar o ganho real do agente, planejamos comparar **três formas de tomar a mesma decisão, usando os mesmos dados**:

1. **Processo atual:** a forma como a empresa dimensiona suas equipes hoje.
2. **Baseline determinístico:** métricas, forecast e cenários com fluxo convencional, **sem LLM**.
3. **Alinia AI-native:** o baseline **mais o agente investigador-planejador** que coordena a coleta, formula hipóteses, chama ferramentas, revisa alternativas e explica a decisão.

O objetivo não é medir o número de chamadas ao modelo, mas se a investigação assistida por IA **reduz o tempo até uma decisão fundamentada, diminui retrabalho e evita erros**, sem aumentar riscos. Avaliaremos tempo de análise, SLA, backlog, custos, qualidade das previsões, cobertura por turno, contestações e intervenções humanas. **O componente de IA precisa demonstrar benefício adicional em relação à análise determinística, não apenas produzir respostas mais elaboradas.**

### Exemplo de investigação conduzida pelo agente

Imagine que uma equipe de suporte apresente aumento de backlog por três semanas. Em vez de recomendar imediatamente novas contratações, **o agente deverá** consultar o histórico de entradas e conclusões, verificar a distribuição por competência e turno e investigar explicações alternativas, como sazonalidade, indisponibilidade temporária ou mudança de processo. Se faltarem dados essenciais, ele solicita a informação ao gestor ou sinaliza a limitação.

Com evidências suficientes, o agente aciona ferramentas para projetar demanda e comparar contratação permanente, temporários, realocação, redesenho operacional e nenhuma intervenção. Cada alternativa precisa mostrar **prazo de efeito, cobertura, custo estimado, riscos, premissas e pontos que exigem revisão**. Um cenário inviável volta para investigação; o resultado só segue ao RH depois de passar pelas validações aplicáveis.

*Esse exemplo ilustra a experiência pretendida com IA. A versão atual permite demonstrar as etapas de dados, investigação determinística e comparação exploratória, mas não toda a autonomia descrita acima.*

## Tecnologias

| Camada | Tecnologias |
| --- | --- |
| Frontend | HTML, CSS, JavaScript ES Modules e gráficos SVG |
| API e contratos | Python 3.12, FastAPI, Pydantic |
| Dados e auditoria | SQLAlchemy, Alembic, SQLite local e PostgreSQL |
| Ferramentas de planejamento | Motor de métricas, baseline de previsão e otimizador OR-Tools CP-SAT (módulo separado) |
| Orquestração de IA | **LangGraph como direção técnica do projeto**; fluxo produtivo do agente ainda não integrado |
| Qualidade | Pytest, regressões de frontend/API, GitHub Actions |

---

## Como executar

### Pré-requisitos

**Git** e **Python 3.12** são suficientes para iniciar a plataforma completa com SQLite. **Node.js 22** é necessário somente para executar ou gerar o build do site estático. Todos os comandos a seguir partem da **raiz do repositório**.

### 1. Clonar o projeto

```bash
git clone https://github.com/Arturvpf/MangueByte-Converge-challenge.git
cd MangueByte-Converge-challenge
```

A branch padrão é a **`main`**, que contém a aplicação integrada e as instruções desta entrega.

### 2. Instalar o backend

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

### 3. Configurar autenticação e banco local

O SQLite já é o banco padrão (`sqlite:///./alinia.db`). Defina a chave de autenticação **no mesmo terminal** que executará o backend.

**PowerShell**

```powershell
$env:DATABASE_URL = "sqlite:///./alinia.db"
$env:ALINIA_AUTH_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Linux/macOS**

```bash
export DATABASE_URL="sqlite:///./alinia.db"
export ALINIA_AUTH_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

O arquivo [`backend/.env.example`](backend/.env.example) descreve as demais variáveis, **mas não é carregado automaticamente**. Não versionar tokens, senhas ou segredos. Para preservar sessões entre reinicializações, reutilize a mesma chave de autenticação.

### 4. Preparar o banco e criar o usuário de demonstração

```bash
python -m alembic -c backend/alembic.ini upgrade head
python -m backend.app.auth.cli create-tenant --tenant-id demo --name "Empresa Demo"
python -m backend.app.auth.cli create-user --tenant-id demo --email rh@demo.example --role rh
```

A criação do usuário solicita uma senha no terminal. O perfil **RH** pode investigar e registrar decisões; o perfil `admin` é destinado à administração de contas e não substitui o RH na demonstração.

Os comandos de criação só precisam ser executados **uma vez em um banco novo**.

### 5. Iniciar a aplicação integrada

```bash
python -m uvicorn backend.app.main:create_app --factory --reload
```

| Endereço local | Finalidade |
| --- | --- |
| [`/prototype/`](http://127.0.0.1:8000/prototype/) | Landing page |
| [`/prototype/app/`](http://127.0.0.1:8000/prototype/app/) | **Plataforma integrada ao backend** |
| [`/docs`](http://127.0.0.1:8000/docs) | Swagger/OpenAPI |
| [`/health`](http://127.0.0.1:8000/health) | Verificação básica do processo |

Todos usam `http://127.0.0.1:8000`. O FastAPI serve os arquivos do frontend e as APIs **na mesma origem**. A aplicação não exige um servidor Node separado para autenticar e consultar dados.

### 6. Carregar dados sintéticos para a demonstração

A plataforma lista snapshots existentes, mas **a importação de CSV ainda não está implementada na interface**. O caminho mais curto para preparar uma demonstração é a fixture de Jira, **sem conexão com Jira real**:

1. Abra [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs) e execute `POST /api/auth/login` usando `tenant_id: demo`, `email: rh@demo.example` e sua senha.
2. Copie o `access_token` e configure-o no botão **Authorize** do Swagger.
3. Execute `POST /api/imports/jira` com o JSON abaixo. A resposta `status: complete` indica que o snapshot sintético foi persistido.
4. Abra [a plataforma](http://127.0.0.1:8000/prototype/app/), entre com as mesmas credenciais, selecione a equipe `team-demo` e carregue as métricas.

```json
{
  "team_id": "team-demo",
  "fixture": "issues"
}
```

**Alternativa:** usar `POST /api/imports` com um CSV agregado (como texto no campo JSON `content`) e depois `POST /api/imports/{import_id}/confirm`. O formato e os campos obrigatórios estão descritos em [`backend/CONTRATOS.md`](backend/CONTRATOS.md) e em `backend/app/ingestion/csvparse.py`. Nenhum dado pessoal deve ser usado na demonstração.

### 7. Percorrer o fluxo no frontend

Com o snapshot carregado, a demonstração sugerida é: **Visão geral → Abrir investigação → Responder às perguntas → Previsão → Comparar A–E → Revisão do RH**. O mesmo caminho pode ser feito pela **Conversa com a Alinia**, perguntando, por exemplo, "Por que a equipe não dá conta da demanda?" e respondendo às perguntas do gestor ali mesmo.

**Nesta entrega, a execução demonstrada é determinística**: a investigação pode exigir mais de uma rodada de respostas, mas o agente LLM ainda não escolhe nem executa as ferramentas do fluxo principal. Relatos do gestor continuam **não verificados** e não alteram automaticamente a capacidade calculada. Com histórico insuficiente, a previsão se abstém e os cenários ficam inconclusivos. O bloqueio de aprovação é **comportamento esperado**, não falha de instalação.

## Testes e build

**Backend e migrações** (ambiente Python ativo):

```bash
python -m pytest backend/tests -q
python -m alembic -c backend/alembic.ini upgrade head
```

**Frontend estático** (Node.js 22):

```bash
node --check src/app/app.js
npm run build
npm run dev
```

`npm run dev` serve apenas os arquivos estáticos em `http://127.0.0.1:5173`. **Para testar a integração com as rotas `/api`, use a plataforma via FastAPI na porta `8000`**, como mostrado acima.

O CI executa testes de backend, regressões da integração HTTP/DOM, verificação de JavaScript, build e migração PostgreSQL a partir de um esquema legado. Veja o [workflow de integração](.github/workflows/p1-p2-integration.yml).

## Evolução da plataforma

O próximo marco é ligar o **agente investigador-planejador** ao fluxo já persistido. Ele poderá partir de um alerta de demanda, buscar dados autorizados, levantar hipóteses, pedir esclarecimentos, acionar previsão e otimização, reconstruir alternativas inviáveis e encaminhar ao RH uma análise com evidências, custos, limites e incertezas. Os validadores independentes continuarão determinando quais propostas podem avançar.

Antes de um piloto empresarial, ainda são necessários: sincronização Jira real somente leitura, simulações quantitativas A–D, previsão por skill/turno, validação de política por categoria/contrato, proteção de dados e testes de segurança do agente (inclusive prompt injection e saídas de ferramentas), avaliações de viés e experimento de ganho incremental do LLM.

Os resultados ilustrativos não são indicadores operacionais reais. Antes de carregar um recorte, o frontend exibe séries de exemplo. Depois, o gráfico da visão geral usa a demanda importada (`demand-flow`), com a capacidade do último período como referência constante; as métricas carregadas da API são identificadas separadamente.

**A intenção é tornar o agente o centro da experiência de investigação, sem transformar o LLM em fonte de verdade matemática, jurídica ou decisória.**

## Organização do repositório

```text
src/                      Landing page e aplicação web
scripts/                  Servidor estático e build do frontend
backend/app/              API e módulos de domínio
backend/migrations/       Evolução de esquema com Alembic
backend/fixtures/         Entradas sintéticas para demonstração
backend/tests/            Testes unitários e de integração
docs/                     Arquitetura, integração, requisitos e decisões técnicas
.github/workflows/        Validações automatizadas
```

### Documentação técnica

- [Integração entre frontend e backend](docs/INTEGRACAO_FRONTEND_BACKEND.md)
- [Backend: arquitetura, autenticação, políticas e contratos](backend/README.md)
- [Contratos de dados e endpoints](backend/CONTRATOS.md)
- [Conceito e identidade visual](docs/ABORDAGEM.md)

---

**Alinia — um agente para investigar, reunir evidências e construir alternativas; pessoas continuam responsáveis pelas decisões.**

*A versão disponível reúne o frontend e a fundação de análise com dados sintéticos. A condução autônoma pelo agente de IA permanece como evolução arquitetural; decisões administrativas exigem validação independente e aprovação humana.*