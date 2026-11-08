import { speech } from "./exemplar-brief.js";
import { historyPoint } from "./centro-history.js";
import { loadInvestigation, loadPolicies } from "./load-investigation.js";
import { mapCompetencies } from "./competency.js";
import { SYNTHETIC_ON_DATE, SYNTHETIC_RUN_ID } from "./synthetic-centro.js";

type ScenarioLine = {
  kind: string;
  headcount_delta: number | null;
  conclusive: boolean;
};

export async function compactInvestigation(runId: string, onDate: string) {
  const loaded = await loadInvestigation(runId);
  if ("code" in loaded) return loaded;
  const point = runId === SYNTHETIC_RUN_ID ? historyPoint(onDate) : undefined;
  if (point !== undefined && point.month !== "2026-11") return withSpeech(historyBrief(point, onDate));
  const runBody = asRecord(loaded.run.ok ? loaded.run.body : null);
  const teamId = typeof runBody.team_id === "string" ? runBody.team_id : "";
  const policyDate = onDate.startsWith("2026-11") ? SYNTHETIC_ON_DATE : onDate;
  const policies = teamId === "" ? undefined : await loadPolicies(teamId, policyDate);
  const metrics = asRecord(runBody.metrics);
  const forecast = asRecord(loaded.forecast.ok ? loaded.forecast.body : null);
  const policyBody = asRecord(policies && "body" in policies && policies.ok ? policies.body : null);
  const hire = asRecord(runBody.hiring_illustration);
  const period = asRecord(runBody.period);
  const runDiscarded = loaded.run.ok && "discarded" in loaded.run ? loaded.run.discarded : [];
  const policyDiscarded = policies && policies.ok && "discarded" in policies ? policies.discarded : [];
  const brief = {
    ok: true as const,
    team_id: teamId,
    people: num(metrics.people),
    period_start: text(period.start),
    period_end: text(period.end_exclusive),
    capacity_cases: num(metrics.capacity_cases),
    demand_cases: num(metrics.projected_demand_cases),
    opens_vacancy: num(metrics.aggregate_gap) !== 0,
    fte: num(metrics.fte),
    ipd: num(metrics.ipd),
    gap: num(metrics.aggregate_gap),
    uncovered_cases: num(metrics.uncovered_cases),
    required_people: num(metrics.required_people),
    forecast_missing: text(forecast.status) === "abstained",
    journey_under_review: bool(policyBody.complete) === false,
    weekly_hours: num(policyBody.weekly_max_hours),
    as_of: onDate,
    prior_demand: priorDemand(runBody.prior_demand),
    internship_open: internshipOpen(priorDemand(runBody.prior_demand)),
    junior_atendimento: num(asRecord(runBody.staffing).junior_atendimento),
    pleno_triagem: num(asRecord(runBody.staffing).pleno_triagem),
    senior: num(asRecord(runBody.staffing).senior),
    skills: mapCompetencies(loaded).map((skill) => ({
      name: skillName(skill.skill_id),
      hours: skill.eligible_hours,
      note: skill.caveat,
    })),
    if_hire_people: num(hire.added_people),
    if_hire_capacity: num(hire.capacity_cases_after),
    if_hire_uncovered: num(hire.uncovered_cases_after),
    if_hire_surplus: num(hire.surplus_cases_after),
    scenarios: scenarioLines(loaded.scenarios.ok ? loaded.scenarios.body : null),
    discarded: unique([...runDiscarded, ...policyDiscarded]),
  };
  return withSpeech(brief);
}

function historyBrief(point: NonNullable<ReturnType<typeof historyPoint>>, onDate: string) {
  const uncovered = round(Math.max(point.demand_cases - point.capacity_cases, 0), 4);
  const hiredPeople = point.people + point.gap;
  const hiredEffective = round(hiredPeople * point.nominal_hours * point.availability, 2);
  const hiredCapacity = point.gap === 0
    ? point.capacity_cases
    : round(hiredEffective * point.productivity_cases_per_hour, 4);
  const uncoveredAfter = round(Math.max(point.demand_cases - hiredCapacity, 0), 4);
  const surplusAfter = round(Math.max(hiredCapacity - point.demand_cases, 0), 4);
  return {
    ok: true as const,
    team_id: "team-centro-sintetico",
    people: point.people,
    period_start: point.month,
    period_end: point.month,
    capacity_cases: point.capacity_cases,
    demand_cases: point.demand_cases,
    opens_vacancy: point.gap > 0,
    fte: round(point.effective_hours / point.nominal_hours, 2),
    ipd: point.ipd,
    gap: point.gap,
    uncovered_cases: uncovered,
    required_people: point.required_people,
    forecast_missing: false,
    journey_under_review: false,
    weekly_hours: point.nominal_hours,
    as_of: onDate,
    prior_demand: [] as Array<{ month: string; cases: number }>,
    internship_open: null as string | null,
    junior_atendimento: point.gap === 0 ? 0 : null,
    pleno_triagem: point.gap === 0 ? 0 : null,
    senior: point.gap === 0 ? 0 : null,
    skills: [] as Array<{ name: string; hours: number; note: string }>,
    if_hire_people: point.gap === 0 ? 0 : point.gap,
    if_hire_capacity: hiredCapacity,
    if_hire_uncovered: uncoveredAfter,
    if_hire_surplus: surplusAfter,
    scenarios: [] as ScenarioLine[],
    discarded: [] as string[],
  };
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function withSpeech<T extends Record<string, unknown>>(brief: T): T & { fala: string } {
  return { ...brief, fala: speech(brief) };
}

function skillName(skillId: string): string {
  if (skillId === "skill-support") return "atendimento";
  if (skillId === "skill-triage") return "triagem";
  return skillId;
}

function priorDemand(value: unknown): Array<{ month: string; cases: number }> {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const row = asRecord(item);
    if (typeof row.month !== "string" || typeof row.cases !== "number") return [];
    return [{ month: row.month, cases: row.cases }];
  });
}

function internshipOpen(series: Array<{ month: string; cases: number }>): string | null {
  if (series.length < 3) return null;
  const base = series[0]?.cases ?? 0;
  const rise = series.find((point) => base > 0 && point.cases >= base * 1.15);
  if (rise === undefined) return null;
  const [yearText, monthText] = rise.month.split("-");
  const year = Number(yearText);
  const month = Number(monthText);
  if (!year || !month) return null;
  const date = new Date(Date.UTC(year, month - 1 - 3, 1));
  const openMonth = String(date.getUTCMonth() + 1).padStart(2, "0");
  return `${date.getUTCFullYear()}-${openMonth}`;
}

function num(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function bool(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function scenarioLines(body: unknown): ScenarioLine[] {
  const items = asRecord(body).items;
  if (!Array.isArray(items)) return [];
  return items.flatMap((item) => {
    const row = asRecord(item);
    if (typeof row.kind !== "string") return [];
    return [{
      kind: row.kind,
      headcount_delta: typeof row.headcount_delta === "number" ? row.headcount_delta : null,
      conclusive: row.conclusive === true,
    }];
  });
}

function unique(values: string[]): string[] {
  return [...new Set(values)];
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
}
