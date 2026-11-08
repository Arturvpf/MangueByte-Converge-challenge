export type CompetencyRow = {
  skill_id: string;
  eligible_hours: number | null;
  evidence_ids: string[];
  caveat: string;
};

export function mapCompetencies(value: unknown): CompetencyRow[] {
  const rows = asRecord(asRecord(asRecord(value).run).body).competencies;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row) => {
    const item = asRecord(row);
    if (typeof item.skill_id !== "string") return [];
    if ("person_id" in item || "score" in item || "salary" in item) return [];
    return [{
      skill_id: item.skill_id,
      eligible_hours: typeof item.eligible_hours === "number" ? item.eligible_hours : null,
      evidence_ids: Array.isArray(item.evidence_ids)
        ? item.evidence_ids.filter((id): id is string => typeof id === "string")
        : [],
      caveat: typeof item.caveat === "string" ? item.caveat : "sem ressalva registrada",
    }];
  });
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : {};
}
