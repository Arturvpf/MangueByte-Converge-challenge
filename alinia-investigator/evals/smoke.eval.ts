import { defineEval } from "@grok/agent-sdk/evals";

export default defineEval({
  tags: ["smoke"],
  description: "O parecer começa pela leitura da investigação.",
  async test(t) {
    await t.send(
      "Escreva o parecer da investigação run-demo. A data das regras é 2026-11-08.",
    );
    t.succeeded();
    t.calledTool("read-investigation");
    t.calledTool("search-rules");
  },
});
