export type ChatMessage = {
  role: "user" | "assistant";
  text: string;
};

export function exemplarTranscript(input: {
  message: string;
  investigation: unknown;
}): { source: "exemplo-local"; messages: ChatMessage[] } {
  const data = asRecord(input.investigation);
  const text = typeof data.fala === "string" ? data.fala : speech(data);
  return {
    source: "exemplo-local",
    messages: [
      { role: "user", text: input.message },
      { role: "assistant", text },
    ],
  };
}

export function speech(data: Record<string, unknown>): string {
  if (data.gap === 0) return coveredMonth(data);
  if (String(data.as_of).startsWith("2026-11")) return openVacancy(data);
  return gapWithoutLevel(data);
}

function gapWithoutLevel(data: Record<string, unknown>): string {
  const count = picture(data);
  const when = monthName(data.as_of);
  return [
    `Em ${when}, a jornada é de ${show(data.weekly_hours)} horas. Não é de 40 horas.`,
    "",
    `A equipe tem ${show(data.people)} pessoas. A demanda é de ${cases(count.demand)} atendimentos. A equipe cobre ${cases(count.capacity)}. Ficam ${cases(count.uncovered)} sem atendimento.`,
    "",
    `Abre vaga para ${show(data.gap)} pessoas. O nível deste mês não vem separado. Só reorganizar quem já está deixa esses atendimentos de fora.`,
    "",
    "Impacto da contratação",
    `A equipe passa de ${cases(count.people)} para ${cases(count.peopleAfter)} pessoas. A cobertura passa de ${cases(count.capacity)} para ${cases(count.after)} atendimentos. Os ${cases(count.uncovered)} entram. Sobram ${cases(count.surplus)}.`,
    "A jornada, a disponibilidade e a produtividade continuam as mesmas. Hora extra não entra.",
    "O custo não aparece nesta conta, porque o salário de cada pessoa não está nos dados.",
    "",
    internshipSentence(data.as_of, false),
    "",
    "Eu fecho essa recomendação. Eu não cadastro a vaga e não escolho o nome de ninguém.",
  ].join("\n");
}

function coveredMonth(data: Record<string, unknown>): string {
  const count = picture(data);
  return [
    `Em ${monthName(data.as_of)}, a jornada é de ${show(data.weekly_hours)} horas. Não é de 40 horas.`,
    "",
    `A equipe tem ${show(data.people)} pessoas. A demanda é de ${cases(count.demand)} atendimentos. A equipe cobre ${cases(count.capacity)}. Sobram ${cases(count.spare)}.`,
    "",
    "Não abre vaga.",
    "Início de carreira: 0. Pleno: 0. Sênior: 0.",
    "A demanda cabe em quem já está. Gente nova não cobre um buraco que não existe.",
    "",
    internshipSentence(data.as_of, false),
    "",
    "Eu fecho essa recomendação. Eu não cadastro a vaga e não escolho o nome de ninguém.",
  ].join("\n");
}

function openVacancy(data: Record<string, unknown>): string {
  const count = picture(data);
  return [
    `Hoje, ${fullDate(data.as_of)}, a jornada é de ${show(data.weekly_hours)} horas. Não é de 40 horas.`,
    "",
    count.people !== null && count.demand !== null && count.capacity !== null
      ? `A equipe tem ${cases(count.people)} pessoas. A demanda é de ${cases(count.demand)} atendimentos. A equipe cobre ${cases(count.capacity)}. Ficam ${cases(count.uncovered)} sem atendimento.`
      : `A equipe cobre ${cases(count.capacity)} atendimentos.`,
    "",
    `A recomendação é contratar ${show(data.junior_atendimento)} pessoas em início de carreira para atendimento e ${show(data.pleno_triagem)} pleno para triagem. Sênior: ${show(data.senior)}. São ${show(data.gap)} pessoas. Só reorganizar quem já está deixa a demanda sem cobertura.`,
    "",
    "Impacto da contratação",
    count.people !== null && count.peopleAfter !== null && count.after !== null
      ? `A equipe passa de ${cases(count.people)} para ${cases(count.peopleAfter)} pessoas. A cobertura passa de ${cases(count.capacity)} para ${cases(count.after)} atendimentos. Os ${cases(count.uncovered)} entram. Sobram ${cases(count.surplus)}.`
      : "A cobertura nova só entra na resposta quando a conta da contratação está completa.",
    "A jornada, a disponibilidade e a produtividade continuam as mesmas. Hora extra não entra.",
    "O custo não aparece nesta conta, porque o salário de cada pessoa não está nos dados.",
    "",
    internshipSentence(data.as_of, true),
    "",
    "Eu fecho essa recomendação. Eu não cadastro a vaga e não escolho o nome de ninguém.",
  ].join("\n");
}

function picture(data: Record<string, unknown>): {
  demand: number | null;
  capacity: number | null;
  after: number | null;
  uncovered: number | null;
  spare: number | null;
  surplus: number | null;
  people: number | null;
  peopleAfter: number | null;
} {
  const demand = whole(data.demand_cases);
  const capacity = whole(data.capacity_cases);
  const after = whole(data.if_hire_capacity);
  const people = whole(data.people);
  const gap = whole(data.gap);
  return {
    demand,
    capacity,
    after,
    uncovered: demand !== null && capacity !== null ? Math.max(demand - capacity, 0) : null,
    spare: demand !== null && capacity !== null ? Math.max(capacity - demand, 0) : null,
    surplus: demand !== null && after !== null ? Math.max(after - demand, 0) : null,
    people,
    peopleAfter: people !== null && gap !== null ? people + gap : null,
  };
}

function internshipSentence(asOf: unknown, replacesThreeHires: boolean): string {
  const text = String(asOf);
  const year = Number(text.slice(0, 4));
  const month = Number(text.slice(5, 7));
  const role = replacesThreeHires
    ? "Ele não substitui essas 3 contratações."
    : "Ele não substitui uma vaga.";
  if (!year || !month) return `O estágio não substitui a contratação.`;
  if (month < 5) return `O estágio abre em maio de ${year}, antes da demanda subir em agosto. ${role}`;
  return `O estágio deste ciclo era em maio de ${year}, antes da subida de agosto. Esse mês já passou. O próximo estágio abre em maio de ${year + 1}. ${role}`;
}

function fullDate(value: unknown): string {
  const text = String(value);
  const day = Number(text.slice(8, 10));
  const name = monthName(value);
  return Number.isInteger(day) && day > 0 ? `${day} de ${name}` : name;
}

function monthName(value: unknown): string {
  const names = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  const text = String(value);
  const month = Number(text.slice(5, 7));
  const year = text.slice(0, 4);
  const name = names[month - 1];
  return name === undefined ? text : `${name} de ${year}`;
}

function whole(value: unknown): number | null {
  return typeof value === "number" ? Math.round(value) : null;
}

function cases(value: number | null): string {
  return value === null ? "não informado" : value.toLocaleString("pt-BR");
}

function show(value: unknown): string {
  if (typeof value === "number") return value.toLocaleString("pt-BR");
  if (value === null || value === undefined || value === "") return "não informado";
  return String(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
}
