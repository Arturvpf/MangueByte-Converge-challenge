import { serve } from "@grok/agent-sdk";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = join(dirname(fileURLToPath(import.meta.url)), "..");
const handle = await serve(dir, { mode: "single", port: 0, playground: false, dev: true });

try {
  const rules = await handle.callTool("search-rules", { topic: "privacidade" });
  const investigation = await handle.callTool("read-investigation", { runId: "run-demo" });
  console.log(JSON.stringify({ rules, investigation }, null, 2));
} finally {
  await handle.close();
}
