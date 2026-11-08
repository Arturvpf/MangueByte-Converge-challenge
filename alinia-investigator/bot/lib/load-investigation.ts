import { aliniaGet } from "./alinia-api.js";
import { present, safeId } from "./present.js";
import { SYNTHETIC_ON_DATE, SYNTHETIC_RUN_ID, SYNTHETIC_TEAM_ID, syntheticCase } from "./synthetic-centro.js";

export async function loadInvestigation(runId: string): Promise<
  | { ok: false; status: number; code: string }
  | { run: ReturnType<typeof present>; forecast: ReturnType<typeof present>; scenarios: ReturnType<typeof present> }
> {
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
  return { run: present(run), forecast: present(forecast), scenarios: present(scenarios) };
}

export type LoadedPolicies = ReturnType<typeof present> | { ok: false; status: number; code: string };

export async function loadPolicies(teamId: string, onDate: string): Promise<LoadedPolicies> {
  const id = safeId(teamId);
  if (id === undefined) return { ok: false, status: 0, code: "INVALID_ID" };
  if (!/^\d{4}-\d{2}-\d{2}$/.test(onDate)) return { ok: false, status: 0, code: "INVALID_DATE" };
  if (id === SYNTHETIC_TEAM_ID && onDate === SYNTHETIC_ON_DATE) return present(syntheticCase().policies);
  const query = new URLSearchParams({ team_id: id, on_date: onDate });
  return present(await aliniaGet(`/api/policies/resolve?${query.toString()}`));
}
