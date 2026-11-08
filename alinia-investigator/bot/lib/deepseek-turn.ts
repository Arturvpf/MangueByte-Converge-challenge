import { dateFromQuestion } from "./asked-month.js";
import { buildCentroHistory, historyPoint } from "./centro-history.js";
import { compactInvestigation } from "./compact-investigation.js";
import { FEATHERLESS_MODEL, featherlessKey } from "./featherless.js";
import { SYNTHETIC_RUN_ID } from "./synthetic-centro.js";

const ENDPOINT = "https://api.featherless.ai/v1/chat/completions";

const system = [
  "Você é a Alinia. Responda a pergunta da pessoa, em português.",
  "Hoje é 8 de novembro de 2026. O mês lido nos fatos já é o mês que a pessoa pediu, inclusive quando ela diz '4 meses atrás' ou 'mês passado'.",
  "Nunca diga que a base não tem o mês lido. Diga só que falta um dado quando ele não aparece nos fatos.",
  "Se a pessoa pedir métricas, responda em lista curta, um item por linha, começando com '- '. Abra com uma frase que diga o mês.",
  "Para outras perguntas, responda em até 5 frases, só o que foi pedido.",
  "Use somente os números dos fatos. Não invente salário, nome, e-mail ou CPF. Não cadastre vaga e não escolha nome.",
  "Não use asterisco nem cabeçalho.",
].join(" ");

export async function answerWithDeepseek(message: string, apiKey?: string): Promise<
  { ok: true; text: string; model: string } | { ok: false; code: string }
> {
  const key = apiKey === undefined ? featherlessKey() : apiKey.trim();
  if (!key) return { ok: false, code: "missing_key" };
  let text = "";
  for await (const chunk of deepseekChunks(message, key)) text += chunk;
  return text ? { ok: true, text, model: process.env.FEATHERLESS_MODEL?.trim() || FEATHERLESS_MODEL } : { ok: false, code: "empty_reply" };
}

export function deepseekStream(message: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    async start(controller) {
      const key = featherlessKey();
      try {
        if (!key) {
          controller.enqueue(encoder.encode(await localReply(message)));
          return;
        }
        for await (const chunk of deepseekChunks(message, key)) controller.enqueue(encoder.encode(chunk));
      } catch {
        controller.enqueue(encoder.encode(await localReply(message)));
      } finally {
        controller.close();
      }
    },
  });
}

async function* deepseekChunks(message: string, apiKey: string): AsyncGenerator<string> {
  const facts = await investigationFacts(message);
  const model = process.env.FEATHERLESS_MODEL?.trim() || FEATHERLESS_MODEL;
  const response = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      authorization: `Bearer ${apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model,
      temperature: 0,
      max_tokens: 320,
      stream: true,
      chat_template_kwargs: { thinking: false },
      messages: [
        { role: "system", content: system },
        { role: "user", content: `Pergunta: ${message}\n\nParecer:\n${facts}` },
      ],
    }),
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok || response.body === null) {
    yield await localReply(message);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sent = false;
  while (true) {
    const step = await reader.read();
    if (step.done) break;
    buffer += decoder.decode(step.value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const payload = line.startsWith("data:") ? line.slice(5).trim() : "";
      if (!payload || payload === "[DONE]") continue;
      const delta = deltaText(payload);
      if (!delta) continue;
      sent = true;
      yield delta;
    }
  }
  if (!sent) yield await localReply(message);
}

async function localReply(message: string): Promise<string> {
  const facts = await investigationFacts(message);
  try {
    const row = JSON.parse(facts) as { fala?: unknown };
    return typeof row.fala === "string" ? row.fala : facts;
  } catch {
    return facts;
  }
}

export async function evidenceFor(message: string): Promise<string> {
  return investigationFacts(message);
}

async function investigationFacts(message: string): Promise<string> {
  const onDate = dateFromQuestion(message);
  const brief = await compactInvestigation(SYNTHETIC_RUN_ID, onDate);
  if (!brief || typeof brief !== "object" || "code" in brief) return "Sem leitura deste mês.";
  return sheet(brief as Record<string, unknown>, onDate);
}

function sheet(row: Record<string, unknown>, onDate: string): string {
  const demand = whole(row.demand_cases);
  const capacity = whole(row.capacity_cases);
  const balance = demand !== null && capacity !== null ? capacity - demand : null;
  const load = demand !== null && capacity !== null && capacity > 0 ? Math.round((demand / capacity) * 100) : null;
  const lines = [
    `Mês lido: ${monthLabel(onDate)}. ${distance(onDate)}`,
    `Pessoas: ${show(row.people)}.`,
    `Jornada semanal: ${show(row.weekly_hours)} horas.`,
    `Demanda: ${show(demand)} atendimentos.`,
    `Cobertura: ${show(capacity)} atendimentos.`,
    balance === null
      ? "Saldo: não informado."
      : balance >= 0
        ? `Sobra: ${balance} atendimentos.`
        : `Falta: ${-balance} atendimentos sem atendimento.`,
    `Uso da capacidade: ${show(load)}% (demanda dividida pela cobertura).`,
    `Pessoas que faltam para cobrir a demanda: ${show(row.gap)}.`,
  ];
  if (typeof row.junior_atendimento === "number") {
    lines.push(`Início de carreira: ${row.junior_atendimento}. Pleno: ${show(row.pleno_triagem)}. Sênior: ${show(row.senior)}.`);
  }
  if (row.gap !== 0 && typeof row.if_hire_capacity === "number") {
    lines.push(`Se entrar o número de pessoas que faltam, a cobertura vai a ${show(whole(row.if_hire_capacity))} atendimentos e a sobra fica em ${show(whole(row.if_hire_surplus))}.`);
  }
  const point = historyPoint(onDate);
  if (point) {
    lines.push(`Produtividade: ${point.productivity_cases_per_hour} atendimentos por hora.`);
    lines.push(`Disponibilidade: ${point.availability}.`);
  }
  const around = nearbyDemand(onDate);
  if (around) lines.push(`Demanda dos meses vizinhos: ${around}.`);
  return lines.join("\n");
}

function nearbyDemand(onDate: string): string {
  const key = onDate.slice(0, 7);
  const months = buildCentroHistory().months;
  const index = months.findIndex((item) => item.month === key);
  if (index < 0) return "";
  return months.slice(Math.max(0, index - 5), index + 1)
    .map((item) => `${monthLabel(`${item.month}-01`)} ${item.demand_cases}`)
    .join(", ");
}

function distance(onDate: string): string {
  const months = (2026 - Number(onDate.slice(0, 4))) * 12 + (11 - Number(onDate.slice(5, 7)));
  if (months === 0) return "É o mês de hoje.";
  if (months === 1) return "É 1 mês antes de hoje.";
  return months > 0 ? `São ${months} meses antes de hoje.` : "";
}

function show(value: unknown): string {
  return value === null || value === undefined ? "não informado" : String(value);
}

function whole(value: unknown): number | null {
  return typeof value === "number" ? Math.round(value) : null;
}

function monthLabel(value: unknown): string {
  const names = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  const text = String(value);
  const name = names[Number(text.slice(5, 7)) - 1];
  return name === undefined ? text : `${name} de ${text.slice(0, 4)}`;
}

function deltaText(payload: string): string {
  try {
    const body = JSON.parse(payload) as { choices?: Array<{ delta?: { content?: unknown } }> };
    const content = body.choices?.[0]?.delta?.content;
    return typeof content === "string" ? content : "";
  } catch {
    return "";
  }
}
