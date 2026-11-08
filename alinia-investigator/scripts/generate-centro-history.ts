import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildCentroHistory } from "../bot/lib/centro-history.ts";

const history = buildCentroHistory();
const target = join(dirname(fileURLToPath(import.meta.url)), "..", "fixtures", "centro-5-anos.json");
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, JSON.stringify({ synthetic: true, ...history }, null, 2));
console.log(JSON.stringify(history.quality, null, 2));
