/**
 * Ficha do site para o agente (alinia-investigator).
 *
 * É o que as telas da simulação mostram da Unidade Centro. O proxy de
 * scripts/serve.mjs anexa esta ficha a cada /agent/chat, e o agente responde
 * só a partir dela, em vez do caso sintético próprio dele (outros números,
 * meses gerados e composição por nível que o site não tem).
 *
 * Fica no servidor, não no navegador, para que ninguém consiga mandar ao
 * modelo uma ficha alterada.
 *
 * Se mudar um número nas telas, mude aqui também:
 * - src/app/index.html (Visão geral, Investigação, Previsão, Revisão);
 * - src/app/app.js (`evidence`, gráfico da Visão geral e `forecastData`);
 * - src/app/agent.js (`DEMO`).
 */

export const SITE_CONTEXT = [
  'Plataforma Alinia, modo simulação. Os dados são o exemplo de demonstração da Unidade Centro, não um recorte real.',
  'Equipe: Unidade Centro, atendimento, 11 pessoas. Período: novembro de 2026.',
  'Fonte: arquivo demanda_centro.csv, janela das últimas 4 semanas. Unidade: atendimentos comparáveis por semana.',
  '',
  'Visão geral',
  '- Demanda nas últimas 4 semanas: 1.060, 1.085, 1.120 e 1.150 atendimentos por semana.',
  '- Demanda atual: 1.150 atendimentos por semana.',
  '- Capacidade: cerca de 954 atendimentos por semana (11 pessoas × 42h × 91% de disponibilidade × 2,27 atendimentos por hora).',
  '- Pressão de demanda (demanda dividida pela capacidade): 1,21, ou seja, a demanda está 21% acima da capacidade.',
  '- Gap agregado: 3 posições para cobrir a demanda em 42h. É uma conta agregada: não diz quais competências, turnos, cargos ou níveis faltam.',
  '',
  'Investigação (etapa 2 de 5, em andamento)',
  '- Hipótese 1: demanda acima da capacidade agregada. Sustentada pelo cálculo.',
  '- Hipótese 2: cobertura desigual por competência e turno. Não verificada; falta a matriz de horas por competência, turno e função.',
  '- Hipótese 3: pico sazonal de dezembro. Não verificada; falta histórico comparável para separar pico passageiro de déficit estrutural.',
  '- Pergunta ao gestor, resposta pendente: há tarefas que exigem supervisão N1 no turno da tarde?',
  '',
  'Previsão das próximas 4 semanas (mediana móvel sobre um histórico curto)',
  '- Faixa provável: 1.165, 1.180, 1.195 e 1.200 atendimentos nas semanas 1 a 4.',
  '- Faixa baixa: 1.050 a 1.080. Faixa alta: 1.265 a 1.320. A faixa ilustrativa vai de 1.080 a 1.320.',
  '- Na semana 4, a faixa provável fica 246 atendimentos acima da capacidade. Com 1.200 atendimentos, o cálculo agregado em 42h equivale a cerca de 14 pessoas no total (hoje são 11).',
  '- O histórico é curto: não separa um pico sazonal de um déficit estrutural.',
  '',
  'Cenários (nenhum é recomendação e nenhum passou pela validação independente)',
  '- A, Contratar: condicional. Risco: prazo de chegada, mentoria e cobertura N1.',
  '- B, Temporários: exploratório. Risco: modalidade, custo e prazo.',
  '- C, Realocar ou capacitar: condicional. Risco: impacto na equipe de origem.',
  '- D, Redesenhar turnos: exploratório. Risco: repousos e cobertura obrigatória.',
  '- E, Não agir: referência. Risco: backlog e pressão operacional.',
  '- Aprovar exige cenário conclusivo e validação independente de cobertura obrigatória, habilitação e regras aplicáveis. A decisão é do RH, na tela Revisão.',
  '',
  'Regras',
  '- Jornada de 42 horas semanais, usada só como premissa de simulação. Categoria, vigência e instrumento coletivo precisam ser confirmados com RH e jurídico.',
  '',
  'O que o site não tem: meses ou anos anteriores às 4 semanas, composição por cargo, nível ou competência, nomes, salários, custos, prazos de recrutamento e dados de outras equipes.',
].join('\n');
