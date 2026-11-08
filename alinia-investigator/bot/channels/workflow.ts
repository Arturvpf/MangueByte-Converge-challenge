import { bearerAuth, defineChannel, GET, POST } from "@grok/agent-sdk/channels";
import * as z from "zod/v4";
import { deepseekStream } from "../lib/deepseek-turn.js";
import { isGreeting, isWorkforceQuestion, introReply, offTopicReply } from "../lib/topic-gate.js";
import { SYNTHETIC_ON_DATE, SYNTHETIC_RUN_ID } from "../lib/synthetic-centro.js";

const webhookToken = process.env.ALINIA_WEBHOOK_TOKEN;
const page = `<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <title>Alinia · chat de exemplo</title>
  <style>
    body { font-family: Georgia, serif; margin: 0; background: #f4f1ea; color: #1c1915; }
    main { max-width: 40rem; margin: 0 auto; padding: 2rem 1rem 4rem; }
    h1 { font-size: 1.4rem; }
    p.note { color: #5c564c; }
    form { display: flex; gap: 0.5rem; }
    input { flex: 1; padding: 0.7rem; border: 1px solid #cfc6b8; background: white; }
    button { padding: 0.7rem 1rem; background: #1c1915; color: #f4f1ea; border: 0; }
    article { margin-top: 1rem; padding: 0.9rem 1rem; background: white; white-space: pre-wrap; }
    article.user { background: #e7e1d6; }
  </style>
</head>
<body>
  <main>
    <h1>Chat de exemplo</h1>
    <p class="note">Esta conversa é o DeepSeek V4.1 Flash, da Featherless, do cumprimento ao parecer.</p>
    <form>
      <input name="message" value="Como está a equipe do Centro neste mês? Precisamos de mais gente ou dá para reorganizar quem já está?" />
      <button type="submit">Enviar</button>
    </form>
    <div id="log"></div>
  </main>
  <script>
    const form = document.querySelector("form");
    const log = document.querySelector("#log");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = new FormData(form).get("message");
      const user = document.createElement("article");
      user.className = "user";
      user.textContent = message;
      const node = document.createElement("article");
      log.replaceChildren(user, node);
      const response = await fetch(location.pathname, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "text/plain" },
        body: JSON.stringify({ message })
      });
      const type = response.headers.get("content-type") || "";
      if (type.includes("application/json")) {
        const data = await response.json();
        const messages = data.messages || [];
        node.textContent = (messages[1] || messages[0] || {}).text || "";
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const step = await reader.read();
        if (step.done) break;
        node.textContent += decoder.decode(step.value, { stream: true });
      }
    });
  </script>
</body>
</html>`;

export default defineChannel({
  ...(webhookToken ? { auth: [bearerAuth(webhookToken)] } : {}),
  routes: [
    GET("/chat", {
      description: "Abre o chat de exemplo.",
      querySchema: z.object({}),
      handler: async () => new Response(page, { headers: { "content-type": "text/html; charset=utf-8" } }),
    }),
    POST("/chat", {
      description: "Monta o parecer de exemplo com as ferramentas.",
      bodySchema: z.object({
        run_id: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/).default(SYNTHETIC_RUN_ID),
        on_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).default(SYNTHETIC_ON_DATE),
        message: z.string().min(1).max(500).default("Qual e o parecer?"),
      }),
      handler: async (_request, { body }) => {
        if (isGreeting(body.message)) {
          return Response.json({
            source: "apresentacao",
            messages: [{ role: "assistant", text: introReply }],
          });
        }
        if (!isWorkforceQuestion(body.message)) {
          return Response.json({
            source: "recusa",
            messages: [{ role: "assistant", text: offTopicReply }],
          });
        }
        return new Response(deepseekStream(body.message), {
          headers: { "content-type": "text/plain; charset=utf-8" },
        });
      },
    }),
    POST("/investigate", {
      description: "Pede o parecer de uma investigação já calculada.",
      bodySchema: z.object({
        run_id: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/),
        on_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
      }),
      handler: async (_request, { send, waitUntil, body }) => {
        waitUntil(
          send(
            [
              `Escreva o parecer da investigação ${body.run_id}.`,
              `A data das regras é ${body.on_date}.`,
              "Chame read-investigation, read-policies e map-competencies.",
              "Siga a skill investigation-brief.",
            ].join(" "),
            {
              continuationToken: `run:${body.run_id}`,
              title: `Investigação ${body.run_id}`,
            },
          ),
        );
        return new Response(null, { status: 202 });
      },
    }),
  ],
});

function teamOf(investigation: unknown): string | undefined {
  const body = typeof investigation === "object" && investigation !== null && "run" in investigation
    ? (investigation as { run?: { body?: { team_id?: unknown } } }).run?.body
    : undefined;
  return typeof body?.team_id === "string" ? body.team_id : undefined;
}
