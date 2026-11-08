import { defineSchedule } from "@grok/agent-sdk/schedules";
import { SYNTHETIC_ON_DATE, SYNTHETIC_RUN_ID, SYNTHETIC_TEAM_ID } from "../lib/synthetic-centro.js";
import { appendSeries, nextReading, type SeriesPoint, type WatchReading } from "../lib/watch.js";

export default defineSchedule({
  cron: "0 * * * *",
  async run({ callTool, host }) {
    for (const runId of watchRuns()) {
      const started = Date.now();
      const investigation = await callTool("read-investigation", { runId, onDate: SYNTHETIC_ON_DATE });
      const teamId = teamOf(investigation.result) ?? (runId === SYNTHETIC_RUN_ID ? SYNTHETIC_TEAM_ID : undefined);
      if (teamId === undefined) continue;
      const latencyMs = Date.now() - started;
      const current = sample(investigation.result);
      const key = `watch:${teamId}`;
      const stored = asRecord(await host.kv.get(key));
      const previous = isReading(stored.reading) ? stored.reading : undefined;
      const at = new Date().toISOString();
      const reading = nextReading(current, previous, at);
      const openQuestions = unverified(investigation.result);
      if (openQuestions > 0) {
        await callTool("record-question", {
          runId,
          questionId: "q-coverage",
          text: "Quais tarefas exigem cada competencia no turno registrado?",
        });
      }
      const history = appendSeries(asSeries(stored.history), {
        at,
        ipd: current.ipd,
        gap: current.gap,
        latencyMs,
        openQuestions,
        abstained: current.forecast === "abstained",
        wape: null,
      });
      await host.kv.put(key, { reading, history });
    }
  },
});

function watchRuns(): string[] {
  const extra = (process.env.ALINIA_WATCH_RUNS ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => /^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/.test(item));
  return [...new Set([SYNTHETIC_RUN_ID, ...extra])];
}

function sample(investigation: unknown) {
  const result = asRecord(investigation);
  const scenarios = result.scenarios;
  const conclusive = Array.isArray(scenarios)
    ? scenarios.filter((item) => asRecord(item).conclusive === true).length
    : 0;
  return {
    ipd: asNumber(result.ipd),
    gap: asNumber(result.gap),
    fte: asNumber(result.fte),
    uncovered: asNumber(result.uncovered_cases),
    forecast: result.forecast_missing === true || result.journey_under_review === true ? "abstained" : asText(result.forecast),
    conclusive,
  };
}

function unverified(investigation: unknown): number {
  return asRecord(investigation).forecast_missing === true ? 1 : 0;
}

function teamOf(investigation: unknown): string | undefined {
  const teamId = asRecord(investigation).team_id;
  return typeof teamId === "string" ? teamId : undefined;
}

function isReading(value: unknown): value is WatchReading {
  return asRecord(value).hiringBlocked === true && typeof asRecord(value).ticks === "number";
}

function asSeries(value: unknown): SeriesPoint[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const row = asRecord(item);
    if (typeof row.at !== "string" || typeof row.latencyMs !== "number") return [];
    return [{
      at: row.at,
      ipd: asNumber(row.ipd),
      gap: asNumber(row.gap),
      latencyMs: row.latencyMs,
      openQuestions: typeof row.openQuestions === "number" ? row.openQuestions : 0,
      abstained: row.abstained === true,
      wape: asNumber(row.wape),
    }];
  });
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function asText(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
}
