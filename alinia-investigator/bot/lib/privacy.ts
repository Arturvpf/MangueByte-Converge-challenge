import type { ToolResultValue } from "@grok/agent-sdk";

const SENSITIVE_KEYS = new Set([
  "email", "e-mail", "cpf", "rg", "phone", "telefone", "celular",
  "salario", "salary", "wage", "remuneracao", "saude", "health", "cid",
  "diagnostico", "sindicato", "union", "afastamento", "atestado", "prompt",
  "senha", "password", "token", "authorization", "nascimento", "birthdate",
  "birth", "endereco", "address", "cns", "pis", "nit", "biometria",
  "religiao", "raca", "genero",   "employees", "persons", "individuals", "trabalhadores",
  "nome_completo", "full_name", "person_name",
]);

const EMAIL = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/gi;
const CPF = /\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b/g;
const INSTRUCTION =
  /ignore (?:all |any |previous |prior )?instructions|desconsidere (?:as |todas as )?instruc(?:oes|ões)|you are now|voce agora e|system prompt|reveal the token|revele o token/gi;

export type Sanitized = {
  value: ToolResultValue;
  discarded: string[];
};

export function sanitizeValue(value: ToolResultValue): Sanitized {
  const discarded = new Set<string>();
  const cleaned = walk(value, discarded);
  return {
    value: cleaned === undefined ? null : cleaned,
    discarded: [...discarded].sort(),
  };
}

export function quarantine(text: string): { text: string; instruction: boolean } {
  const withoutControls = text.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
  const instruction = INSTRUCTION.test(withoutControls);
  INSTRUCTION.lastIndex = 0;
  const neutered = withoutControls.replace(INSTRUCTION, "[instrucao descartada]");
  return { text: neutered.slice(0, 800), instruction };
}

function walk(
  value: ToolResultValue,
  discarded: Set<string>,
  key?: string,
): ToolResultValue | undefined {
  if (key !== undefined && SENSITIVE_KEYS.has(fold(key))) {
    discarded.add(fold(key));
    return undefined;
  }
  if (typeof value === "string") return scrubString(value, discarded);
  if (Array.isArray(value)) {
    return value.flatMap((item) => {
      const next = walk(item, discarded);
      return next === undefined ? [] : [next];
    });
  }
  if (typeof value === "object" && value !== null) {
    const out: { [key: string]: ToolResultValue } = {};
    for (const [childKey, child] of Object.entries(value)) {
      const next = walk(child, discarded, childKey);
      if (next !== undefined) out[childKey] = next;
    }
    return out;
  }
  return value;
}

function scrubString(value: string, discarded: Set<string>): string | undefined {
  let text = value;
  if (EMAIL.test(text)) {
    discarded.add("email");
    text = text.replace(EMAIL, "");
  }
  EMAIL.lastIndex = 0;
  if (CPF.test(text)) {
    discarded.add("cpf");
    text = text.replace(CPF, "");
  }
  CPF.lastIndex = 0;
  const held = quarantine(text);
  if (held.instruction) discarded.add("instrucao");
  const trimmed = held.text.trim();
  if (trimmed.length === 0) return undefined;
  return trimmed;
}

function fold(value: string): string {
  return value.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}
