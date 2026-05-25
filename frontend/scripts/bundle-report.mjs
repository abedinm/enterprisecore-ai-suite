#!/usr/bin/env node
// Bundle-size reporter for the Vite build output.
//
// Lists every chunk in dist/assets/ with raw + gzipped size, computes totals,
// emits a markdown table for CI summaries, and fails if either:
//   - any *.js chunk named "index*.js" exceeds MAX_ENTRY_KB (default 700)
//   - the total bundle size exceeds MAX_TOTAL_MB (default 5)
//
// Usage:
//   node scripts/bundle-report.mjs
//   MAX_ENTRY_KB=600 MAX_TOTAL_MB=4 node scripts/bundle-report.mjs
//   node scripts/bundle-report.mjs --json   # machine-readable

import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PROJECT_ROOT = resolve(__dirname, '..');
const ASSETS_DIR = resolve(PROJECT_ROOT, 'dist', 'assets');

const MAX_ENTRY_KB = Number(process.env.MAX_ENTRY_KB ?? '700');
const MAX_TOTAL_MB = Number(process.env.MAX_TOTAL_MB ?? '5');
const wantJson = process.argv.includes('--json');

function fmtBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function collectChunks() {
  if (!existsSync(ASSETS_DIR)) {
    console.error(`No build output at ${ASSETS_DIR}. Run \`npm run build\` first.`);
    process.exit(2);
  }
  const entries = readdirSync(ASSETS_DIR)
    .filter((f) => !f.endsWith('.map'))
    .map((file) => {
      const full = join(ASSETS_DIR, file);
      const buf = readFileSync(full);
      const stat = statSync(full);
      return {
        file,
        path: full,
        bytes: stat.size,
        gzip: gzipSync(buf).length,
      };
    });
  // Sort by raw bytes desc.
  entries.sort((a, b) => b.bytes - a.bytes);
  return entries;
}

function buildMarkdown(chunks) {
  const rows = [];
  rows.push('| Chunk | Type | Raw | Gzip |');
  rows.push('| --- | --- | ---: | ---: |');
  let totalRaw = 0;
  let totalGzip = 0;
  let jsRaw = 0;
  let jsGzip = 0;
  for (const c of chunks) {
    const ext = c.file.split('.').pop() ?? '';
    totalRaw += c.bytes;
    totalGzip += c.gzip;
    if (ext === 'js') {
      jsRaw += c.bytes;
      jsGzip += c.gzip;
    }
    rows.push(`| \`${c.file}\` | ${ext} | ${fmtBytes(c.bytes)} | ${fmtBytes(c.gzip)} |`);
  }
  rows.push(`| **Total** | — | **${fmtBytes(totalRaw)}** | **${fmtBytes(totalGzip)}** |`);
  rows.push(`| **JS only** | — | **${fmtBytes(jsRaw)}** | **${fmtBytes(jsGzip)}** |`);
  return { table: rows.join('\n'), totalRaw, totalGzip, jsRaw, jsGzip };
}

function main() {
  const chunks = collectChunks();
  const { table, totalRaw, totalGzip, jsRaw, jsGzip } = buildMarkdown(chunks);

  if (wantJson) {
    console.log(JSON.stringify({ chunks, totalRaw, totalGzip, jsRaw, jsGzip }, null, 2));
    return;
  }

  console.log('# Bundle report\n');
  console.log(table);
  console.log('');

  // Threshold checks.
  const entryChunk = chunks.find((c) => /^index-.*\.js$/.test(c.file));
  const entryKb = entryChunk ? entryChunk.bytes / 1024 : 0;
  const totalMb = totalRaw / 1024 / 1024;

  console.log('## Thresholds');
  console.log(`- index.js: ${entryKb.toFixed(1)} kB (limit ${MAX_ENTRY_KB} kB) -> ${entryKb <= MAX_ENTRY_KB ? 'PASS' : 'FAIL'}`);
  console.log(`- total:    ${totalMb.toFixed(2)} MB (limit ${MAX_TOTAL_MB} MB) -> ${totalMb <= MAX_TOTAL_MB ? 'PASS' : 'FAIL'}`);

  let failed = false;
  if (entryChunk && entryKb > MAX_ENTRY_KB) failed = true;
  if (totalMb > MAX_TOTAL_MB) failed = true;
  if (failed) {
    process.exitCode = 1;
    console.error('\nBundle size thresholds exceeded.');
  }
}

main();
