# Contratos compartilhados v1 — COM-01

Estes contratos são um acordo inicial para revisão cruzada, não uma aplicação, autorização, armazenamento ou integração de produção. A Pessoa 1 mantém `app/contracts/v1.py`: `SkillCapacitySnapshot`, `InvestigationReport`, `ForecastResult`, estado da orquestração e envelopes comuns. A Pessoa 2 mantém os contratos de cenários e revisão; as propostas abaixo não são implementação nem contrato aprovado. Mudanças que afetem a outra equipe exigem revisão e teste de contrato. Os dois arquivos em `fixtures/contracts/` descrevem empresas e equipes inteiramente sintéticas, sem pessoas ou segredos; não são dados operacionais.

## Validar exemplos

Com Python 3.10+ e Pydantic 2.7.1 instalado, a partir da raiz do repositório:

```sh
python -m pip install pydantic==2.7.1
python -m unittest discover -s backend/tests -v
```

O teste usa apenas a biblioteca padrão e Pydantic. Ele valida ambos os exemplos e exercita rejeições. Para consumidores JSON, use `SkillCapacitySnapshot.model_validate_json(...)` e analogamente `ToolRequest`, `ForecastResult` ou `ToolResponse[InvestigationReport]`; `model_json_schema()` gera o schema JSON da classe. A validação é estrita, proíbe campos extras e rejeita NaN/infinito. A validação direta de objetos Python exige tipos Python corretos; datas e timestamps em JSON são strings ISO 8601. Esta entrega não inclui servidor ou configuração de banco.

## Convenções

- `schema_version` é obrigatória e igual a `1.0`; uma alteração incompatível exige nova versão e negociação. IDs são strings opacas não vazias, sem espaços nas extremidades; não carregam significado nem garantem unicidade global por si. `tenant_id` e `team_id` definem escopo, `data_snapshot_id` identifica uma versão imutável dos dados, `run_id` a execução, `trace_id` a correlação e `idempotency_key` uma intenção de operação. A persistência, unicidade e enforcement de idempotência são responsabilidades futuras.
- O envelope de ferramenta transporta escopo, snapshot, versões de política, horário e chave. Esses valores **não autenticam** a requisição: a identidade e as permissões devem vir do contexto autenticado e ser verificadas pelo serviço, inclusive contra empresa/equipe/snapshot. Igualdade de IDs nos schemas detecta inconsistências locais, não comprova autorização ou propriedade no banco.
- Períodos são intervalos de datas locais semiabertos `[start, end_exclusive)` em timezone IANA explícito. Timestamps devem trazer offset UTC; preservar o timezone local do período separadamente. Em Windows pode ser necessário instalar `tzdata` se o banco IANA não estiver disponível. `hours_per_period` expressa horas elegíveis no período inteiro; `cases_per_period` expressa atendimentos no intervalo de cada ponto. Horas entre skills podem se sobrepor e não devem ser somadas sem deduplicação. Frações de disponibilidade/confiança vão de 0 a 1; custos agregados por hora são em BRL. Conversão de moeda, arredondamento financeiro e qualquer outra unidade exigem acordo posterior; os números JSON não são valores monetários de precisão arbitrária.
- Campos `null` representam valor desconhecido ou não aplicável, conforme o contexto; zero representa valor conhecido igual a zero. Campos anuláveis são obrigatórios mesmo quando desconhecidos. Lista vazia indica ausência conhecida de itens no conteúdo fornecido; ela não comprova a inexistência de dados externos. Custos requerem ambos os limites e moeda, ou os três nulos. Não incluir dados individuais nem salários individuais.
- Evidências carregam IDs, escopo e snapshot; referências de hipóteses devem apontar para evidências presentes. Hipótese `supported` requer evidência; `unverified` não declara confiança ou evidência. O contrato verifica referências, não se a evidência sustenta semanticamente a hipótese. `pending` tem resposta nula; `answered` exige resposta preenchida. A ausência de dados deve produzir limitações/perguntas ou erro, não valores fabricados.
- Previsão declara método, versão, histórico, horizonte, unidade, status, backtest e limitações. `abstained` não tem pontos; `uncalibrated` pode apresentar estimativas explicitamente sem calibração; `calibrated` requer backtest. Intervalos requerem descrição de como foram produzidos; não são rotulados automaticamente como quantis. Histórico e avaliação terminam antes do horizonte, mas qualidade estatística e ausência de vazamento interno também precisam de testes do forecaster. WAPE nulo pode indicar denominador zero e deve ter explicação nas limitações.
- O envelope de resposta usa `ok` com resultado ou `error` com erro tipado, nunca ambos. Evidências e resultado com escopo devem coincidir com o envelope; `data_version` é o ID do snapshot nesta versão. `model_version` nulo significa não aplicável/desconhecido, não uma versão zero. `rule_versions` vazia não prova que não existam políticas aplicáveis. O estado `COMPLETED` só sinaliza conclusão do fluxo, não execução de contratação.

## Erros tipados

Todos incluem `code`, `message`, `retryable` e `details`; a decisão sobre retry depende da causa e contexto. Não incluir dados sensíveis na mensagem/detalhes. `INSUFFICIENT_DATA`: dados insuficientes, coletar dados ou abster-se; `UNIT_MISMATCH`: unidades incompatíveis, corrigir origem; `POLICY_REVIEW_REQUIRED`: regra ausente/conflitante, revisão humana; `FORBIDDEN_SCOPE`: acesso negado, não tentar outro escopo; `SOLVER_TIMEOUT`: tempo esgotado, não implica inviabilidade; `INFEASIBLE`: problema comprovadamente inviável sob as restrições; `INTEGRATION_UNAVAILABLE`: dependência indisponível, eventual nova tentativa. O contrato não prescreve códigos HTTP nem implementa esses tratamentos.

## Proposta de integração para revisão da Pessoa 2

Estes campos são requisitos de conversa, não schemas implementados nem uma decisão sobre seus detalhes ou persistência:

| Artefato da Pessoa 2 | Proposta mínima a acordar |
|---|---|
| `ScenarioCandidate` | Identificadores/versões de escopo e snapshot, ações, composição, premissas, custos preliminares, dependências e evidências. |
| `SimulationResult` | Escopo e versões de cenário, dados e regras; cobertura, custo, backlog, sensibilidade, premissas e status distinguindo ótimo, viável, inviável e timeout/desconhecido. |
| `CriticResult` | Escopo e versão do cenário, riscos, bloqueios, revisão solicitada, dados faltantes e referências; permitir retorno `NEEDS_DATA`. |
| `DecisionRecord` | Escopo, cenário/snapshot/regras versionados, aprovador autenticado, decisão, motivo e timestamp; sem ação administrativa automática. |

Validação por Pessoa 2, semântica definitiva dos resultados, contratos de políticas e integração real continuam pendentes. Testes de contrato futuros devem cobrir versões e propagação de evidências entre ambos os domínios.
