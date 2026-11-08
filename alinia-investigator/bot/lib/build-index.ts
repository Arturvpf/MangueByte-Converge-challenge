import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Document } from "@langchain/core/documents";
import { RecursiveCharacterTextSplitter } from "@langchain/textsplitters";
import { createEmbeddings, embeddingModelId } from "./embeddings.js";

const corpusDir = join(dirname(fileURLToPath(import.meta.url)), "corpus");

const documents = readdirSync(corpusDir)
  .filter((name) => name.endsWith(".md"))
  .sort()
  .map((name) => new Document({
    pageContent: readFileSync(join(corpusDir, name), "utf8"),
    metadata: { source: name },
  }));

const splitter = new RecursiveCharacterTextSplitter({
  chunkSize: 1000,
  chunkOverlap: 200,
});
const splits = await splitter.splitDocuments(documents);
const vectors = await createEmbeddings().embedDocuments(
  splits.map((split) => split.pageContent),
);

const chunks = splits.map((split, index) => {
  const source = typeof split.metadata.source === "string" ? split.metadata.source : "regra";
  return {
    id: `${source.replace(/\.md$/, "")}-${index}`,
    source,
    text: split.pageContent,
    vector: vectors[index] ?? [],
  };
});

writeFileSync(
  join(corpusDir, "index.json"),
  JSON.stringify({ embedding: embeddingModelId(), chunks }),
);
console.log(`indexed ${chunks.length} chunks with ${embeddingModelId()}`);
