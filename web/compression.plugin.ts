import { createHash } from 'node:crypto';
import { readdir, readFile, writeFile } from 'node:fs/promises';
import { resolve, relative } from 'node:path';
import { gzipSync } from 'node:zlib';
import type { Plugin, ResolvedConfig } from 'vite';

export function gzipAsset(filename: string, bytes: Uint8Array): Buffer | undefined {
  if (!/\.(?:html|css|js|json|webmanifest|svg)$/.test(filename) || bytes.byteLength < 512) return;
  const encoded = gzipSync(bytes, { level: 9 });
  return encoded.length < bytes.byteLength ? encoded : undefined;
}

/** Static build output only. The host must opt into gzip_static and preserve Vary/Content-Type. */
export function compressedAssetsPlugin(): Plugin {
  let config: ResolvedConfig;
  return {
    name: 'mingjing-precompressed-static',
    apply: 'build',
    configResolved(value) {
      config = value;
    },
    closeBundle: {
      order: 'post',
      sequential: true,
      async handler() {
        const output = resolve(config.root, config.build.outDir);
        if (output !== resolve(config.root, '../static/dist')) throw new Error('Unexpected static build destination');
        const entries: { path: string; bytes: number; gzip_bytes: number; sha256: string; gzip_sha256: string }[] = [];
        const sha = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
        async function visit(directory: string) {
          for (const item of await readdir(directory, { withFileTypes: true })) {
            const filename = resolve(directory, item.name);
            if (item.isDirectory()) await visit(filename);
            else if (item.isFile()) {
              const bytes = await readFile(filename);
              const encoded = gzipAsset(filename, bytes);
              if (!encoded) continue;
              await writeFile(filename + '.gz', encoded);
              entries.push({
                path: relative(output, filename).replaceAll('\\', '/'),
                bytes: bytes.length,
                gzip_bytes: encoded.length,
                sha256: sha(bytes),
                gzip_sha256: sha(encoded),
              });
            }
          }
        }
        await visit(output);
        await writeFile(
          resolve(output, 'encoded-assets.json'),
          JSON.stringify(
            {
              encoding: 'gzip',
              identity_files_unchanged: true,
              entries: entries.sort((a, b) => a.path.localeCompare(b.path)),
            },
            null,
            2,
          ),
        );
      },
    },
  };
}
