import { prompt } from "@grok/agent-sdk";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { mapCompetencies } from "../lib/competency.js";
import { loadInvestigation } from "../lib/load-investigation.js";

export default defineTool({
  description: prompt`
    Mapeia competencias do run com horas elegiveis, evidencia e ressalva.
    Nao devolve nota, salario nem pessoa.
  `,
  effect: "read",
  inputSchema: z.object({
    runId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/),
  }),
  async execute({ runId }) {
    const investigation = await loadInvestigation(runId);
    if ("code" in investigation) return investigation;
    return { ok: true, competencies: mapCompetencies(investigation) };
  },
});
