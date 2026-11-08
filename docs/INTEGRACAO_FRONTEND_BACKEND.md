# Análise da integração — novo frontend × backend Alinia

**Data:** 2026-11-08  
**Origem:** `frontend/lp-copy-e-fundo` (`53a4d499`).  
**Destino:** `fix/auditoria-v42-p1-p2-2026-11-08`.  
**Merge de interface:** `d9f6c1e8` (dois pais).  
**Fonte funcional:** Workforce Intelligence PRD v4.2; não há aceite integral.

## O que foi mesclado

Foram trazidos **nove arquivos do frontend**: `src/app/index.html`, `src/app/app.css`, `src/app/app.js`, `src/index.html` e cinco arquivos em `src/styles/`. O `README.md` criado anteriormente e as correções do backend foram **preservados**, em vez de serem substituídos pela documentação da branch de frontend.

O novo visual altera a organização da visão geral, investigação, previsão, cinco cenários A–E e revisão do RH. A conexão de dados aparece em um diálogo dedicado, e os gráficos demonstrativos são renderizados como SVG.

## Integração verificada no código

| UI | Endpoint do backend | Situação |
| --- | --- | --- |
| Entrada com empresa, e-mail e senha | `POST /api/auth/login`, `GET /api/auth/me` | Conectado; bearer token apenas em memória |
| Equipes disponíveis | `GET /api/teams` | Conectado com escopo imposto pelo backend |
| Snapshots por equipe | `GET /api/teams/{team_id}/snapshots` | Conectado |
| Cartões agregados de demanda, capacidade, IPD, gap | `GET /api/teams/{team_id}/metrics?snapshot_id=...` | Conectado |
| Gráfico Demanda × capacidade e painel Fluxo da demanda | `GET /api/teams/{team_id}/demand-flow?snapshot_id=...` | Conectado; demanda dos últimos 6 períodos do CSV; a capacidade é a do último período, repetida como referência (não há histórico de capacidade); fluxo legado aparece como não classificado |
| Conversa com a Alinia (`src/app/agent.js`) | As rotas desta tabela, mais `GET /api/policies/resolve` | Conectado; cada pergunta é encaminhada a uma ferramenta fixa; o modelo de linguagem ainda não está ligado |
| Retomada de investigação após novo login | `GET /api/investigations`, `GET /api/investigations/{id}` | Conectado; o login restaura a última investigação só com leitura; o diálogo **Conectar dados** lista as investigações da equipe e o botão **Retomar** pode avançar o fluxo; o usuário precisa autenticar novamente ao atualizar a página |
| Abertura e retomada do fluxo | `POST /api/investigations`, `POST /api/investigations/{id}/advance` | Conectado; workflow síncrono e determinístico |
| Respostas às perguntas | `POST /api/investigations/{id}/answers` | Conectado; relatos não se tornam evidências verificadas |
| Previsão | Campo `forecast` da investigação | Conectado; gráfico usa os pontos da API quando disponíveis; intervalos não são P10/P50/P90 |
| Cinco cenários A–E | `GET /api/investigations/{id}/scenarios` | Conectado; B/C/D continuam exploratórios |
| Aprovar, rejeitar ou adiar | `POST /api/scenarios/{id}/decisions` | Rejeição e adiamento possíveis; **aprovação bloqueada** sem `conclusive=true` e `v42_validation` válida |
| Rascunho de requisição | `POST /api/scenarios/{id}/requisition-drafts` | Só após aprovação confirmada; sem execução externa |

### Resoluções do conflito em `app.js`

- Recuperação da investigação mais recente acessível, utilizando a API após login; não salva token no `localStorage` nem no `sessionStorage`.
- Limpeza de estado de investigação, cenários e aprovação ao mudar de equipe ou snapshot para não apresentar uma decisão de outro recorte.
- Botão **Aprovar** habilitado somente com cenário conclusivo **e** validação independente válida; a verificação definitiva continua no backend.
- Dados externos e respostas de gestores são adicionados ao DOM como `textContent`, não HTML executável.
- Estado visual de déficit não calculado não é confundido com `0`.

## Conversa com a Alinia

A tela inicial (`#agente`) é a interface de conversa com o agente. Enquanto o modelo de raciocínio da branch `agent/alinia-investigator` não está ligado, a conversa funciona assim:

