#!/usr/bin/env node
// Lighthouse audit runner for EnterpriseCore frontend.
//
// Usage:
//   node scripts/lighthouse-audit.mjs                  # runs against dev server
//   LH_URL=http://127.0.0.1:4173 node scripts/lighthouse-audit.mjs
//   LH_MIN_SCORE=85 node scripts/lighthouse-audit.mjs  # tighter threshold
//
// Fails (exit 1) if any category score is below LH_MIN_SCORE (default 80).
// Writes the full HTML report to frontend/lighthouse-report.html so devs can
// open it and dig into the suggestions.

import { writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as chromeLauncher from 'chrome-launcher';
import lighthouse from 'lighthouse';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PROJECT_ROOT = resolve(__dirname, '..');

const URL_TO_AUDIT = process.env.LH_URL ?? 'http://127.0.0.1:5173/';
const MIN_SCORE = Number(process.env.LH_MIN_SCORE ?? '80');
const REPORT_PATH = resolve(PROJECT_ROOT, 'lighthouse-report.html');

function colour(name, score) {
  const pct = Math.round((score ?? 0) * 100);
  const flag = pct >= MIN_SCORE ? 'PASS' : 'FAIL';
  return `  ${name.padEnd(18)} ${String(pct).padStart(3)}/100  ${flag}`;
}

async function main() {
  console.log(`Lighthouse audit -> ${URL_TO_AUDIT}`);
  console.log(`Pass threshold:    ${MIN_SCORE}/100`);

  const chrome = await chromeLauncher.launch({
    chromeFlags: ['--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });
  try {
    const options = {
      logLevel: 'error',
      output: 'html',
      onlyCategories: ['performance', 'accessibility', 'best-practices', 'seo'],
      port: chrome.port,
    };
    const runnerResult = await lighthouse(URL_TO_AUDIT, options);
    const lhr = runnerResult.lhr;

    writeFileSync(REPORT_PATH, runnerResult.report);

    const categories = lhr.categories;
    console.log('\nScores:');
    console.log(colour('Performance', categories.performance?.score));
    console.log(colour('Accessibility', categories.accessibility?.score));
    console.log(colour('Best Practices', categories['best-practices']?.score));
    console.log(colour('SEO', categories.seo?.score));
    console.log(`\nReport: ${REPORT_PATH}`);

    const failed = Object.entries(categories)
      .filter(([, c]) => Math.round((c?.score ?? 0) * 100) < MIN_SCORE)
      .map(([k]) => k);
    if (failed.length > 0) {
      console.error(`\nLighthouse failed — below threshold: ${failed.join(', ')}`);
      process.exitCode = 1;
    } else {
      console.log('\nLighthouse passed all thresholds.');
    }
  } finally {
    await chrome.kill();
  }
}

main().catch((err) => {
  console.error('Lighthouse audit crashed:', err);
  process.exit(2);
});
