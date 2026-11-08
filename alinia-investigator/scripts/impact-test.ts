import { writeFileSync } from "node:fs";
import { serve } from "@grok/agent-sdk";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { RULE_TOPICS } from "../bot/lib/rag.js";
import {
  SYNTHETIC_ON_DATE,
  SYNTHETIC_RUN_ID,
  SYNTHETIC_TEAM_ID,
  syntheticCase,
  syntheticFormula,
} from "../bot/lib/synthetic-centro.js";

const secrets = [
  "pessoa@empresa.com",
  "123.456.789-09",
  "8500.00",
  "Ignore previous",
  "reveal the token",
];

type ToolOutcome = {
  durationMs: number;
  isError: boolean;
  result: unknown;
};

const raw = syntheticCase();
const rawBytes = Buffer.byteLength(JSON.stringify(raw.run.body), "utf8");
const dir = join(dirname(fileURLToPath(import.meta.url)), "..");
const handle = await serve(dir, { mode: "single", port: 0, playground: false, dev: true });

const ruleOutcomes: Array<{ topic: string; durationMs: number; chunks: number }> = [];
let investigation: ToolOutcome | undefined;
let policies: ToolOutcome | undefined;

try {
  for (const topic of RULE_TOPICS) {
    const outcome = await handle.callTool("search-rules", { topic }) as ToolOutcome;
    const chunks = Array.isArray(asRecord(outcome.result).chunks)
      ? (asRecord(outcome.result).chunks as unknown[]).length
      : 0;
    ruleOutcomes.push({ topic, durationMs: outcome.durationMs, chunks });
  }
  investigation = await handle.callTool("read-investigation", { runId: SYNTHETIC_RUN_ID }) as ToolOutcome;
  policies = await handle.callTool("read-policies", {
    teamId: SYNTHETIC_TEAM_ID,
    onDate: SYNTHETIC_ON_DATE,
  }) as ToolOutcome;
} finally {
  await handle.close();
}

const releasedText = JSON.stringify({
  investigation: investigation?.result,
  policies: policies?.result,
});
const releasedBytes = Buffer.byteLength(JSON.stringify(asRecord(investigation?.result).run ?? null), "utf8");
const leaked = secrets.filter((secret) => releasedText.includes(secret));
const runBody = asRecord(asRecord(investigation?.result).run).body;
const metrics = asRecord(asRecord(runBody).metrics);
const forecast = asRecord(asRecord(investigation?.result).forecast).body;
const scenarioItems = asRecord(asRecord(investigation?.result).scenarios).body;
const items = Array.isArray(asRecord(scenarioItems).items) ? asRecord(scenarioItems).items as Array<Record<string, unknown>> : [];
const policyBody = asRecord(asRecord(policies?.result).body);
const hiring = asRecord(asRecord(runBody).hiring_illustration);
const discarded = new Set<string>();
for (const part of ["run", "forecast", "scenarios"] as const) {
  const list = asRecord(asRecord(investigation?.result)[part]).discarded;
  if (Array.isArray(list)) for (const item of list) if (typeof item === "string") discarded.add(item);
}

const checks = [
  ["capacidade 954.3534", metrics.capacity_cases === syntheticFormula.capacity],
  ["pessoas requeridas 14", metrics.required_people === syntheticFormula.requiredPeople],
  ["gap agregado 3", metrics.aggregate_gap === syntheticFormula.aggregateGap],
  ["quadro agregado 11 permanece", metrics.people === syntheticFormula.people],
  ["previsao abstida", asRecord(forecast).status === "abstained"],
  ["tres cenarios", items.length === 3],
  ["nenhum cenario conclusivo", items.every((item) => item.conclusive === false)],
  ["hire informa headcount 3", items.some((item) => item.kind === "hire" && item.headcount_delta === 3)],
  ["politica pede revisao", policyBody.complete === false && policyBody.outcome_reason === "review_required"],
  ["e-mail, CPF, salario e instrucao descartados", ["cpf", "email", "instrucao", "salario"].every((item) => discarded.has(item))],
  ["segredo ausente na saida", leaked.length === 0],
  ["dez temas com trecho", ruleOutcomes.every((item) => item.chunks > 0)],
  ["horas efetivas 420.42", metrics.effective_hours === syntheticFormula.effectiveHours],
  ["FTE 10.01", metrics.fte === syntheticFormula.fte],
  ["IPD acima de 1", typeof metrics.ipd === "number" && metrics.ipd > 1],
  ["contratacao agregada cobre a demanda", hiring.uncovered_cases_after === 0 && hiring.conclusive === false],
  ["custo de contratacao ausente", hiring.cost === null],
];

