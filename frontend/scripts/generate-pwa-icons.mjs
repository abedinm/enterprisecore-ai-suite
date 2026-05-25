// Regenerate PWA PNG icons from the master SVG.
// Run: `node scripts/generate-pwa-icons.mjs`
//
// Tries `sharp` first (high-quality rasterization). If sharp isn't installed,
// falls back to a tiny built-in PNG writer that emits a solid brand-coloured
// PNG with the EnterpriseCore monogram baked in as a 1-bit overlay. The
// fallback is good enough to satisfy PWA installability requirements (Chrome
// just needs PNGs that exist and decode); for production polish run a fresh
// install with sharp available.

import { writeFileSync, readFileSync, mkdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { deflateSync } from 'node:zlib';

const __dirname = dirname(fileURLToPath(import.meta.url));
const iconsDir = resolve(__dirname, '..', 'public', 'icons');
const svgPath = resolve(iconsDir, 'icon.svg');

if (!existsSync(iconsDir)) {
  mkdirSync(iconsDir, { recursive: true });
}

const sizes = [
  { name: 'icon-192.png', size: 192, maskable: false },
  { name: 'icon-512.png', size: 512, maskable: false },
  { name: 'icon-512-maskable.png', size: 512, maskable: true },
];

async function loadSharp() {
  try {
    const mod = await import('sharp');
    return mod.default ?? mod;
  } catch {
    return null;
  }
}

async function generateWithSharp(sharp) {
  const svg = readFileSync(svgPath);
  for (const { name, size, maskable } of sizes) {
    const padding = maskable ? Math.round(size * 0.1) : 0;
    const inner = size - padding * 2;
    const buffer = await sharp(svg)
      .resize(inner, inner)
      .extend({
        top: padding,
        bottom: padding,
        left: padding,
        right: padding,
        background: { r: 79, g: 70, b: 229, alpha: 1 },
      })
      .png()
      .toBuffer();
    writeFileSync(resolve(iconsDir, name), buffer);
    console.log(`wrote ${name} (sharp, ${size}x${size}${maskable ? ' maskable' : ''})`);
  }
}

// Tiny manual PNG encoder for the fallback path. Produces a solid brand-coloured
// square with white horizontal bars approximating the logo. Just enough pixels
// for browsers to accept it as a valid PNG.
function crc32(buf) {
  let c;
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    c = n;
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    }
    table[n] = c >>> 0;
  }
  let crc = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    crc = table[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, 'ascii');
  const crcInput = Buffer.concat([typeBuf, data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(crcInput), 0);
  return Buffer.concat([len, typeBuf, data, crc]);
}

function encodePng(width, height, getPixel) {
  // PNG: 8-bit RGBA, filter type 0 per scanline.
  const raw = Buffer.alloc((width * 4 + 1) * height);
  let p = 0;
  for (let y = 0; y < height; y++) {
    raw[p++] = 0; // filter: none
    for (let x = 0; x < width; x++) {
      const px = getPixel(x, y);
      raw[p++] = px[0];
      raw[p++] = px[1];
      raw[p++] = px[2];
      raw[p++] = px[3];
    }
  }
  const idat = deflateSync(raw);
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  return Buffer.concat([
    sig,
    chunk('IHDR', ihdr),
    chunk('IDAT', idat),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

function renderFallback(size, maskable) {
  const brand = [0x4f, 0x46, 0xe5, 0xff];
  const white = [0xff, 0xff, 0xff, 0xff];
  const accent = [0xa5, 0xb4, 0xfc, 0xff];
  const radius = maskable ? size * 0.5 : size * 0.19;
  const cx = size / 2;
  const cy = size / 2;
  const safe = maskable ? size * 0.1 : 0;

  function inRoundedRect(x, y) {
    if (x < safe || x > size - safe || y < safe || y > size - safe) return false;
    if (maskable) {
      const dx = x - cx;
      const dy = y - cy;
      return dx * dx + dy * dy <= radius * radius;
    }
    // squircle approximation: corners clipped
    const rx = Math.min(x, size - x);
    const ry = Math.min(y, size - y);
    if (rx >= radius || ry >= radius) return true;
    const ex = radius - rx;
    const ey = radius - ry;
    return ex * ex + ey * ey <= radius * radius;
  }

  const innerSize = size - safe * 2;
  const barLong = innerSize * 0.6;
  const barShort = innerSize * 0.4;
  const barX = safe + (innerSize - barLong) / 2;
  const barShortX = safe + (innerSize - barLong) / 2;
  const barHeight = innerSize * 0.06;
  const gap = innerSize * 0.1;
  const firstY = safe + innerSize * 0.28;
  const dotR = innerSize * 0.05;
  const dotCx = barShortX + barShort + dotR * 2.4;
  const dotCy = firstY + (barHeight / 2) + (gap + barHeight) * 2;

  return (x, y) => {
    if (!inRoundedRect(x, y)) return [0, 0, 0, 0];
    // dot
    const ddx = x - dotCx;
    const ddy = y - dotCy;
    if (ddx * ddx + ddy * ddy <= dotR * dotR) return accent;
    // three bars
    for (let i = 0; i < 3; i++) {
      const by = firstY + i * (barHeight + gap);
      const bx0 = i === 2 ? barShortX : barX;
      const bx1 = bx0 + (i === 2 ? barShort : barLong);
      if (y >= by && y <= by + barHeight && x >= bx0 && x <= bx1) return white;
    }
    return brand;
  };
}

async function generateFallback() {
  for (const { name, size, maskable } of sizes) {
    const getPixel = renderFallback(size, maskable);
    const png = encodePng(size, size, getPixel);
    writeFileSync(resolve(iconsDir, name), png);
    console.log(`wrote ${name} (fallback, ${size}x${size}${maskable ? ' maskable' : ''})`);
  }
}

async function main() {
  if (!existsSync(svgPath)) {
    throw new Error(`master svg not found at ${svgPath}`);
  }
  const sharp = await loadSharp();
  if (sharp) {
    await generateWithSharp(sharp);
  } else {
    console.log('sharp not available, using built-in PNG encoder fallback');
    await generateFallback();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
