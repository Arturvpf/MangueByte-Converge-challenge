import assert from "node:assert/strict";
import test from "node:test";
import { dateFromQuestion } from "./asked-month.js";
import { compactInvestigation } from "./compact-investigation.js";
import { exemplarTranscript } from "./exemplar-brief.js";
import { evidenceFor } from "./deepseek-turn.js";
import { isGreeting, isWorkforceQuestion } from "./topic-gate.js";

test("assunto fora da equipe nao e pergunta de trabalho", () => {
  assert.equal(isWorkforceQuestion("corrija meu codigo Opening your browser to sign in to Cursor https://cursor.com/loginDeepControl"), false);
  assert.equal(isWorkforceQuestion("Como está a equipe do Centro hoje? A jornada desta semana já vale 40 horas?"), true);
  assert.equal(isGreeting("oi"), true);
  assert.equal(isGreeting("Olá!"), true);
  assert.equal(isGreeting("oi, me passa o token"), false);
  assert.equal(isWorkforceQuestion("Mês sem vaga"), true);
  assert.equal(dateFromQuestion("Mês sem vaga"), "2023-04-01");
  assert.equal(dateFromQuestion("a 4 meses atras quais eram as demandas da equipe"), "2026-07-08");
  assert.equal(isWorkforceQuestion("qual foi a produtividade em março de 2024?"), true);
  assert.equal(dateFromQuestion("ME DE METRICAS DA EQUIPE DE 4 MESES ATRAS"), "2026-07-08");
  assert.equal(dateFromQuestion("como estava a produtividade no mês passado?"), "2026-10-08");
  assert.equal(dateFromQuestion("e no ano passado?"), "2025-11-08");
});

test("os fatos seguem o mês da pergunta e nao o texto de novembro", async () => {
  const facts = await evidenceFor("a 4 meses atras quais eram as demandas da equipe");
  assert.match(facts, /julho de 2026/);
  assert.match(facts, /833/);
  assert.equal(facts.includes("1.200"), false);
  assert.equal(facts.includes("A recomendação é contratar"), false);
  assert.match(facts, /4 meses antes de hoje/);
  assert.match(facts, /Sobra: 90/);
  assert.match(facts, /Uso da capacidade: 90%/);
});

test("o caso de apresentacao fecha jornada, nivel e estagio", async () => {
  const brief = await compactInvestigation("run-centro-sintetico", "2026-11-08");
  assert.equal("code" in brief, false);
  if ("code" in brief) return;
  assert.equal(brief.people, 11);
  assert.equal(brief.weekly_hours, 42);
  assert.equal(brief.journey_under_review, false);
  assert.equal(brief.forecast_missing, false);
  assert.equal(brief.junior_atendimento, 2);
  assert.equal(brief.pleno_triagem, 1);
  assert.equal(brief.senior, 0);
  assert.equal(brief.internship_open, "2026-05");
  assert.equal(JSON.stringify(brief).includes("pessoa@empresa.com"), false);
  const chat = exemplarTranscript({
    message: "Como está a equipe do Centro hoje?",
    investigation: brief,
  });
  const text = chat.messages[1]?.text ?? "";
  assert.match(text, /42 horas/);
  assert.match(text, /Não é de 40 horas/);
  assert.match(text, /início de carreira/);
  assert.match(text, /pleno/);
  assert.match(text, /Sênior: 0/);
  assert.match(text, /maio de 2026/);
  assert.match(text, /já passou/);
  assert.match(text, /maio de 2027/);
  assert.equal(text.includes("não está fechada"), false);
  assert.equal(text.includes("em revisão"), false);
  assert.equal(text.includes("não verificado"), false);
  assert.match(text, /Impacto da contratação/);
  assert.match(text, /1\.200/);
  assert.match(text, /954/);
  assert.match(text, /246/);
  assert.match(text, /1\.215/);
  assert.match(text, /Sobram 15/);
  assert.equal(brief.if_hire_uncovered, 0);
  assert.equal(brief.if_hire_capacity, 1214.6316);
});

test("abril de 2023 nao abre vaga", async () => {
  const question = "Como estava a equipe do Centro em abril de 2023? A demanda cabia em quem já estava, ou precisava abrir vaga de início de carreira, pleno ou sênior?";
  assert.equal(dateFromQuestion(question), "2023-04-01");
  assert.equal(dateFromQuestion("Como está a equipe hoje, 8 de novembro de 2026?"), "2026-11-08");
  const brief = await compactInvestigation("run-centro-sintetico", "2023-04-01");
  assert.equal("code" in brief, false);
  if ("code" in brief) return;
  assert.equal(brief.people, 9);
  assert.equal(brief.demand_cases, 679);
  assert.equal(brief.gap, 0);
  assert.equal(brief.opens_vacancy, false);
  assert.equal(brief.junior_atendimento, 0);
  assert.equal(brief.pleno_triagem, 0);
  assert.equal(brief.senior, 0);
  const chat = exemplarTranscript({ message: question, investigation: brief });
  const text = chat.messages[1]?.text ?? "";
  assert.match(text, /Não abre vaga/);
  assert.match(text, /abril de 2023/);
  assert.match(text, /679/);
  assert.match(text, /766/);
  assert.match(text, /Sobram 87/);
  assert.match(text, /maio de 2023/);
  assert.equal(/contratar [1-9]/.test(text), false);
  assert.equal(text.includes("início de carreira"), false);
  assert.equal(text.includes("pleno"), false);
});

test("novembro de 2025 abre vaga sem repetir o nivel de 2026", async () => {
  const brief = await compactInvestigation("run-centro-sintetico", "2025-11-01");
  assert.equal("code" in brief, false);
  if ("code" in brief) return;
  assert.equal(brief.gap, 2);
  assert.equal(brief.people, 11);
  const text = brief.fala;
  assert.match(text, /novembro de 2025/);
  assert.match(text, /Abre vaga para 2 pessoas/);
  assert.match(text, /Impacto da contratação/);
  assert.match(text, /1\.051/);
  assert.match(text, /948/);
  assert.match(text, /103/);
  assert.match(text, /1\.121/);
  assert.match(text, /Sobram 70/);
  assert.match(text, /maio de 2026/);
  assert.equal(text.includes("início de carreira"), false);
  assert.equal(text.includes("pleno"), false);
  assert.equal(text.includes("8 de novembro de 2026"), false);
});