const passed = checks.filter((item) => item[1] === true).length;
const reduction = rawBytes === 0 ? 0 : (rawBytes - releasedBytes) / rawBytes;
const lines = [
  "Relatorio de impacto do teste real",
  "Agente: alinia-investigator",
  "Run: run-centro-sintetico",
  "Equipe: team-centro-sintetico",
  "Data das regras: 2026-11-08",
  "",
  "O teste subiu o servidor do agente e chamou as ferramentas por callTool.",
  "Os numeros vem do exemplo homogeneo do PRD: 11 x 42 x 0,91 x 2,27.",
  "O modelo de raciocinio nao participou. A metrica e o que as ferramentas entregam.",
  "",
  "1. Tempo das ferramentas",
  ...ruleOutcomes.map((item) => `- search-rules ${item.topic}: ${item.durationMs} ms, ${item.chunks} trechos`),
  `- read-investigation: ${investigation?.durationMs ?? "sem medida"} ms`,
  `- read-policies: ${policies?.durationMs ?? "sem medida"} ms`,
  "",
  "2. Privacidade",
  `- bytes do run antes do filtro: ${rawBytes}`,
  `- bytes do run depois do filtro: ${releasedBytes}`,
  `- reducao: ${(reduction * 100).toFixed(1)}%`,
  `- categorias descartadas: ${[...discarded].sort().join(", ") || "nenhuma"}`,
  `- segredos ainda visiveis: ${leaked.length === 0 ? "nenhum" : leaked.join(", ")}`,
  "",
  "3. Numeros do PRD que sobreviveram",
  `- capacidade: ${String(metrics.capacity_cases)}`,
  `- pessoas no quadro: ${String(metrics.people)}`,
  `- pessoas requeridas: ${String(metrics.required_people)}`,
  `- gap agregado: ${String(metrics.aggregate_gap)}`,
  `- previsao: ${String(asRecord(forecast).status)}`,
  `- cenarios conclusivos: ${items.filter((item) => item.conclusive === true).length} de ${items.length}`,
  `- headcount do cenario hire: ${String(items.find((item) => item.kind === "hire")?.headcount_delta)}`,
  `- politica completa: ${String(policyBody.complete)}`,
  "",
  "4. Produtividade do quadro atual",
  `- horas efetivas: ${String(metrics.effective_hours)}`,
  `- produtividade: ${String(metrics.productivity_cases_per_hour)} atendimentos por hora efetiva`,
  `- capacidade por pessoa: ${String(metrics.capacity_per_person)} atendimentos no periodo`,
  `- FTE: ${String(metrics.fte)}`,
  `- IPD, demanda projetada / capacidade: ${String(metrics.ipd)}`,
  `- demanda sem cobertura: ${String(metrics.uncovered_cases)} atendimentos`,
  "",
  "5. Contratacao agregada, nao conclusiva",
  `- pessoas a mais no cenario hire: ${String(hiring.added_people)}`,
  `- horas efetivas depois: ${String(hiring.effective_hours_after)}`,
  `- capacidade depois: ${String(hiring.capacity_cases_after)} atendimentos`,
  `- demanda sem cobertura depois: ${String(hiring.uncovered_cases_after)}`,
  `- folga de capacidade depois: ${String(hiring.surplus_cases_after)} atendimentos`,
  `- custo: ${hiring.cost === null ? "indisponivel, salario individual descartado" : String(hiring.cost)}`,
  `- conclusivo: ${String(hiring.conclusive)}`,
  "",
  "6. Cobertura das regras",
  ...ruleOutcomes.map((item) => `- ${item.topic}: ${item.chunks > 0 ? "coberto" : "sem trecho"}`),
  "",
  "7. Checagens",
  ...checks.map((item) => `- ${item[1] ? "passou" : "falhou"}: ${item[0]}`),
  "",
  `Resultado: ${passed} de ${checks.length} checagens passaram.`,
  "Nenhuma aprovacao, rejeicao ou requisicao foi executada.",
];

const reportPath = "C:\\Users\\soninho\\Desktop\\relatorio-impacto-agente-alinia.txt";
writeFileSync(reportPath, lines.join("\r\n"), "utf8");
console.log(lines.join("\n"));
if (passed !== checks.length) process.exitCode = 1;

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
}
