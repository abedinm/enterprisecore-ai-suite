// Copies the PyInstaller-built backend.exe into electron/resources/backend so
// electron-builder picks it up via the "extraResources" mapping. Idempotent.
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'backend', 'dist', 'enterprisecore-backend.exe');
const DST_DIR = path.join(ROOT, 'electron', 'resources', 'backend');
const DST = path.join(DST_DIR, 'enterprisecore-backend.exe');

if (!fs.existsSync(SRC)) {
  console.error(`[stage-backend] missing source: ${SRC}`);
  console.error('Did pyinstaller run? Check backend/pyinstaller.log');
  process.exit(1);
}

fs.mkdirSync(DST_DIR, { recursive: true });
fs.copyFileSync(SRC, DST);
const size = fs.statSync(DST).size;
console.log(`[stage-backend] copied ${(size / 1024 / 1024).toFixed(1)} MB → ${DST}`);
