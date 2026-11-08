/**
 * Modelo de raciocínio do turno.
 * O esforço fica em `params`, não no id.
 */
export type ReasoningModel = {
  id: string;
  params?: Array<{ id: string; value: string }>;
};

export function reasoningModel(): ReasoningModel {
  return {
    id: "grok-4.7",
    params: [
      { id: "reasoning_effort", value: "low" },
      { id: "fast", value: "true" },
    ],
  };
}
