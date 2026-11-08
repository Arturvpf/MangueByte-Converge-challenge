# P1-04 — Metrics Engine (parcial)

Núcleo puro e determinístico em `app/metrics/engine.py`; não implementa a entrega completa. COM-02, P1-01 e P2-01 ainda não estão disponíveis. Persistência de resultados, versão e evidências, API por snapshot, autenticação e integração real continuam pendentes. A matriz é uma proposta interna para revisão com P2, não um contrato de solver aprovado; P2-04 não está implementado. A comparação de escopo dos objetos detecta inconsistências, não verifica autorização nem propriedade do snapshot.

## Métricas homogêneas

`homogeneous_metrics` exige número inteiro de pessoas, horas nominais por pessoa no período, fração de disponibilidade [0,1], produtividade em atendimentos por hora efetiva e demanda atual em atendimentos no mesmo período. `projected_demand_cases` informa demanda projetada para dimensionamento; quando omitida, usa a demanda atual explicitamente como premissa; `None` é rejeitado. Unidades aceitas explicitamente são `hours_per_period`, `cases_per_period` e `cases_per_hour`; o chamador deve assegurar que os períodos correspondem. Valores são convertidos para Decimal através de sua representação decimal; para exatidão na origem prefira `Decimal` ou strings decimais. Multiplicações, somas e teto usam aritmética racional exata, independente do contexto Decimal externo. Razões são arredondadas para 50 algarismos significativos, half-even, em contexto próprio; não use essas razões arredondadas para decisões de teto ou limites. Definições assumidas, sujeitas a validação de domínio:

- horas efetivas = pessoas × horas nominais × disponibilidade + horas extras efetivas informadas; capacidade = horas efetivas × produtividade;
- disponibilidade efetiva informada é fração da jornada nominal básica, sem incluir horas extras; se a jornada básica total é zero, ela é indefinida (`None`);
- IPD = demanda atual / capacidade, índice de pressão da demanda; capacidade zero torna IPD indefinido, inclusive se a demanda é zero;
- FTE = horas efetivas totais / jornada nominal individual; FTE de horas extras = horas extras efetivas / jornada nominal individual. Jornada zero torna ambos indefinidos;
- pessoas requeridas = teto(demanda projetada / capacidade básica por pessoa); gap = máximo(requeridas − pessoas atuais, 0). Horas extras existentes não são extrapoladas para futuras pessoas. Se a capacidade básica por pessoa é zero e demanda projetada positiva, ambos são indefinidos; com demanda projetada zero, requeridas = 0 e gap = 0.

A entrada de horas extras já deve estar após descontos de disponibilidade; não a multiplique novamente. O resultado é agregado e homogêneo, sem inferência de cargo ou vaga. Valores ausentes, não finitos, negativos ou frações inválidas geram `MetricsError(INSUFFICIENT_DATA)`; unidades incompatíveis geram `UNIT_MISMATCH`. A igualdade `11 × 42 × 0,91 × 2,27 = 954,3534` com demanda 1.200 produz 14 pessoas requeridas e gap 3.

## Matriz de skill/turno

`prepare_matrix` recebe `SkillCapacitySnapshot` e `DemandSnapshot` COM-01, revalida os objetos e exige escopo, snapshot e período idênticos. A demanda permanece por skill, sem distribuir entre turnos; falta de skill na demanda não significa demanda zero. Preserva listas de pools por linha, os limites efetivos, custos ficam no snapshot original, os metadados de disponibilidade e as limitações. Não soma tetos entre skills nem reaplica disponibilidade às horas COM-01, já efetivas. Nulos permanecem desconhecidos. O solver deverá receber também custos e regras aprovadas pela integração futura; esta matriz isolada não permite otimização completa nem representa elegibilidade parcial dentro de um pool.

`validate_allocations` verifica alocações propostas externamente por pool/skill/turno: elegibilidade, duplicidade, não negatividade, soma por pool e por linha. Qualquer alocação que use limite desconhecido é rejeitada, inclusive zero; um conjunto vazio apenas não viola os limites, não prova cobertura ou viabilidade. Não verifica políticas, demanda atendida, custos, existência de solução, nem homogeneidade ou não sobreposição dos pools de origem. Erros de validação estrutural COM-01 permanecem `pydantic.ValidationError`; erros operacionais são `MetricsError` com código COM-01. A adoção do formato por P2 exige revisão cruzada e teste de integração.

Executar na raiz: `python -m unittest discover -s backend/tests -v` (Python 3.10+ e Pydantic 2.7.1).
