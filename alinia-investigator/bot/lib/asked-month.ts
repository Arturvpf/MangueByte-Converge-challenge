import { SYNTHETIC_ON_DATE } from "./synthetic-centro.js";

const monthNames = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

export function dateFromQuestion(message: string): string {
  const iso = message.match(/\b(20\d{2}-\d{2}-\d{2})\b/);
  if (iso?.[1] !== undefined) return iso[1];
  const plain = message.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  const named = plain.match(/\b(?:(\d{1,2}) de )?(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro) de (20\d{2})\b/);
  if (named?.[2] !== undefined && named[3] !== undefined) {
    const month = monthNames.indexOf(named[2]) + 1;
    const day = named[1] === undefined ? 1 : Number(named[1]);
    const safeDay = day >= 1 && day <= 31 ? day : 1;
    return `${named[3]}-${String(month).padStart(2, "0")}-${String(safeDay).padStart(2, "0")}`;
  }
  const ago = plain.match(/\b(\d{1,2})\s+mes(?:es)?\s+atras\b/);
  if (ago?.[1] !== undefined) return shiftMonths(SYNTHETIC_ON_DATE, -Number(ago[1]));
  if (/\b(mes passado|ultimo mes|mes anterior)\b/.test(plain)) return shiftMonths(SYNTHETIC_ON_DATE, -1);
  if (/\b(ano passado|um ano atras|1 ano atras)\b/.test(plain)) return shiftMonths(SYNTHETIC_ON_DATE, -12);
  if (/\bsem vaga\b/.test(plain)) return "2023-04-01";
  return SYNTHETIC_ON_DATE;
}

function shiftMonths(date: string, delta: number): string {
  const year = Number(date.slice(0, 4));
  const month = Number(date.slice(5, 7));
  const day = Number(date.slice(8, 10));
  const shifted = new Date(Date.UTC(year, month - 1 + delta, day));
  const nextMonth = String(shifted.getUTCMonth() + 1).padStart(2, "0");
  const nextDay = String(shifted.getUTCDate()).padStart(2, "0");
  return `${shifted.getUTCFullYear()}-${nextMonth}-${nextDay}`;
}
