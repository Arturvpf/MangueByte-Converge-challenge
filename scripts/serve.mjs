#!/usr/bin/env node
/**
 * Servidor estático mínimo para desenvolvimento.
 * WebGL e ES modules não funcionam via file://, por isso o site precisa de HTTP.
 *
 *   node scripts/serve.mjs            -> serve src/ em http://localhost:5173
 *   node scripts/serve.mjs dist 8080  -> serve dist/ na porta 8080
 *
 * /agent/health e /agent/chat são repassados ao agente em ALINIA_AGENT_URL
 * (padrão http://127.0.0.1:3141, o `npm run agent`). Cada /agent/chat leva a
 * ficha do site (scripts/agent-site-context.mjs).
 */

import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { SITE_CONTEXT } from './agent-site-context.mjs';

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

/* --- Repasse para o agente ------------------------------------------------
   O servidor do agente (alinia-investigator) recusa chamadas de navegador
   vindas de outra origem. A tela fala com /agent/* aqui, na mesma origem, e
   este servidor repassa. A chave do modelo fica só no processo do agente. */
const AGENT = (process.env.ALINIA_AGENT_URL ?? 'http://127.0.0.1:3141').replace(/\/$/, '');
const JSON_TYPE = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' };

function readBody(req, limit = 4096) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(new Error('too_large'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

async function proxyAgent(req, res, url) {
  if (url.pathname === '/agent/health' && req.method === 'GET') {
    // Só diz se o agente está de pé; o /v1/health dele expõe memória do processo.
    const ok = await fetch(`${AGENT}/v1/health`, { signal: AbortSignal.timeout(2000) }).then((r) => r.ok, () => false);
    res.writeHead(ok ? 200 : 502, JSON_TYPE).end(JSON.stringify({ ok }));
    return;
  }
  if (url.pathname !== '/agent/chat' || req.method !== 'POST') {
    res.writeHead(404, JSON_TYPE).end(JSON.stringify({ ok: false }));
    return;
  }
  const origin = req.headers.origin;
  if (origin && origin !== `http://${req.headers.host}`) {
    res.writeHead(403, JSON_TYPE).end(JSON.stringify({ ok: false, error: 'forbidden_origin' }));
    return;
  }
  let message;
  try {
    message = JSON.parse(await readBody(req)).message;
  } catch {
    message = undefined;
  }
  if (typeof message !== 'string' || !message.trim() || message.length > 500) {
    res.writeHead(400, JSON_TYPE).end(JSON.stringify({ ok: false, error: 'invalid_message' }));
    return;
  }
  let upstream;
  try {
    upstream = await fetch(`${AGENT}/v1/channels/workflow/chat`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'text/plain' },
      // A ficha do site vai junto: o agente responde a partir do que a tela mostra.
      body: JSON.stringify({ message, context: SITE_CONTEXT }),
      signal: AbortSignal.timeout(60_000),
    });
  } catch {
    res.writeHead(502, JSON_TYPE).end(JSON.stringify({ ok: false, error: 'agent_unavailable' }));
    return;
  }
  res.writeHead(upstream.status, {
    'content-type': upstream.headers.get('content-type') ?? 'text/plain; charset=utf-8',
    'cache-control': 'no-store',
  });
  try {
    if (upstream.body) for await (const chunk of upstream.body) res.write(chunk);
  } finally {
    res.end();
  }
}

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname.startsWith('/agent/')) {
    await proxyAgent(req, res, url).catch(() => { if (!res.headersSent) res.writeHead(502).end(); else res.end(); });
    return;
  }
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
