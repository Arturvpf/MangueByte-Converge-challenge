import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const FEATHERLESS_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash";
const ENDPOINT = "https://api.featherless.ai/v1/chat/completions";

export function featherlessKey(env: NodeJS.ProcessEnv = process.env): string | undefined {
  const fromEnv = env.FEATHERLESS_API_KEY?.trim();
  if (fromEnv) return fromEnv;
  try {
    const path = join(dirname(fileURLToPath(import.meta.url)), "..", "..", ".env.local");
    const text = readFileSync(path, "utf8");
    for (const line of text.split(/\r?\n/)) {
      const match = line.match(/^FEATHERLESS_API_KEY=(.*)$/);
      const value = match?.[1]?.trim().replace(/^["']|["']$/g, "");
      if (value) return value;
    }
  } catch {
    return undefined;
  }
  return undefined;
}

export async function rewriteWithDeepseek(input: {
  question?: string;
  facts: string;
  apiKey?: string;
}): Promise<{ ok: true; text: string; model: string } | { ok: false; code: string }> {
  const apiKey = input.apiKey === undefined ? featherlessKey() : input.apiKey.trim();
  if (!apiKey) return { ok: false, code: "missing_key" };
  const model = process.env.FEATHERLESS_MODEL?.trim() || FEATHERLESS_MODEL;
  try {
    const response = await fetch(ENDPOINT, {
      method: "POST",
      headers: {
        authorization: `Bearer ${apiKey}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model,
        temperature: 0.2,
        max_tokens: 700,
        chat_template_kwargs: { thinking: false },
        messages: [
          {
            role: "system",
            content: [
              "Você fala com o RH. Entregue somente o parecer final.",
              "Não diga que está reescrevendo e não use markdown.",
              "Não mude nenhum número.",
              "Não invente salário, nome, e-mail ou CPF.",
              "Se o texto diz que não abre vaga, mantenha isso.",
              "Não diga que a vaga foi cadastrada nem escolha um nome.",
              "Comece pela data ou pelo mês.",
            ].join(" "),
          },
          {
            role: "user",
            content: `Pergunta: ${input.question ?? "Como está a equipe?"}\n\nParecer:\n${input.facts}`,
          },
        ],
      }),
      signal: AbortSignal.timeout(45_000),
    });
    if (!response.ok) return { ok: false, code: `upstream_${response.status}` };
    const body = await response.json() as { choices?: Array<{ message?: { content?: unknown } }> };
    const text = body.choices?.[0]?.message?.content;
    if (typeof text !== "string" || text.trim() === "") return { ok: false, code: "empty_reply" };
    return { ok: true, text: plainReply(text), model };
  } catch {
    return { ok: false, code: "unavailable" };
  }
}

export function plainReply(text: string): string {
  const lines = text.replaceAll("**", "").split(/\r?\n/);
  const start = lines.findIndex((line) => /jornada|equipe tem|não abre vaga|abre vaga/i.test(line));
  return (start > 0 ? lines.slice(start) : lines).join("\n").trim();
}
