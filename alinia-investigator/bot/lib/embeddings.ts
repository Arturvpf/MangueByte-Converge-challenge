import { Embeddings } from "@langchain/core/embeddings";

const DIMENSIONS = 256;

/**
 * Mesmo modelo na indexação e na consulta.
 * Troque esta função pela API de embeddings quando ela existir e
 * rode de novo `npm run index`. Não misture dois modelos no mesmo índice.
 */
export function embeddingModelId(): string {
  return "local-hash-v1";
}

export function createEmbeddings(): Embeddings {
  return new LocalHashEmbeddings();
}

class LocalHashEmbeddings extends Embeddings {
  constructor() {
    super({});
  }

  async embedDocuments(texts: string[]): Promise<number[][]> {
    return texts.map((text) => hashEmbed(text));
  }

  async embedQuery(text: string): Promise<number[]> {
    return hashEmbed(text);
  }
}

function hashEmbed(text: string): number[] {
  const vector = Array.from({ length: DIMENSIONS }, () => 0);
  const tokens = normalize(text).split(/[^a-z0-9]+/).filter((token) => token.length > 2);
  for (const token of tokens) {
    const hash = fnv(token);
    vector[hash % DIMENSIONS] += (hash & 1) === 0 ? 1 : -1;
  }
  const norm = Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0));
  if (norm === 0) return vector;
  return vector.map((value) => value / norm);
}

function normalize(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

function fnv(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}
