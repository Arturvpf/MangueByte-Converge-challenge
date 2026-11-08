import { defineAgent } from "@grok/agent-sdk";
import { reasoningModel } from "./lib/reasoning-model.js";

const model = reasoningModel();

export default defineAgent({
  description:
    "Lê uma investigação já calculada e as regras vigentes, e escreve o parecer.",
  tools: [],
  ...(model === undefined ? {} : { model }),
});
