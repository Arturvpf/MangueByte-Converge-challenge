import { prompt } from "@grok/agent-sdk";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { SYNTHETIC_TEAM_ID } from "../lib/synthetic-centro.js";
import { loadPolicies } from "../lib/load-investigation.js";

export default defineTool({
  description: prompt`
    Lê as regras vigentes de uma equipe em uma data.
    A data vem do pedido. Não invente a data nem a equipe.
    Se o resultado pedir revisão, diga isso no parecer.
  `,
  effect: "read",
  inputSchema: z.object({
    teamId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/),
    onDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  }),
  async execute({ teamId, onDate }) {
    if (teamId !== SYNTHETIC_TEAM_ID) return { ok: false as const, code: "USE_READ_PLANNING" };
    return loadPolicies(teamId, onDate);
  },
});
