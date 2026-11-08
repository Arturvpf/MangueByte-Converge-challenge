import { prompt } from "@grok/agent-sdk";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { aliniaGet } from "../lib/alinia-api.js";
import { present, safeId } from "../lib/present.js";
import { SYNTHETIC_ON_DATE, SYNTHETIC_TEAM_ID, syntheticCase } from "../lib/synthetic-centro.js";

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
    const id = safeId(teamId);
    if (id === undefined) return { ok: false, status: 0, code: "INVALID_ID" };
    if (id === SYNTHETIC_TEAM_ID && onDate === SYNTHETIC_ON_DATE) {
      return present(syntheticCase().policies);
    }
    const query = new URLSearchParams({ team_id: id, on_date: onDate });
    return present(await aliniaGet(`/api/policies/resolve?${query.toString()}`));
  },
});
