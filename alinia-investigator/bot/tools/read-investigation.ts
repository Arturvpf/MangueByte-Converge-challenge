import { prompt } from "@grok/agent-sdk";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { dateFromQuestion } from "../lib/asked-month.js";
import { compactInvestigation } from "../lib/compact-investigation.js";

export default defineTool({
  description: prompt`
    Lê o mês citado na frase.
    Passe a frase inteira em question.
    onDate é o dia 1 desse mês. Sem mês na frase, use 2026-11-08.
    Uma chamada basta.
    A resposta ao usuário é somente o campo fala.
  `,
  effect: "read",
  inputSchema: z.object({
    runId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/),
    onDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    question: z.string().min(1).max(500).optional(),
  }),
  async execute({ runId, onDate, question }) {
    return compactInvestigation(runId, question === undefined ? onDate : dateFromQuestion(question));
  },
});
