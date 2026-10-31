import { createHash } from 'node:crypto';
import { readFile, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { Plugin, ResolvedConfig } from 'vite';

export const SHELL_FONTS = [
  'noto-sans-sc-119-wght-normal.woff2',
  'noto-sans-sc-latin-wght-normal.woff2',
  'noto-serif-sc-119-wght-normal.woff2',
  'noto-serif-sc-latin-wght-normal.woff2',
];
export function selectShellFiles(assetNames: string[], publicNames: string[]) {
  return [
    ...new Set([
      'index.html',
      ...assetNames.filter((name) => /^assets\/[A-Za-z0-9_.-]+-[A-Za-z0-9_-]{8,}\.(?:js|css)$/.test(name)),
      ...publicNames.filter((name) =>
        [
          'favicon.svg',
          'pwa/manifest.webmanifest',
          'pwa/seal.svg',
          'pwa/icon-192.png',
          'pwa/icon-512.png',
          'fonts/fonts.css',
          ...SHELL_FONTS.map((font) => `fonts/${font}`),
        ].includes(name),
      ),
    ]),
  ].sort();
}
export function shellPwaPlugin(): Plugin {
  let config: ResolvedConfig;
  return {
    name: 'mingjing-static-shell',
    apply: 'build',
    enforce: 'post',
    configResolved(value) {
      config = value;
    },
    async closeBundle() {
      const directory = resolve(config.root, config.build.outDir);
      const assets = (await readdir(resolve(directory, 'assets'))).map((name) => `assets/${name}`);
      const publicNames = [
        'favicon.svg',
        ...(await readdir(resolve(directory, 'pwa'))).map((name) => `pwa/${name}`),
        ...(await readdir(resolve(directory, 'fonts'))).map((name) => `fonts/${name}`),
      ];
      const entries = await Promise.all(
        selectShellFiles(assets, publicNames).map(async (path) => {
          const body = await readFile(resolve(directory, path));
          return { path, bytes: body.length, sha256: createHash('sha256').update(body).digest('hex') };
        }),
      );
      const fontBytes = entries
        .filter((entry) => entry.path.endsWith('.woff2'))
        .reduce((sum, entry) => sum + entry.bytes, 0);
      if (fontBytes > 512 * 1024) throw new Error('PWA selected font slices exceed 512 KiB');
      if (entries.reduce((sum, entry) => sum + entry.bytes, 0) > 4 * 1024 * 1024)
        throw new Error('PWA static shell exceeds 4 MiB');
      const runtime = await readFile(resolve(config.root, 'public/pwa/shell-runtime.js'), 'utf8');
      const version = createHash('sha256').update(JSON.stringify(entries)).update(runtime).digest('hex');
      const manifest = { version, assets: entries };
      await writeFile(
        resolve(directory, 'shell-sw.js'),
        `self.__MINGJING_SHELL__=${JSON.stringify(manifest)};\n${runtime}`,
      );
      await writeFile(resolve(directory, 'pwa/shell-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
    },
  };
}
