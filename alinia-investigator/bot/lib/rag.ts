import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createEmbeddings, embeddingModelId } from "./embeddings.js";
import { quarantine } from "./privacy.js";

export const RULE_TOPICS = [
  "autonomia",
  "privacidade",
  "evidencia",
  "capacidade",
  "previsao",
  "cenarios",
  "jornada",
  "cotas",
  "prova",
  "contencao",
] as const;

export type RuleTopic = (typeof RULE_TOPICS)[number];

const TOPIC_QUERY: Record<RuleTopic, string> = {
  autonomia: "limites de autonomia aprovacao humana requisicao escala desligamento",
  privacidade: "dados pessoais LGPD descarte salario saude minimizacao",
  evidencia: "hipotese evidencia abstencao numero relato gestor",
  capacidade: "demanda capacidade gap homogeneo competencia turno backlog",
  previsao: "previsao baseline backtesting intervalo horizonte abstencao",
  cenarios: "contratar capacitar realocar turno headcount residual",
  jornada: "jornada repouso guarda direitos instrumento coletivo transicao",
  cotas: "cota aprendiz deficiencia agregado estagio reserva",
  prova: "braco processo atual ganho incremental KPI sem modelo",
  contencao: "entrada maligna instrucao dado nao confiavel ferramenta filtrada",
};

type StoredChunk = {
  id: string;
  source: string;
  text: string;
  vector: number[];
};

type StoredIndex = {
  embedding: string;
  chunks: StoredChunk[];
};

export type RetrievedChunk = {
  id: string;
  source: string;
  text: string;
};

const indexPath = join(dirname(fileURLToPath(import.meta.url)), "corpus", "index.json");

let stored: StoredIndex | undefined;

export async function searchRules(topic: RuleTopic): Promise<RetrievedChunk[]> {
  const index = readIndex();
  if (index === undefined || index.embedding !== embeddingModelId()) return [];
  const query = await createEmbeddings().embedQuery(TOPIC_QUERY[topic]);
  return index.chunks
    .map((chunk) => ({ chunk, score: cosine(query, chunk.vector) }))
    .filter((item) => item.score >= 0.2)
    .sort((left, right) => right.score - left.score)
    .slice(0, 4)
    .map(({ chunk }) => ({
      id: chunk.id,
      source: chunk.source,
      text: quarantine(chunk.text).text,
    }));
}

function readIndex(): StoredIndex | undefined {
  if (stored) return stored;
  try {
    stored = JSON.parse(readFileSync(indexPath, "utf8")) as StoredIndex;
  } catch {
    return undefined;
  }
  return stored;
}

function cosine(left: number[], right: number[]): number {
  const length = Math.min(left.length, right.length);
  let score = 0;
  for (let index = 0; index < length; index += 1) {
    score += (left[index] ?? 0) * (right[index] ?? 0);
  }
  return score;
}
