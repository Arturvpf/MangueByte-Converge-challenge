/**
 * API do modelo de raciocínio.
 *
 * Deixe o retorno `undefined` até a API existir. Quando ela existir,
 * devolva o modelo neste formato. O esforço fica em `params`, não no id.
 *
 * return {
 *   id: "grok-4.7",
 *   params: [
 *     { id: "reasoning_effort", value: "high" },
 *     { id: "fast", value: "true" },
 *   ],
 * };
 */
export type ReasoningModel = {
  id: string;
  params?: Array<{ id: string; value: string }>;
};

export function reasoningModel(): ReasoningModel | undefined {
  return undefined;
}
