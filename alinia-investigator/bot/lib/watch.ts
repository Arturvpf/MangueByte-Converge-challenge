export type WatchSample = {
  ipd: number | null;
  gap: number | null;
  fte: number | null;
  uncovered: number | null;
  forecast: string | null;
  conclusive: number;
};

export type WatchReading = WatchSample & {
  at: string;
  ticks: number;
  ipdAboveOneTicks: number;
  sameGapTicks: number;
  forecastAbstainedTicks: number;
  hiringBlocked: true;
  reason: string;
};

export type SeriesPoint = {
  at: string;
  ipd: number | null;
  gap: number | null;
  latencyMs: number;
  openQuestions: number;
  abstained: boolean;
  wape: number | null;
};

export function appendSeries(previous: SeriesPoint[] | undefined, point: SeriesPoint): SeriesPoint[] {
  return [...(previous ?? []), point].slice(-24);
}

export function nextReading(
  current: WatchSample,
  previous: WatchReading | undefined,
  at: string,
): WatchReading {
  const ipdAboveOne = current.ipd !== null && current.ipd > 1;
  const sameGap = previous !== undefined && previous.gap === current.gap;
  const abstained = current.forecast === "abstained";
  const ipdAboveOneTicks = ipdAboveOne ? (previous?.ipdAboveOneTicks ?? 0) + 1 : 0;
  const sameGapTicks = sameGap ? previous.sameGapTicks + 1 : 1;
  const forecastAbstainedTicks = abstained ? (previous?.forecastAbstainedTicks ?? 0) + 1 : 0;
  return {
    ...current,
    at,
    ticks: (previous?.ticks ?? 0) + 1,
    ipdAboveOneTicks,
    sameGapTicks,
    forecastAbstainedTicks,
    hiringBlocked: true,
    reason: reasonFor(ipdAboveOneTicks, forecastAbstainedTicks, current.conclusive),
  };
}

function reasonFor(ipdTicks: number, abstainedTicks: number, conclusive: number): string {
  if (abstainedTicks > 0) return "previsao abstida; gap persistente nao autoriza contratacao";
  if (conclusive === 0) return "nenhum cenario conclusivo";
  if (ipdTicks < 2) return "um unico intervalo acima de 1 nao basta";
  return "persistencia registrada; a decisao continua humana";
}
