import { prompt } from "@grok/agent-sdk";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { aliniaGet } from "../lib/alinia-api.js";
import { present, safeId } from "../lib/present.js";
import { SYNTHETIC_RUN_ID, syntheticCase } from "../lib/synthetic-centro.js";

export default defineTool({
  description: prompt`
    Lê uma investigação já calculada pelo backend.
    Devolve o run, a previsão e os cenários.
    Use os números deste resultado. Não calcule headcount, custo ou cobertura.
  `,
  effect: "read",
  inputSchema: z.object({
    runId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/),
  }),
  async execute({ runId }) {
    const id = safeId(runId);
    if (id === undefined) return { ok: false, status: 0, code: "INVALID_ID" };
    if (id === SYNTHETIC_RUN_ID) {
      const fixture = syntheticCase();
      return {
        run: present(fixture.run),
        forecast: present(fixture.forecast),
        scenarios: present(fixture.scenarios),
      };
    }
    const encoded = encodeURIComponent(id);
    const [run, forecast, scenarios] = await Promise.all([
      aliniaGet(`/api/investigations/${encoded}`),
      aliniaGet(`/api/investigations/${encoded}/forecast`),
      aliniaGet(`/api/investigations/${encoded}/scenarios`),
    ]);
    return {
      run: present(run),
      forecast: present(forecast),
      scenarios: present(scenarios),
    };
  },
});
