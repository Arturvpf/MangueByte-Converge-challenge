#!/usr/bin/env node
/**
 * Build sem dependências: limpa dist/ e copia src/ para lá.
 *
 * O site é HTML + CSS + ES modules nativos, então não há bundling. dist/ é
 * o diretório publicado (ver .openai/hosting.json -> static.directory).
 */

import { cp, rm, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = path.join(root, 'src');
const dist = path.join(root, 'dist');

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
await cp(src, dist, {
  recursive: true,
  filter: (file) => !path.basename(file).startsWith('.'),
});

console.log(`build: ${path.relative(process.cwd(), src)} -> ${path.relative(process.cwd(), dist)}`);
