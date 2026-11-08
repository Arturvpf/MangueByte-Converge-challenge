import assert from "node:assert/strict";
import test from "node:test";
import { answerWithDeepseek } from "./deepseek-turn.js";
import { FEATHERLESS_MODEL, rewriteWithDeepseek } from "./featherless.js";

test("sem chave o deepseek nao sai da maquina", async () => {
  const result = await rewriteWithDeepseek({ facts: "Não abre vaga.", apiKey: "" });
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.code, "missing_key");
});

test("sem chave o turno nao sai da maquina", async () => {
  const result = await answerWithDeepseek("oi", "");
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.code, "missing_key");
});
test("o modelo pedido e o DeepSeek V4.1 Flash", () => {
  assert.equal(FEATHERLESS_MODEL, "deepseek-ai/DeepSeek-V4.1-Flash");
});

test("a resposta do modelo nao anuncia que esta reescrevendo", async () => {
  const { plainReply } = await import("./featherless.js");
  const text = plainReply("Aqui está o parecer reescrito.\n\nHoje, 8 de novembro de 2026, a jornada é de 42 horas.");
  assert.match(text, /^Hoje, 8 de novembro de 2026/);
  assert.equal(text.includes("reescrito"), false);
});
