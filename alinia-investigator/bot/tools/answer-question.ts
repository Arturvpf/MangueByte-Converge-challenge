import { prompt } from "@grok/agent-sdk";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { answerQuestion, type StoredQuestion } from "../lib/questions.js";
import { safeId } from "../lib/present.js";

export default defineTool({
  description: prompt`
    Registra a resposta de uma pergunta como relato.
    Nao transforma a resposta em fato nem marca hipotese como verificada.
  `,
  effect: "idempotent",
  inputSchema: z.object({
    runId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/),
    questionId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._~-]{0,63}$/),
    answer: z.string().min(1).max(500),
  }),
  async execute({ runId, questionId, answer }, ctx) {
    const id = safeId(runId);
    if (id === undefined) return { ok: false, code: "INVALID_ID" };
    const key = `questions:${id}`;
    const current = asQuestions(await ctx.host.kv.get(key));
    const result = answerQuestion(current, questionId, answer);
    if (!result.found) return { ok: false, code: "NOT_FOUND" };
    await ctx.host.kv.put(key, result.questions);
    return { ok: true, kind: "relato", questions: result.questions };
  },
});

function asQuestions(value: unknown): StoredQuestion[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const row = typeof item === "object" && item !== null ? item as Record<string, unknown> : {};
    if (typeof row.question_id !== "string" || typeof row.text !== "string") return [];
    return [{
      question_id: row.question_id,
      text: row.text,
      status: row.status === "answered" ? "answered" as const : "pending" as const,
      answer: typeof row.answer === "string" ? row.answer : null,
      kind: row.kind === "relato" ? "relato" as const : null,
    }];
  });
}
