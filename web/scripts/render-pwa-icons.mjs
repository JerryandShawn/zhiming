import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
// Optional raster export for platforms that require PNG. Run only when explicitly scheduled locally.
const directory = new URL('../public/pwa/', import.meta.url);
const svg = await fs.readFile(new URL('seal.svg', directory), 'utf8');
const browser = await chromium.launch({ headless: true, channel: process.env.CI ? undefined : 'chrome' });
try {
  for (const size of [192, 512]) {
    const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
    await page.setContent(
      `<html><head><style>html,body{margin:0;width:100%;height:100%}svg{display:block;width:100%;height:100%}</style></head><body>${svg}</body></html>`,
    );
    await page.screenshot({ path: fileURLToPath(new URL(`icon-${size}.png`, directory)) });
    await page.close();
  }
} finally {
  await browser.close();
}
const manifestUrl = new URL('manifest.webmanifest', directory);
const manifest = JSON.parse(await fs.readFile(manifestUrl, 'utf8'));
manifest.icons = [
  { src: 'seal.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
  ...[192, 512].map((size) => ({
    src: `icon-${size}.png`,
    sizes: `${size}x${size}`,
    type: 'image/png',
    purpose: 'any maskable',
  })),
];
await fs.writeFile(manifestUrl, JSON.stringify(manifest, null, 2) + '\n');
