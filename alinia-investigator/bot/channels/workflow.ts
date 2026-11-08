import { bearerAuth, defineChannel, POST } from "@grok/agent-sdk/channels";
import * as z from "zod/v4";

const webhookToken = process.env.ALINIA_WEBHOOK_TOKEN;

export default defineChannel({
  ...(webhookToken ? { auth: [bearerAuth(webhookToken)] } : {}),
  routes: [
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
              "Chame read-investigation e read-policies.",
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
