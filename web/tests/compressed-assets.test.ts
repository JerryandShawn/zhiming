import { gunzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { gzipAsset } from '../compression.plugin';

describe('static compressed delivery retains byte-exact identity assets', () => {
  it.each(['app.js', 'fonts.css', 'index.html', 'public.json', 'manifest.webmanifest', 'icon.svg'])(
    'round trips %s without touching its source',
    (name) => {
      const bytes = Buffer.from('合成静态内容 '.repeat(200));
      const copy = Buffer.from(bytes);
      const encoded = gzipAsset(name, bytes)!;
      expect(encoded.length).toBeLessThan(bytes.length);
      expect(gunzipSync(encoded)).toEqual(bytes);
      expect(bytes).toEqual(copy);
    },
  );
  it.each(['font.woff2', 'icon.png', 'output.gz', 'data.sqlite', 'body.txt'])('does not encode %s', (name) => {
    expect(gzipAsset(name, Buffer.from('synthetic'.repeat(200)))).toBeUndefined();
  });
  it('does not create a sidecar for tiny or already incompressible payloads', () => {
    expect(gzipAsset('tiny.js', Buffer.from('x'))).toBeUndefined();
    const bytes = Buffer.concat(Array.from({ length: 16 }, (_, i) => createHash('sha256').update(String(i)).digest()));
    expect(gzipAsset('asset.js', bytes)).toBeUndefined();
  });
});
