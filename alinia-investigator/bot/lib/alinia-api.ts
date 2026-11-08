import type { ToolResultValue } from "@grok/agent-sdk";

export type ApiSuccess = {
  ok: true;
  status: number;
  body: ToolResultValue;
};

export type ApiFailure = {
  ok: false;
  status: number;
  code: string;
};

export type ApiResult = ApiSuccess | ApiFailure;

function failure(status: number, code: string): ApiFailure {
  return { ok: false, status, code };
}

function asJson(value: unknown): ToolResultValue {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(asJson);
  }
  if (typeof value === "object") {
    const out: { [key: string]: ToolResultValue } = {};
    for (const [key, item] of Object.entries(value)) {
      out[key] = asJson(item);
    }
    return out;
  }
  return null;
}

function errorCode(body: unknown, status: number): string {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return `HTTP_${status}`;
  }
  const detail = body.detail;
  if (typeof detail !== "object" || detail === null || !("code" in detail)) {
    return `HTTP_${status}`;
  }
  return typeof detail.code === "string" && detail.code.length > 0
    ? detail.code
    : `HTTP_${status}`;
}

export async function aliniaGet(path: string): Promise<ApiResult> {
  const base = process.env.ALINIA_API_BASE?.replace(/\/$/, "");
  const token = process.env.ALINIA_API_TOKEN;
  if (!base || !token) {
    return failure(0, "API_NOT_CONFIGURED");
  }

  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      headers: {
        accept: "application/json",
        authorization: `Bearer ${token}`,
      },
    });
  } catch {
    return failure(0, "API_UNAVAILABLE");
  }

  const text = await response.text();
  let body: unknown = null;
  if (text.length > 0) {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      return failure(response.status, "INVALID_RESPONSE");
    }
  }

  if (!response.ok) {
    return failure(response.status, errorCode(body, response.status));
  }
  return { ok: true, status: response.status, body: asJson(body) };
}
