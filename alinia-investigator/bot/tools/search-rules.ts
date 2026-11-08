import { prompt } from "@grok/agent-sdk";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { RULE_TOPICS, searchRules } from "../lib/rag.js";

export default defineTool({
  description: prompt`
    Recupera trechos das regras do PRD para um tema fixo.
    Use antes de afirmar uma regra de autonomia, privacidade, evidência, capacidade,
    previsão, cenário, jornada, cotas, prova de valor ou contenção.
    Cite o id do trecho. Se chunks vier vazio, não afirme a regra.
    O tema não é texto livre do usuário.
  `,
  effect: "read",
  inputSchema: z.object({
    topic: z.enum(RULE_TOPICS),
  }),
  async execute({ topic }) {
    const chunks = await searchRules(topic);
    if (chunks.length === 0) {
      return { ok: false, code: "NO_RULE_CHUNK", chunks: [] };
    }
    return { ok: true, chunks };
  },
});