- **Encaminhamento fixo:** a pergunta é classificada por padrões de texto (situação, investigação, previsão, cenários, contratação, regras, decisão, fontes) e vai para uma ferramenta que lê a API. Pedidos para revelar credenciais, avaliar pessoas ou usar dado individual são recusados antes de qualquer chamada.
- **Transparência:** cada resposta mostra os passos executados (endpoint e tempo) e o selo de origem de cada número, que abre o detalhe da fonte.
- **Perguntas ao gestor:** as perguntas pendentes da investigação aparecem na conversa; a resposta vai para `POST /api/investigations/{id}/answers` como relato não verificado, e o ciclo avança.
- **Limites:** a Alinia não aprova, não rejeita e não adia; ela leva até a Revisão do RH. Sem headcount conclusivo e validado, ela não recomenda número de vagas.
- **Sem conexão:** a conversa é uma simulação com os dados de exemplo da Unidade Centro, e a interface avisa isso.
- **Estado:** a conversa fica só em memória e é apagada a cada novo login.

Quando o modelo for ligado, ele passa a escolher a ferramenta e a redigir o texto; a interface (passos, fontes, perguntas e passagem para a decisão) não precisa mudar.

## Falha de execução identificada e corrigida

O teste HTTP de integração revelou que `StaticFiles(directory=prototype)` (configuração anterior) retornava **404 em `/prototype/app/`**. O backend foi ajustado para `StaticFiles(directory=prototype, html=True)` em `backend/app/main.py`, permitindo servir o `index.html` ao acessar a pasta da landing ou da aplicação, sem exigir `/index.html` na URL. O teste cobre ambas as rotas de diretório.

## Lacunas e riscos restantes

1. **Falta importação pela própria UI:** ainda é necessário criar e confirmar o CSV via API/Swagger. O frontend apenas seleciona snapshots já disponíveis.
2. **Landing e gráficos de exemplo:** até carregar métricas há valores sintéticos. Depois de carregá-las, o gráfico da visão geral usa a demanda do `demand-flow`; a linha de capacidade continua sendo uma referência constante do último período (a própria UI informa). Recortes com menos de 2 períodos mantêm a série ilustrativa.
3. **Sem dimensionamento v4.2 concluído:** forecast não alimenta o solver CP-SAT por competência/turno; as famílias B/C/D não têm simulação quantitativa. O frontend exibe apenas o resultado disponibilizado pela API.
4. **Aprovação operacional indisponível por segurança:** o workflow ainda não produz `v42_validation` independente e válida; o bloqueio não deve ser removido para fins de demonstração.
5. **Jira real indisponível:** a rota de sincronização ainda não persiste dados operacionais; o fluxo demonstrável usa CSV sintético.
6. **Sem sessão persistida no navegador:** ao atualizar, é necessário fazer login novamente. A investigação é retomada do banco após autenticação.
7. **Sem teste automatizado em navegador real:** verificação de sintaxe JS, hooks DOM, conteúdo servido pelo FastAPI e pytest não substituem testes Playwright/Cypress, acessibilidade visual, interação responsiva e E2E completo.
8. **Frontend isolado não equivale ao full-stack:** `npm run dev` abre somente arquivos estáticos em `localhost:5173`; para `/api` no mesmo origin, use o servidor FastAPI em `localhost:8000/prototype/app/`.

## Como conferir localmente

Instruções completas no [README principal](../README.md). Em resumo:

```bash
# Da raiz do repositório, ambiente Python 3.12 ativo e
# ALINIA_AUTH_SECRET definido no mesmo terminal:
python -m pip install -r backend/requirements.lock.txt
python -m alembic -c backend/alembic.ini upgrade head
python -m uvicorn backend.app.main:create_app --factory --reload
```

Acesse **http://127.0.0.1:8000/prototype/app/**, autentique como `rh` de uma empresa com snapshot, carregue as métricas e abra a investigação. Para criar o usuário e um CSV sintético veja as etapas 4.4 e 4.6 do README.

O teste de integração estática está em `backend/tests/test_frontend_smoke.py`. O workflow de CI inclui `node --check src/app/app.js`, build Node.js, pytest e teste de migração PostgreSQL. **O teste estático não executa o JavaScript em um browser**; esse é o próximo nível de validação.

**Conclusão:** o novo frontend está conectado às rotas essenciais de leitura e fluxo do backend e preserva a autorização de decisão. É uma **integração demonstrável com dados sintéticos**, não um produto v4.2 operacional ou uma prova de sincronização Jira/LLM/CP-SAT de ponta a ponta.
