#!/usr/bin/env node
/**
 * Extracts every i18n key referenced from `src/` via `t('…')` or `i18n.t('…')`
 * and reports which keys are missing from each locale JSON file. Run with:
 *
 *     node src/i18n/extract.mjs            # report missing keys
 *     node src/i18n/extract.mjs --write    # also stub missing keys with the
 *                                          # English value as a placeholder
 *
 * Regex-driven on purpose — no AST, no babel, no extra deps. Picks up the
 * default react-i18next usage and `i18n.t()` direct calls. Hover-string
 * templates and computed keys are ignored.
 */
import { readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, '..');
const LOCALES_DIR = resolve(__dirname, 'locales');

const KEY_RE = /\b(?:t|i18n\.t)\(\s*['"`]([a-zA-Z0-9_.:-]+)['"`]/g;
const EXTS = new Set(['.ts', '.tsx', '.js', '.jsx']);

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const s = statSync(p);
    if (s.isDirectory()) {
      if (name === 'node_modules' || name === 'dist' || name === 'i18n') continue;
      walk(p, out);
    } else if (EXTS.has(p.slice(p.lastIndexOf('.')))) {
      out.push(p);
    }
  }
  return out;
}

function extractKeys(files) {
  const keys = new Set();
  for (const f of files) {
    const src = readFileSync(f, 'utf8');
    for (const m of src.matchAll(KEY_RE)) {
      keys.add(m[1]);
    }
  }
  return [...keys].sort();
}

function getNested(obj, path) {
  return path.split('.').reduce((acc, k) => (acc && acc[k] !== undefined ? acc[k] : undefined), obj);
}
function setNested(obj, path, val) {
  const parts = path.split('.');
  let cur = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (typeof cur[parts[i]] !== 'object' || cur[parts[i]] === null) cur[parts[i]] = {};
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = val;
}

const write = process.argv.includes('--write');
const files = walk(SRC);
const keys = extractKeys(files);
console.log(`Scanned ${files.length} files, found ${keys.length} unique t() keys.`);

const en = JSON.parse(readFileSync(join(LOCALES_DIR, 'en.json'), 'utf8'));
const locales = readdirSync(LOCALES_DIR).filter((n) => n.endsWith('.json') && n !== 'en.json');

let missing = 0;
for (const file of locales) {
  const path = join(LOCALES_DIR, file);
  const data = JSON.parse(readFileSync(path, 'utf8'));
  const gaps = [];
  for (const k of keys) {
    if (getNested(data, k) === undefined) {
      gaps.push(k);
      if (write) setNested(data, k, getNested(en, k) ?? k);
    }
  }
  if (gaps.length) {
    missing += gaps.length;
    console.log(`  ${file}: missing ${gaps.length} keys`);
    for (const k of gaps.slice(0, 6)) console.log(`    - ${k}`);
    if (gaps.length > 6) console.log(`    … +${gaps.length - 6} more`);
  }
  if (write) writeFileSync(path, JSON.stringify(data, null, 2) + '\n');
}
if (write && missing) console.log(`\nStubbed ${missing} missing keys (using English fallbacks).`);
if (!missing) console.log('All locales have every key.');
