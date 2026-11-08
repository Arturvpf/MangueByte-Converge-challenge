import assert from "node:assert/strict";
import test from "node:test";
import { buildCentroHistory } from "./centro-history.js";

test("cinco anos sinteticos fecham no exemplo do PRD e medem o erro", () => {
  const history = buildCentroHistory();
  assert.equal(history.months.length, 60);
  assert.equal(history.months[0]?.month, "2021-12");
  assert.equal(history.months[59]?.month, "2026-11");
  assert.equal(history.months[59]?.capacity_cases, 954.3534);
  assert.equal(history.months[59]?.people, 11);
  assert.equal(history.months[59]?.gap, 3);
  assert.equal(history.quality.wape_seasonal_naive_last_12 > 0, true);
  assert.equal(history.quality.wape_seasonal_naive_last_12 < 0.5, true);
  assert.equal(JSON.stringify(history).includes("@"), false);
  assert.equal(JSON.stringify(history).includes("cpf"), false);
});
