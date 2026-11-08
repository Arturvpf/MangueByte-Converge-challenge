import type { ApiResult } from "./alinia-api.js";
import { sanitizeValue } from "./privacy.js";

const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._~-]{0,127}$/;

export function safeId(value: string): string | undefined {
  if (!SAFE_ID.test(value) || value === "." || value === "..") return undefined;
  return value;
}

export function present(result: ApiResult) {
  if (!result.ok) return result;
  const cleaned = sanitizeValue(result.body);
  return {
    ok: true as const,
    status: result.status,
    body: cleaned.value,
    discarded: cleaned.discarded,
  };
}
