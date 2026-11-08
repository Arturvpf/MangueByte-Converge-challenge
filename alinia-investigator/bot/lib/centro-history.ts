export type MonthPoint = {
  month: string;
  people: number;
  nominal_hours: number;
  availability: number;
  productivity_cases_per_hour: number;
  effective_hours: number;
  capacity_cases: number;
  demand_cases: number;
  required_people: number;
  gap: number;
  ipd: number;
  atendimento_hours: number;
  triagem_hours: number;
  synthetic: true;
};

export type HistoryQuality = {
  months: number;
  from: string;
  to: string;
  wape_seasonal_naive_last_12: number;
  months_with_ipd_above_1: number;
  peak_month_name: string;
  rise_month_name: string;
  internship_open_month: string;
  last_capacity_cases: number;
  last_gap: number;
};

const monthNames = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

export function buildCentroHistory(): { months: MonthPoint[]; quality: HistoryQuality } {
  const random = mulberry32(20261108);
  const months: MonthPoint[] = [];
  for (let index = 0; index < 60; index += 1) {
    const date = new Date(Date.UTC(2021, 11 + index, 1));
    const year = date.getUTCFullYear();
    const month = date.getUTCMonth() + 1;
    const yearIndex = year - 2021;
    const people = year < 2023 || (year === 2023 && month < 6) ? 9 : year < 2025 || (year === 2025 && month < 3) ? 10 : 11;
    const availability = month === 1 ? 0.86 : month === 7 ? 0.88 : 0.91;
    const productivity = index === 59 ? 2.27 : round(2.2 + yearIndex * 0.014, 3);
    const season = 1 + 0.18 * Math.cos(((month - 11) / 12) * Math.PI * 2);
    const noise = 0.97 + random() * 0.06;
    const demand = index === 59 ? 1200 : Math.round(780 * (1.03 ** yearIndex) * season * noise);
    const perPerson = 42 * availability * productivity;
    const capacity = index === 59 ? 954.3534 : round(people * perPerson, 4);
    const required = Math.ceil(demand / perPerson);
    months.push({
      month: `${year}-${String(month).padStart(2, "0")}`,
      people: index === 59 ? 11 : people,
      nominal_hours: 42,
      availability: index === 59 ? 0.91 : availability,
      productivity_cases_per_hour: productivity,
      effective_hours: index === 59 ? 420.42 : round(people * 42 * availability, 2),
      capacity_cases: capacity,
      demand_cases: demand,
      required_people: index === 59 ? 14 : required,
      gap: index === 59 ? 3 : Math.max(required - people, 0),
      ipd: round(demand / capacity, 4),
      atendimento_hours: Math.round(people * 42 * 0.62),
      triagem_hours: Math.round(people * 42 * 0.38),
      synthetic: true,
    });
  }
  const lastTwelve = months.slice(-12);
  const errors = lastTwelve.map((point) => {
    const prior = months.find((item) => item.month === shiftYear(point.month, -1));
    return { actual: point.demand_cases, forecast: prior?.demand_cases ?? point.demand_cases };
  });
  const wape = errors.reduce((sum, item) => sum + Math.abs(item.actual - item.forecast), 0)
    / errors.reduce((sum, item) => sum + item.actual, 0);
  const byCalendar = averageByMonth(months);
  const peak = byCalendar.reduce((best, item) => item.cases > best.cases ? item : best);
  const trough = byCalendar.reduce((best, item) => item.cases < best.cases ? item : best);
  const midpoint = trough.cases + (peak.cases - trough.cases) * 0.35;
  let rise = peak;
  for (let step = 1; step <= 12; step += 1) {
    const monthNumber = ((trough.monthNumber - 1 + step) % 12) + 1;
    const point = byCalendar.find((item) => item.monthNumber === monthNumber)!;
    if (point.cases >= midpoint) {
      rise = point;
      break;
    }
  }
  const open = addMonths(rise.monthNumber, -3);
  return {
    months,
    quality: {
      months: months.length,
      from: months[0]!.month,
      to: months[59]!.month,
      wape_seasonal_naive_last_12: round(wape, 4),
      months_with_ipd_above_1: months.filter((item) => item.ipd > 1).length,
      peak_month_name: monthNames[peak.monthNumber - 1]!,
      rise_month_name: monthNames[rise.monthNumber - 1]!,
      internship_open_month: monthNames[open - 1] ?? monthNames[(open + 11) % 12]!,
      last_capacity_cases: months[59]!.capacity_cases,
      last_gap: months[59]!.gap,
    },
  };
}

export function historyPoint(onDate: string): MonthPoint | undefined {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(onDate)) return undefined;
  return buildCentroHistory().months.find((item) => item.month === onDate.slice(0, 7));
}

function averageByMonth(months: MonthPoint[]): Array<{ monthNumber: number; cases: number }> {
  return monthNames.map((_, index) => {
    const monthNumber = index + 1;
    const sample = months.filter((item) => Number(item.month.slice(5, 7)) === monthNumber);
    const cases = sample.reduce((sum, item) => sum + item.demand_cases, 0) / sample.length;
    return { monthNumber, cases };
  });
}

function addMonths(month: number, delta: number): number {
  const shifted = ((month - 1 + delta) % 12 + 12) % 12;
  return shifted + 1;
}

function shiftYear(month: string, delta: number): string {
  const year = Number(month.slice(0, 4)) + delta;
  return `${year}${month.slice(4)}`;
}

function mulberry32(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
