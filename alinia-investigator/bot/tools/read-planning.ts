import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";
import { aliniaGet } from "../lib/alinia-api.js";

const nullable = z.number().nullable();
const forecastPoint = z.object({
  starts: z.iso.date(),
  estimate: nullable,
  p10: nullable,
  p50: nullable,
  p90: nullable,
});
const summary = z.object({
  source_kind: z.enum(["csv", "manual", "jira", "synthetic"]).nullable(),
  forecast_status: z.enum(["calibrated", "uncalibrated", "abstained"]),
  usable_for_planning: z.boolean(),
  points: z.array(forecastPoint).max(12),
  scenarios: z.array(z.object({
    kind: z.enum(["hire", "temporary", "reallocate", "redesign", "do_nothing"]),
    version: z.number().int().positive(),
    solver_status: z.enum(["optimal", "feasible", "infeasible", "unknown", "blocked"]),
    residual_hours: nullable,
    hours_saved_vs_baseline: nullable,
    implementation_days: nullable,
    cost_min_brl: nullable,
    cost_max_brl: nullable,
    cost_status: z.enum(["known_baseline", "assumed", "unavailable"]),
    backlog_end: nullable,
    sla_fraction: nullable,
    approval_ready: z.literal(false),
  })).max(5),
});

export async function readPlanning(runId: string) {
  const result = await aliniaGet(`/api/investigations/${encodeURIComponent(runId)}/planning-summary`);
  if (!result.ok) return result;
  const parsed = summary.safeParse(result.body);
  if (!parsed.success) return { ok: false as const, code: "INVALID_PLANNING_RESULT" };
  return { ok: true as const, ...parsed.data };
}

export function canReadOperationalPlanning(channelId: string, authenticator: string | undefined) {
  return channelId === "workflow" && authenticator === "bearer" && Boolean(process.env.ALINIA_WEBHOOK_TOKEN);
}

export default defineTool({
  description: "Lê previsão e cenários A–E calculados para uma investigação autorizada. Use as métricas como fornecidas. Campos nulos são indisponíveis.",
  effect: "read",
  inputSchema: z.object({ runId: z.uuid() }),
  async execute({ runId }, ctx) {
    // Built-in session/tool routes also exist outside the protected workflow
    // channel. A session from the public demo must not use server credentials.
    if (!canReadOperationalPlanning(ctx.session.channelId, ctx.session.auth?.authenticator)) {
      return { ok: false as const, code: "AUTHENTICATED_WORKFLOW_REQUIRED" };
    }
    return readPlanning(runId);
  },
});
