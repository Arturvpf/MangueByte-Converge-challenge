const workforce = /equipe|centro|jornada|contrat|est[aá]gio|demanda|quadro|gente|capacidade|vaga|produtiv|atendimento|cobertura|pessoas|hora|janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|\d+\s+mes/i;
const outside = /corrig|c[oó]digo|login|cursor\.com|navegador|browser|token|api key/i;
const greeting = /^(oi|ola|hey|hello|hi|opa|salve|e ai|eae|bom dia|boa tarde|boa noite|tudo bem)(?:[!,.\s]+tudo bem)?[!.?\s]*$/i;

export function isGreeting(message: string): boolean {
  const text = message.normalize("NFD").replace(/\p{M}/gu, "").trim();
  return greeting.test(text);
}

export function isWorkforceQuestion(message: string): boolean {
  const text = message.normalize("NFD").replace(/\p{M}/gu, "");
  if (outside.test(text) && !workforce.test(text)) return false;
  return workforce.test(text);
}

export const introReply = "Oi. Eu sou a Alinia. Eu olho a equipe do Centro: a jornada, a capacidade, a contratação e o estágio. Pode perguntar, por exemplo: como está a equipe hoje, 8 de novembro de 2026?";

export const offTopicReply = "Eu só falo da equipe. Pergunte como está o Centro, a jornada, a contratação ou o estágio.";
