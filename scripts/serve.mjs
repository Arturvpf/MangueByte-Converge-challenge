#!/usr/bin/env node
/**
 * Servidor estático mínimo para desenvolvimento.
 * WebGL e ES modules não funcionam via file://, por isso o site precisa de HTTP.
 *
 *   node scripts/serve.mjs            -> serve src/ em http://localhost:5173
 *   node scripts/serve.mjs dist 8080  -> serve dist/ na porta 8080
 */

import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dir = path.join(root, process.argv[2] ?? 'src');
const port = Number(process.argv[3] ?? 5173);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
  '.json': 'application/json',
};

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  let file = path.join(dir, decodeURIComponent(url.pathname));
  if (!file.startsWith(dir)) {
    res.writeHead(403).end();
    return;
  }
  try {
    if ((await stat(file)).isDirectory()) file = path.join(file, 'index.html');
    const body = await readFile(file);
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] ?? 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404, { 'content-type': 'text/plain' }).end('404');
  }
}).listen(port, '127.0.0.1', () => console.log(`serve: ${path.relative(root, dir)} em http://localhost:${port}`));
